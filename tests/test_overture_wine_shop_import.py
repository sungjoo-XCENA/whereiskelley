import importlib.util
import queue
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "collect_overture_wine_shops.py"
SPEC = importlib.util.spec_from_file_location("overture_wine_shops", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class OvertureWineShopImportTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "shops.sqlite"
        MODULE.ensure_shop_db(self.db_path)

    def tearDown(self):
        self.tempdir.cleanup()

    def candidate(self, place_id="place-1", name="Kelley Fine Wines"):
        candidate = {
            "provider_place_id": place_id,
            "name": name,
            "candidate_reason": "retail_category",
            "primary_category": "wine_shop",
            "categories": {"primary": "wine_shop"},
            "taxonomy": {},
            "confidence": 0.95,
            "operating_status": "open",
            "country_code": "FR",
            "region": "Ile-de-France",
            "city": "Paris",
            "postcode": "75001",
            "address": "1 Rue du Vin",
            "latitude": 48.86,
            "longitude": 2.34,
            "websites": ["https://example.test/shop"],
            "phones": ["+33100000000"],
            "socials": [],
            "source_updated_at": "2026-08-01",
        }
        candidate["raw_hash"] = MODULE.stable_hash(candidate)
        return candidate

    def test_upsert_keeps_discovery_separate_from_verified_inventory(self):
        con = MODULE.connect_shop(self.db_path)
        try:
            run_id = con.execute(
                "insert into merchant_discovery_runs(provider,status) values('overture','running')"
            ).lastrowid
            outcome = MODULE.upsert_candidate(con, self.candidate(), run_id, "2026-07-22.0")
            con.commit()

            merchant = con.execute(
                "select inventory_status, website_url from merchants"
            ).fetchone()
            place_source = con.execute(
                "select provider, provider_release, active from merchant_place_sources"
            ).fetchone()
            inventory_sources = con.execute("select count(*) from merchant_sources").fetchone()[0]

            self.assertEqual("inserted", outcome)
            self.assertEqual("pending", merchant["inventory_status"])
            self.assertEqual("https://example.test/shop", merchant["website_url"])
            self.assertEqual(("overture", "2026-07-22.0", 1), tuple(place_source))
            self.assertEqual(0, inventory_sources)
        finally:
            con.close()

    def test_reimport_updates_same_place_instead_of_duplicating_it(self):
        con = MODULE.connect_shop(self.db_path)
        try:
            first_run = con.execute(
                "insert into merchant_discovery_runs(provider,status) values('overture','running')"
            ).lastrowid
            first = self.candidate()
            MODULE.upsert_candidate(con, first, first_run, "2026-07-22.0")
            second_run = con.execute(
                "insert into merchant_discovery_runs(provider,status) values('overture','running')"
            ).lastrowid
            second = self.candidate()
            second["city"] = "Lyon"
            second["raw_hash"] = MODULE.stable_hash(second)
            outcome = MODULE.upsert_candidate(con, second, second_run, "2026-08-19.0")
            con.commit()

            self.assertEqual("updated", outcome)
            self.assertEqual(1, con.execute("select count(*) from merchants").fetchone()[0])
            self.assertEqual(1, con.execute("select count(*) from merchant_place_sources").fetchone()[0])
            row = con.execute(
                "select provider_release, city, last_seen_run_id from merchant_place_sources"
            ).fetchone()
            self.assertEqual(("2026-08-19.0", "Lyon", second_run), tuple(row))
        finally:
            con.close()

    def test_name_only_restaurant_is_not_a_shop_candidate(self):
        row = {
            "id": "restaurant-1",
            "name": "Wine Garden Restaurant",
            "old_primary": "restaurant",
            "categories_json": "[]",
            "basic_category": "restaurant",
            "taxonomy_primary": "restaurant",
            "taxonomy_json": "{}",
        }
        self.assertIsNone(MODULE.candidate_from_row(row))

    def test_cached_reimport_uses_fast_unchanged_path(self):
        con = MODULE.connect_shop(self.db_path)
        try:
            first_run = con.execute(
                "insert into merchant_discovery_runs(provider,status) values('overture','running')"
            ).lastrowid
            candidate = self.candidate()
            MODULE.upsert_candidate(con, candidate, first_run, "2026-07-22.0")
            con.commit()

            second_run = con.execute(
                "insert into merchant_discovery_runs(provider,status) values('overture','running')"
            ).lastrowid
            state = MODULE.load_import_state(con)
            statements = []
            con.set_trace_callback(statements.append)
            outcome = MODULE.upsert_candidate(
                con, candidate, second_run, "2026-08-19.0", state=state
            )
            con.set_trace_callback(None)
            con.commit()

            self.assertEqual("unchanged", outcome)
            self.assertFalse(any("select id, merchant_id, raw_hash" in sql.lower() for sql in statements))
            self.assertEqual(
                second_run,
                con.execute(
                    "select last_seen_run_id from merchant_place_sources where provider_place_id='place-1'"
                ).fetchone()[0],
            )
            self.assertEqual(1, con.execute("select active from merchant_websites").fetchone()[0])
        finally:
            con.close()

    def test_import_indexes_cover_name_matching(self):
        con = MODULE.connect_shop(self.db_path)
        try:
            indexes = {
                row[1] for row in con.execute("pragma index_list('merchants')").fetchall()
            }
            self.assertIn("idx_merchants_name_domain", indexes)
            self.assertIn("idx_merchants_name_location", indexes)
        finally:
            con.close()

    def test_batch_reimport_collapses_unchanged_rows(self):
        con = MODULE.connect_shop(self.db_path)
        try:
            first_run = con.execute(
                "insert into merchant_discovery_runs(provider,status) values('overture','running')"
            ).lastrowid
            candidates = [
                self.candidate("place-1", "Kelley Fine Wines"),
                self.candidate("place-2", "Kelley Cellars"),
            ]
            state = MODULE.load_import_state(con)
            first = MODULE.upsert_candidate_batch(
                con, candidates, first_run, "2026-07-22.0", state=state
            )
            con.commit()
            self.assertEqual(2, first["inserted"])

            second_run = con.execute(
                "insert into merchant_discovery_runs(provider,status) values('overture','running')"
            ).lastrowid
            state = MODULE.load_import_state(con)
            statements = []
            con.set_trace_callback(statements.append)
            second = MODULE.upsert_candidate_batch(
                con, candidates, second_run, "2026-08-19.0", state=state
            )
            con.set_trace_callback(None)
            con.commit()

            self.assertEqual(2, second["unchanged"])
            merchant_updates = [
                sql
                for sql in statements
                if " ".join(sql.lower().split()).startswith("update merchants set")
            ]
            self.assertEqual(1, len(merchant_updates))
            self.assertEqual(
                2,
                con.execute(
                    "select count(*) from merchant_place_sources where last_seen_run_id=?",
                    (second_run,),
                ).fetchone()[0],
            )
        finally:
            con.close()

    def test_parquet_reader_uses_configured_duckdb_threads(self):
        class EmptyResult:
            description = [("id",)]

            def fetchmany(self, _size):
                return []

        class FakeConnection:
            def execute(self, _query):
                return EmptyResult()

            def close(self):
                pass

        class FakeDuckDB:
            @staticmethod
            def connect():
                return FakeConnection()

        output = queue.Queue()
        stop_event = threading.Event()
        with mock.patch.object(MODULE, "configure_duck") as configure:
            MODULE.read_overture_file(
                FakeDuckDB,
                "source.parquet",
                {"id"},
                "",
                "",
                5000,
                output,
                stop_event,
                "1152MB",
                4,
            )

        configure.assert_called_once_with(
            mock.ANY,
            threads=4,
            memory_limit="1152MB",
        )
        self.assertEqual(("done", "source.parquet", None, None), output.get_nowait())


if __name__ == "__main__":
    unittest.main()
