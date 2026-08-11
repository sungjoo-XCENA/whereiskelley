import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import app
from publish_guide_snapshot import publish_guide_snapshot


SCHEMA = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")


def create_db(path):
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    con.commit()
    return con


def insert_guide_row(
    con,
    url,
    status="found",
    raw_text="2021 Romanee Conti Grand Cru",
    country="Korea",
    price_text=None,
    price_value=None,
    currency=None,
):
    con.execute(
        """
        insert into restaurant_targets
          (id, normalized_key, name, country, city, address, lat, lng, website_url)
        values (1, 'test|seoul|korea', 'Test Restaurant', ?, 'Seoul',
                '1 Test Road', 37.5, 127.0, 'https://restaurant.example')
        """,
        (country,),
    )
    con.execute(
        """
        insert into wine_list_sources
          (id, target_id, url, source_type, status, last_checked_at, line_count)
        values (1, 1, ?, 'html', ?, '2026-08-07T00:00:00+00:00', 1)
        """,
        (url, status),
    )
    con.execute(
        """
        insert into guide_wine_entries
          (id, target_id, wine_list_source_id, raw_text, vintage,
           price_text, price_value, currency, source_url)
        values (1, 1, 1, ?, '2021', ?, ?, ?, ?)
        """,
        (raw_text, price_text, price_value, currency, url),
    )
    con.commit()


def insert_star_wine_row(
    con,
    raw_text="2020 Romanee Conti Grand Cru 1200",
    country="France",
    city="Paris",
    price_text="1200",
    price_value=1200,
    currency="EUR",
):
    con.execute(
        "insert into countries(id, slug, name) values (1, 'country', ?)",
        (country,),
    )
    con.execute(
        """
        insert into venues(id, slug, name, type, country_id, city, venue_url)
        values (1, 'star-restaurant', 'Star Restaurant', 'Restaurant', 1, ?,
                'https://starwinelist.com/wine-place/star-restaurant')
        """,
        (city,),
    )
    con.execute(
        """
        insert into wine_lists(id, venue_id, starwine_list_id, label, download_url)
        values (1, 1, 'star-list-1', 'Wine list', 'https://starwinelist.com/list.pdf')
        """
    )
    con.execute(
        """
        insert into wine_entries(
          id, wine_list_id, venue_id, raw_text, vintage, price_text, price_value, currency
        ) values (1, 1, 1, ?, '2020', ?, ?, ?)
        """,
        (raw_text, price_text, price_value, currency),
    )
    con.commit()


