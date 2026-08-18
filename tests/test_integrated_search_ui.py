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
        self.assertIn('sortHeader("Price", "krw")', APP_SCRIPT)
        self.assertIn('title="${escapeHtml(offer.label)}"', APP_SCRIPT)
        self.assertNotIn("sources.map(sourceBadge)", APP_SCRIPT)
        self.assertIn('label: "Star Wine"', APP_SCRIPT)
        self.assertIn('label: "Restaurant DB"', APP_SCRIPT)
        self.assertIn('label: "Wine Shop DB"', APP_SCRIPT)
        self.assertIn("groupOfferLines(group)", APP_SCRIPT)
        self.assertIn('`${resultSourceKind(result)}|${resultDedupKey(result)}`', APP_SCRIPT)
        self.assertIn('source: resultSourceLabel(line)', APP_SCRIPT)
        self.assertIn('"Source URL"', APP_SCRIPT)
        self.assertIn("Official website", APP_SCRIPT)

    def test_collapsed_price_offer_has_no_shop_source_background(self):
        styles = (ROOT / "public" / "styles.css").read_text(encoding="utf-8")
        self.assertNotIn(".price-offer.shop", styles)

    def test_search_maps_enable_mouse_zoom_controls(self):
        map_fix = (ROOT / "public" / "mapfix.js").read_text(encoding="utf-8")
        for script in (APP_SCRIPT, map_fix):
            self.assertIn("zoomControl: true", script)
            self.assertIn('gestureHandling: "greedy"', script)
            self.assertIn("scrollwheel: true", script)

    def test_database_map_enables_mouse_zoom_controls(self):
        dashboard_fix = (ROOT / "public" / "dashboardfix.js").read_text(encoding="utf-8")
        self.assertIn("zoomControl: true", dashboard_fix)
        self.assertIn('gestureHandling: "greedy"', dashboard_fix)
        self.assertIn("scrollwheel: true", dashboard_fix)

    def test_collapsed_rows_show_compact_source_marks(self):
        self.assertIn('short: "S", label: "Star Wine"', APP_SCRIPT)
        self.assertIn('short: "R", label: "Restaurant DB"', APP_SCRIPT)
        self.assertIn('short: "W", label: "Wine Shop DB"', APP_SCRIPT)
        self.assertIn("sourceLegendMarkup()", APP_SCRIPT)
        self.assertIn("groupSourceMarks(group)", APP_SCRIPT)
        self.assertIn("if (!candidates.length) return [];", APP_SCRIPT)

    def test_review_cross_is_removed_from_venue_name(self):
        self.assertIn("stripVenueReviewPrefix", APP_SCRIPT)
        self.assertIn("nameNeedsReview", APP_SCRIPT)
        self.assertIn("venueReviewBadge(group)", APP_SCRIPT)

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

    def test_collected_shop_uses_one_canonical_wine_list_button(self):
        self.assertIn("result.venue?.inventoryUrl", APP_SCRIPT)
        self.assertIn("const collectedListUrl = collectedResults", APP_SCRIPT)
        self.assertNotIn("collectedListUrls.slice(0, 3)", APP_SCRIPT)


if __name__ == "__main__":
    unittest.main()
