import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_SCRIPT = (ROOT / "public" / "app.js").read_text(encoding="utf-8")


class IntegratedSearchUiTests(unittest.TestCase):
    def test_search_uses_one_integrated_endpoint(self):
        run_search = APP_SCRIPT.split("async function runSearch()", 1)[1].split(
            'form.addEventListener("submit"', 1
        )[0]
        self.assertIn("getJson(`/api/search_v2?${params.toString()}`)", run_search)
        self.assertNotIn("Promise.allSettled", run_search)
        self.assertNotIn("searchSnapshot", run_search)
        self.assertNotIn("/api/search?", run_search)
        index = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("snapshot-search.js", index)

    def test_database_matches_are_availability_results(self):
        self.assertIn("Database wine-list matches", APP_SCRIPT)
        self.assertIn("Matched text only. Database prices are not estimated.", APP_SCRIPT)
        self.assertIn('label = key === "both" ? "Star Wine + Database"', APP_SCRIPT)


if __name__ == "__main__":
    unittest.main()
