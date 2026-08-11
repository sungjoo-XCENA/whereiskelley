import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


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
          (id, target_id, wine_list_source_id, raw_text, vintage, source_url)
        values (1, 1, 1, ?, '2021', ?)
        """,
        (raw_text, url),
    )
    con.commit()


def insert_star_wine_row(con, raw_text="2020 Romanee Conti Grand Cru 1200"):
    con.execute("insert into countries(id, slug, name) values (1, 'france', 'France')")
    con.execute(
        """
        insert into venues(id, slug, name, type, country_id, city, venue_url)
        values (1, 'star-restaurant', 'Star Restaurant', 'Restaurant', 1, 'Paris',
                'https://starwinelist.com/wine-place/star-restaurant')
        """
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
        ) values (1, 1, 1, ?, '2020', '1200', 1200, 'EUR')
        """,
        (raw_text,),
    )
    con.commit()


class CollectedSearchTests(unittest.TestCase):
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