class CollectedSearchTests(unittest.TestCase):
    def test_filters_split_greater_china_into_user_facing_countries(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "search.sqlite"
            con = create_db(db_path)
            con.execute(
                "insert into countries(id, slug, name) values (1, 'greater-china', 'Greater China')"
            )
            con.execute(
                "insert into countries(id, slug, name) values (2, 'taiwan', 'Taiwan')"
            )
            con.commit()
            con.close()
            previous_path = app.DB_PATH
            app.DB_PATH = db_path
            try:
                payload = app.filters()
            finally:
                app.DB_PATH = previous_path

        self.assertNotIn("Greater China", payload["countries"])
        self.assertTrue({"China", "Hong Kong", "Macau", "Taiwan"}.issubset(payload["countries"]))

    def test_greater_china_rows_are_filtered_by_display_country(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "search.sqlite"
            con = create_db(db_path)
            insert_star_wine_row(con, country="Greater China", city="Hong Kong")
            con.close()
            previous_path = app.DB_PATH
            app.DB_PATH = db_path
            try:
                hong_kong = app.search(
                    {"q": ["Romanee Conti"], "country": ["Hong Kong"], "limit": ["100"]}
                )
                china = app.search(
                    {"q": ["Romanee Conti"], "country": ["China"], "limit": ["100"]}
                )
            finally:
                app.DB_PATH = previous_path

        self.assertEqual(hong_kong["count"], 1)
        self.assertEqual(hong_kong["results"][0]["venue"]["country"], "Hong Kong")
        self.assertEqual(china["count"], 0)

    def test_live_source_ids_still_require_every_query_token(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "search.sqlite"
            con = create_db(db_path)
            insert_star_wine_row(
                con,
                raw_text="2019 Jules Desjourneys Pouilly Loche 980",
                country="Greater China",
                city="Hong Kong",
            )
            con.execute("update wine_entries set source_item_id='loose-result'")
            con.commit()
            con.close()
            previous_path = app.DB_PATH
            app.DB_PATH = db_path
            try:
                with patch.object(
                    app,
                    "refresh_from_search_api",
                    return_value={"sourceItemIds": ["loose-result"]},
                ):
                    payload = app.search(
                        {
                            "q": ["Jules Brochet"],
                            "country": ["Hong Kong"],
                            "live": ["1"],
                            "limit": ["100"],
                        }
                    )
            finally:
                app.DB_PATH = previous_path

        self.assertEqual(payload["count"], 0)

    def test_country_filter_uses_greater_china_only_for_star_wine_region(self):
        self.assertEqual(app.starwine_region_for_country("China"), "greater-china")
        self.assertEqual(app.starwine_region_for_country("Hong Kong"), "greater-china")
        self.assertEqual(app.starwine_region_for_country("Macau"), "greater-china")
        self.assertEqual(app.starwine_region_for_country("Taiwan"), "taiwan")

    def test_collected_result_is_availability_only_and_uses_exact_list_url(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "search.sqlite"
            con = create_db(db_path)
            insert_guide_row(con, "https://restaurant.example/wine-list")
            con.close()
            previous_path = app.DB_PATH
            app.DB_PATH = db_path
            try:
                results = app.search_collected_guides("Romanée-Conti", vintage="2021")
            finally:
                app.DB_PATH = previous_path

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["availabilityOnly"])
        self.assertIsNone(results[0]["priceValue"])
        self.assertEqual(results[0]["source"], "Database")
        self.assertEqual(results[0]["wineList"]["downloadUrl"], "https://restaurant.example/wine-list")

    def test_review_source_is_not_returned_as_collected_match(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "search.sqlite"
            con = create_db(db_path)
            insert_guide_row(con, "https://restaurant.example/candidate", status="review")
            con.close()
            previous_path = app.DB_PATH
            app.DB_PATH = db_path
            try:
                results = app.search_collected_guides("Romanee Conti")
            finally:
                app.DB_PATH = previous_path
        self.assertEqual(results, [])

    def test_search_combines_star_wine_and_database_results(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "search.sqlite"
            con = create_db(db_path)
            insert_star_wine_row(con)
            insert_guide_row(con, "https://restaurant.example/wine-list")
            con.close()
            previous_path = app.DB_PATH
            app.DB_PATH = db_path
            try:
                payload = app.search({"q": ["Romanee Conti"], "limit": ["100"]})
            finally:
                app.DB_PATH = previous_path

        self.assertEqual(payload["count"], 2)
        self.assertEqual({result["source"] for result in payload["results"]}, {"Star Wine", "Database"})
        database_result = next(result for result in payload["results"] if result["source"] == "Database")
        self.assertTrue(database_result["availabilityOnly"])
        self.assertIsNone(database_result["priceValue"])

    def test_star_wine_price_uses_country_currency_when_currency_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "search.sqlite"
            con = create_db(db_path)
            insert_star_wine_row(
                con,
                raw_text="2011 Chateauneuf du Pape Rouge Pignan Rayas France 170,000",
                country="Japan",
                city="Tokyo",
                price_text="170,000",
                price_value=170000,
                currency="",
            )
            con.close()
            previous_path = app.DB_PATH
            app.DB_PATH = db_path
            try:
                payload = app.search({"q": ["Rayas"], "country": ["Japan"], "limit": ["100"]})
            finally:
                app.DB_PATH = previous_path

        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["results"][0]["priceValue"], 170000)
        self.assertEqual(payload["results"][0]["currency"], "JPY")

    def test_english_country_filter_matches_localized_guide_country(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "search.sqlite"
            con = create_db(db_path)
            insert_guide_row(
                con,
                "https://restaurant.example/hyakuyaku-wine-list.pdf",
                raw_text=(
                    "2011 Chateauneuf du Pape Rouge Pignan Rayas France 170,000"
                ),
                country="일본",
                price_text="170,000",
                price_value=170000,
            )
            con.close()
            previous_path = app.DB_PATH
            app.DB_PATH = db_path
            try:
                results = app.search_collected_guides("Rayas", country="Japan")
            finally:
                app.DB_PATH = previous_path

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["venue"]["country"], "Japan")
        self.assertIn("Pignan Rayas", results[0]["text"])
        self.assertEqual(results[0]["priceValue"], 170000)
        self.assertEqual(results[0]["currency"], "JPY")
        self.assertEqual(results[0]["prices"], ["170,000"])

    def test_country_filter_still_excludes_other_countries(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "search.sqlite"
            con = create_db(db_path)
            insert_guide_row(
                con,
                "https://restaurant.example/france-wine-list.pdf",
                raw_text="2011 Chateauneuf du Pape Rouge Pignan Rayas 170,000",
                country="프랑스",
            )
            con.close()
            previous_path = app.DB_PATH
            app.DB_PATH = db_path
            try:
                results = app.search_collected_guides("Rayas", country="Japan")
            finally:
                app.DB_PATH = previous_path

        self.assertEqual(results, [])


class PublishSnapshotTests(unittest.TestCase):
    def test_publish_replaces_only_guide_collection_tables(self):
        with tempfile.TemporaryDirectory() as directory:
            live_path = Path(directory) / "live.sqlite"
            stage_path = Path(directory) / "stage.sqlite"
            live = create_db(live_path)
            live.execute("insert into countries(id, slug, name) values (1, 'keep', 'Keep Me')")
            insert_guide_row(live, "https://restaurant.example/old-list")
            live.close()

            stage = create_db(stage_path)
            insert_guide_row(
                stage,
                "https://restaurant.example/new-list",
                raw_text="2019 Krug Grande Cuvee Champagne",
            )
            stage.close()

            publish_guide_snapshot(stage_path, live_path)
            con = sqlite3.connect(live_path)
            try:
                self.assertEqual(con.execute("select name from countries").fetchone()[0], "Keep Me")
                self.assertEqual(
                    con.execute("select url from wine_list_sources").fetchone()[0],
                    "https://restaurant.example/new-list",
                )
                self.assertEqual(
                    con.execute("select raw_text from guide_wine_entries").fetchone()[0],
                    "2019 Krug Grande Cuvee Champagne",
                )
            finally:
                con.close()


if __name__ == "__main__":
    unittest.main()
