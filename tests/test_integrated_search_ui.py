import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_SCRIPT = (ROOT / "public" / "app.js").read_text(encoding="utf-8")


class IntegratedSearchUiTests(unittest.TestCase):
    def test_search_uses_one_integrated_endpoint(self):
        run_search = APP_SCRIPT.split("async function runSearch()", 1)[1].split(
            'form.addEventListener("submit"', 1
        )[0]
        self.assertIn("getJson(`/api/search_v2?${params.toString()}`", run_search)
        self.assertNotIn("Promise.allSettled", run_search)
        self.assertNotIn("searchSnapshot", run_search)
        self.assertNotIn("/api/search?", run_search)
        index = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("snapshot-search.js", index)

    def test_database_matches_are_availability_results(self):
        self.assertIn("Prices are kept as separate offers by source.", APP_SCRIPT)
        self.assertIn('Japan: "JPY"', APP_SCRIPT)
        self.assertIn("krwPriceText(result)", APP_SCRIPT)
        self.assertIn('label = key === "both" ? "Star Wine + Database"', APP_SCRIPT)

    def test_same_restaurant_is_grouped_but_source_prices_stay_separate(self):
        self.assertIn('return `${name}|${city}|${country}`', APP_SCRIPT)
        self.assertIn('sortHeader("Price offers", "krw")', APP_SCRIPT)
        self.assertIn('label: "Star Wine"', APP_SCRIPT)
        self.assertIn('label: "Database"', APP_SCRIPT)
        self.assertIn("groupOfferLines(group)", APP_SCRIPT)
        self.assertIn('`${resultSourceKind(result)}|${resultDedupKey(result)}`', APP_SCRIPT)
        self.assertIn('source: resultSourceLabel(line)', APP_SCRIPT)
        self.assertIn('"Source URL"', APP_SCRIPT)
        self.assertIn("Official website", APP_SCRIPT)

    def test_server_html_is_not_rendered_as_search_error(self):
        get_json = APP_SCRIPT.split("async function getJson(", 1)[1].split(
            "async function getOptionalJson", 1
        )[0]
        self.assertNotIn("throw new Error(await response.text())", get_json)
        self.assertIn("response.status === 504", get_json)
        self.assertIn("invalid response", get_json)

    def test_running_search_can_be_stopped_and_restarted(self):
        self.assertIn("new AbortController()", APP_SCRIPT)
        self.assertIn("stopActiveSearch()", APP_SCRIPT)
        self.assertIn('submitButton.textContent = searching ? "Stop" : "Search"', APP_SCRIPT)
        self.assertIn("signal: controller.signal", APP_SCRIPT)
        self.assertIn('if (error.name === "AbortError") return', APP_SCRIPT)
        self.assertNotIn("submitButton.disabled = true", APP_SCRIPT)


if __name__ == "__main__":
    unittest.main()
