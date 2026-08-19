import tempfile
import unittest
from pathlib import Path

import wine_shop_db
from wine_shop_db import (
    connect_shop,
    ensure_shop_db,
    search_shop_products,
    shop_collection_status,
    upsert_product,
    utc_now,
)


class WineShopDatabaseTests(unittest.TestCase):
    def test_search_remains_available_during_collection_write(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "shops.sqlite"
            ensure_shop_db(db_path)
            con = connect_shop(db_path)
            try:
                merchant_id = con.execute(
                    "insert into merchants(name,normalized_name,website_url,country,city,active,inventory_status) values(?,?,?,?,?,1,'found')",
                    ("Concurrent Wines", "concurrent wines", "https://wines.example", "FR", "Paris"),
                ).lastrowid
                source_id = con.execute(
                    "insert into merchant_sources(merchant_id,source_type,source_url,status,parser_status) values(?,'html',?,'found','parsed')",
                    (merchant_id, "https://wines.example/list"),
                ).lastrowid
                upsert_product(con, merchant_id, source_id, {
                    "source_key": "rayas-2011",
                    "source_url": "https://wines.example/list",
                    "raw_name": "Chateau Rayas 2011",
                    "raw_text": "Chateau Rayas 2011 EUR 1000",
                    "price_value": 1000,
                    "currency": "EUR",
                    "price_text": "EUR 1000",
                })
                con.commit()
            finally:
                con.close()

            writer = connect_shop(db_path)
            try:
                writer.execute("begin immediate")
                writer.execute(
                    "update merchants set last_seen_at=? where id=?",
                    (utc_now(), merchant_id),
                )

                results = search_shop_products("Rayas", path=db_path)
            finally:
                writer.rollback()
                writer.close()

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["venue"]["name"], "Concurrent Wines")

    def test_map_only_includes_inventory_checked_shops_with_valid_locations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "shops.sqlite"
            ensure_shop_db(db_path)
            con = connect_shop(db_path)
            try:
                con.executemany(
                    """
                    insert into merchants(
                      name,normalized_name,website_url,country,city,address,
                      latitude,longitude,last_inventory_checked_at,inventory_status
                    ) values(?,?,?,?,?,?,?,?,?,?)
                    """,
                    [
                        (
                            "Checked Wine Shop", "checked wine shop", "https://checked.example",
                            "France", "Paris", "Paris, France", 48.8566, 2.3522,
                            utc_now(), "review",
                        ),
                        (
                            "Candidate Only", "candidate only", "https://candidate.example",
                            "France", "Lyon", "Lyon, France", 45.7640, 4.8357,
                            None, "pending",
                        ),
                        (
                            "Bad Antarctic Candidate", "bad antarctic candidate", "https://bad.example",
                            "AQ", None, "AQ", -80.7606, -144.8438,
                            utc_now(), "review",
                        ),
                    ],
                )
                con.commit()
            finally:
                con.close()

            payload = shop_collection_status(path=db_path)
            self.assertEqual([row["name"] for row in payload["mapMerchants"]], ["Checked Wine Shop"])

    def test_product_is_searchable_in_integrated_result_shape(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "shops.sqlite"
            ensure_shop_db(db_path)
            con = connect_shop(db_path)
            try:
                merchant_id = con.execute(
                    """
                    insert into merchants(
                      wine_searcher_id,wine_searcher_url,name,normalized_name,website_url,
                      country,city,address,latitude,longitude,last_seen_at,inventory_status
                    ) values(?,?,?,?,?,?,?,?,?,?,?,'found')
                    """,
                    (
                        33938, "https://www.wine-searcher.com/merchant/33938",
                        "Di Jin Wines SA", "di jin wines sa", "https://www.di-jin-wines.com/en/",
                        "CH", "Geneva", "Geneva, Switzerland", 46.2044, 6.1432, utc_now(),
                    ),
                ).lastrowid
                source_id = con.execute(
                    """
                    insert into merchant_sources(merchant_id,source_type,source_url,status,parser_status)
                    values(?, 'xlsx', ?, 'found', 'parsed')
                    """,
                    (merchant_id, "https://www.di-jin-wines.com/pricelist.xlsx"),
                ).lastrowid
                upsert_product(con, merchant_id, source_id, {
                    "source_key": "rayas-2011",
                    "source_url": "https://www.di-jin-wines.com/pricelist.xlsx",
                    "raw_name": "2011 Chateau Rayas Chateauneuf-du-Pape",
                    "raw_text": "2011 Chateau Rayas Chateauneuf-du-Pape CHF 1700",
                    "wine_name": "Chateau Rayas Chateauneuf-du-Pape",
                    "vintage": "2011",
                    "price_value": 1700,
                    "currency": "CHF",
                    "price_text": "CHF 1700",
                    "availability": "listed",
                })
                con.commit()
            finally:
                con.close()

            results = search_shop_products("Rayas", country="Switzerland", path=db_path)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["source"], "Wine Shop Database")
            self.assertEqual(results[0]["prices"], ["CHF 1700"])
            self.assertEqual(results[0]["venue"]["name"], "Di Jin Wines SA")
            self.assertEqual(results[0]["venue"]["country"], "Switzerland")
            self.assertEqual(results[0]["venue"]["countryCode"], "CH")
            self.assertEqual(
                results[0]["venue"]["inventoryUrl"],
                "https://www.di-jin-wines.com/pricelist.xlsx",
            )
            self.assertEqual(results[0]["wineList"]["downloadUrl"], "https://www.di-jin-wines.com/pricelist.xlsx")

    def test_search_terms_can_span_merchant_and_product_names(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "shops.sqlite"
            ensure_shop_db(db_path)
            con = connect_shop(db_path)
            try:
                merchant_id = con.execute(
                    "insert into merchants(name,normalized_name,website_url,country,city,active,inventory_status) values(?,?,?,?,?,1,'found')",
                    ("Volcano Winery", "volcano winery", "https://volcanowinery.com/", "US", "Volcano"),
                ).lastrowid
                source_id = con.execute(
                    "insert into merchant_sources(merchant_id,source_type,source_url,status,parser_status) values(?,'json',?,'found','parsed')",
                    (merchant_id, "https://volcanowinery.com/wines"),
                ).lastrowid
                upsert_product(con, merchant_id, source_id, {
                    "source_key": "rose", "source_url": "https://volcanowinery.com/wine/volcano-rose-750ml",
                    "raw_name": "Rosé 750ml", "raw_text": "Rosé 750ml", "wine_name": "Rosé 750ml",
                    "price_value": 30, "currency": "USD", "price_text": "USD 30",
                })
                con.commit()
            finally:
                con.close()

            results = search_shop_products("Volcano Rose", path=db_path)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["venue"]["name"], "Volcano Winery")
            self.assertEqual(results[0]["venue"]["inventoryUrl"], "https://volcanowinery.com/wines")
            self.assertEqual(results[0]["priceValue"], 30)

    def test_all_terms_are_filtered_before_candidate_limit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "shops.sqlite"
            ensure_shop_db(db_path)
            con = connect_shop(db_path)
            try:
                decoy_merchant_id = con.execute(
                    "insert into merchants(name,normalized_name,website_url,country,city,active,inventory_status) values(?,?,?,?,?,1,'found')",
                    ("Discount Wines", "discount wines", "https://discount.example", "US", "Portland"),
                ).lastrowid
                decoy_source_id = con.execute(
                    "insert into merchant_sources(merchant_id,source_type,source_url,status,parser_status) values(?,'html',?,'found','parsed')",
                    (decoy_merchant_id, "https://discount.example/list"),
                ).lastrowid
                for index in range(2001):
                    upsert_product(con, decoy_merchant_id, decoy_source_id, {
                        "source_key": f"rose-{index}",
                        "source_url": f"https://discount.example/rose-{index}",
                        "raw_name": f"Rose {index}",
                        "raw_text": f"Rose {index}",
                        "wine_name": f"Rose {index}",
                        "price_value": 1,
                        "currency": "USD",
                        "price_text": "USD 1",
                    })

                merchant_id = con.execute(
                    "insert into merchants(name,normalized_name,website_url,country,city,active,inventory_status) values(?,?,?,?,?,1,'found')",
                    ("Volcano Winery", "volcano winery", "https://volcanowinery.com/", "US", "Volcano"),
                ).lastrowid
                source_id = con.execute(
                    "insert into merchant_sources(merchant_id,source_type,source_url,status,parser_status) values(?,'json',?,'found','parsed')",
                    (merchant_id, "https://volcanowinery.com/wines"),
                ).lastrowid
                upsert_product(con, merchant_id, source_id, {
                    "source_key": "volcano-rose",
                    "source_url": "https://volcanowinery.com/wine/volcano-rose-750ml",
                    "raw_name": "Rose 750ml",
                    "raw_text": "Rose 750ml",
                    "wine_name": "Rose 750ml",
                    "price_value": 30,
                    "currency": "USD",
                    "price_text": "USD 30",
                })
                con.commit()
            finally:
                con.close()

            results = search_shop_products("Volcano Rose", limit=1, path=db_path)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["venue"]["name"], "Volcano Winery")

    def test_joined_transposed_name_matches_split_shop_product_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "shops.sqlite"
            ensure_shop_db(db_path)
            con = connect_shop(db_path)
            try:
                merchant_id = con.execute(
                    "insert into merchants(name,normalized_name,website_url,country,city,active,inventory_status) values(?,?,?,?,?,1,'found')",
                    ("Test Wines", "test wines", "https://wines.example", "FR", "Paris"),
                ).lastrowid
                source_id = con.execute(
                    "insert into merchant_sources(merchant_id,source_type,source_url,status,parser_status) values(?,'html',?,'found','parsed')",
                    (merchant_id, "https://wines.example/list"),
                ).lastrowid
                upsert_product(con, merchant_id, source_id, {
                    "source_key": "koji-jae-hwa",
                    "source_url": "https://wines.example/list",
                    "raw_name": "Domaine Koji et Jae Hwa Bourgogne Rouge",
                    "raw_text": "Domaine Koji et Jae Hwa Bourgogne Rouge EUR 100",
                    "price_value": 100,
                    "currency": "EUR",
                    "price_text": "EUR 100",
                })
                con.commit()
            finally:
                con.close()

            results = search_shop_products("koji jaewha", path=db_path)

        self.assertEqual(len(results), 1)
        self.assertIn("Jae Hwa", results[0]["text"])

    def test_hong_kong_filter_uses_iso_code_and_displays_country_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "shops.sqlite"
            ensure_shop_db(db_path)
            con = connect_shop(db_path)
            try:
                merchant_id = con.execute(
                    "insert into merchants(name,normalized_name,website_url,country,city,active,inventory_status) values(?,?,?,?,?,1,'found')",
                    ("Hong Kong Wines", "hong kong wines", "https://hk.example", "HK", "Hong Kong"),
                ).lastrowid
                source_id = con.execute(
                    "insert into merchant_sources(merchant_id,source_type,source_url,status,parser_status) values(?,'html',?,'found','parsed')",
                    (merchant_id, "https://hk.example/wines"),
                ).lastrowid
                upsert_product(con, merchant_id, source_id, {
                    "source_key": "rayas-2011",
                    "source_url": "https://hk.example/wines/rayas-2011",
                    "raw_name": "Chateau Rayas 2011",
                    "raw_text": "Chateau Rayas 2011 HK$12,888",
                    "wine_name": "Chateau Rayas",
                    "vintage": "2011",
                    "price_value": 12888,
                    "currency": "HKD",
                    "price_text": "HK$12,888",
                })
                con.commit()
            finally:
                con.close()

            hong_kong = search_shop_products("Rayas", country="Hong Kong", path=db_path)
            china = search_shop_products("Rayas", country="China", path=db_path)

            self.assertEqual(len(hong_kong), 1)
            self.assertEqual(hong_kong[0]["venue"]["country"], "Hong Kong")
            self.assertEqual(hong_kong[0]["venue"]["countryCode"], "HK")
            self.assertEqual(china, [])

    def test_existing_country_names_are_migrated_without_losing_original_value(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "shops.sqlite"
            ensure_shop_db(db_path)
            con = connect_shop(db_path)
            try:
                merchant_id = con.execute(
                    "insert into merchants(name,normalized_name,country,city,active) values(?,?,?,?,1)",
                    ("Legacy Shop", "legacy shop", "Hong Kong", "Hong Kong"),
                ).lastrowid
                con.commit()
            finally:
                con.close()

            wine_shop_db._INITIALIZED_PATHS.discard(str(db_path.resolve()))
            ensure_shop_db(db_path)
            con = connect_shop(db_path)
            try:
                row = con.execute(
                    "select country,country_raw from merchants where id=?", (merchant_id,)
                ).fetchone()
            finally:
                con.close()

            self.assertEqual(row["country"], "HK")
            self.assertEqual(row["country_raw"], "Hong Kong")


if __name__ == "__main__":
    unittest.main()
