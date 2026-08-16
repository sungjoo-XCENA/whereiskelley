import tempfile
import unittest
from pathlib import Path

from wine_shop_db import (
    connect_shop,
    ensure_shop_db,
    search_shop_products,
    shop_collection_status,
    upsert_product,
    utc_now,
)


class WineShopDatabaseTests(unittest.TestCase):
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
                        "Switzerland", "Geneva", "Geneva, Switzerland", 46.2044, 6.1432, utc_now(),
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


if __name__ == "__main__":
    unittest.main()
