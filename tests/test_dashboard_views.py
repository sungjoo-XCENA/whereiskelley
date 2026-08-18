import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_SCRIPT = ROOT / "public" / "dashboardfix.js"


class DashboardViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = DASHBOARD_SCRIPT.read_text(encoding="utf-8")

    def test_navigation_has_three_clear_views(self):
        self.assertIn('["search", "Wine Search"]', self.script)
        self.assertIn('["database", "Database Map"]', self.script)
        self.assertIn('["collection", "Collection"]', self.script)
        self.assertNotIn('["dashboard", "Dashboard"]', self.script)

    def test_database_owns_map_and_collection_owns_resources(self):
        database = self.script.split("function renderDatabase()", 1)[1].split(
            "function renderCollection()", 1
        )[0]
        collection = self.script.split("function renderCollection()", 1)[1].split(
            "function renderActiveGuideView()", 1
        )[0]

        self.assertIn('id="dashboardDbMap"', database)
        self.assertNotIn("database-summary", database)
        self.assertNotIn("db-health-grid", database)
        self.assertNotIn("resourcePanelMarkup", database)
        self.assertIn("resourcePanelMarkup", collection)
        self.assertNotIn('id="dashboardDbMap"', collection)

    def test_database_map_only_updates_while_database_view_is_active(self):
        self.assertIn('state.activeView !== "database"', self.script)
        self.assertNotIn('state.activeView !== "dashboard"', self.script)

    def test_selected_restaurant_has_one_clear_world_map_action(self):
        self.assertIn("Back to world map", self.script)
        self.assertIn("World view", self.script)
        self.assertIn("database-world-reset", self.script)
        self.assertNotIn("data-world-view-control", self.script)
        self.assertNotIn("function syncWorldViewControls()", self.script)
        self.assertNotIn(">Close</button>", self.script)

    def test_collection_auto_refreshes_with_compact_payloads(self):
        self.assertIn("COLLECTION_REFRESH_MS = 5000", self.script)
        self.assertIn("syncCollectionAutoRefresh()", self.script)
        self.assertIn('const suffix = compact ? "?compact=1" : ""', self.script)
        self.assertIn("Auto refresh", self.script)

    def test_database_mode_uses_compact_colored_keys(self):
        self.assertIn('class="database-mode-key">R</span>', self.script)
        self.assertIn('class="database-mode-key">W</span>', self.script)
        self.assertIn("button.restaurant.active", self.script)
        self.assertIn("button.shop.active", self.script)

    def test_database_map_can_filter_verified_places_by_wine_count(self):
        self.assertIn('databaseMapFilter: "all"', self.script)
        self.assertIn('data-database-map-filter="all"', self.script)
        self.assertIn('data-database-map-filter="found"', self.script)
        self.assertIn('data-database-map-filter="100"', self.script)
        self.assertIn('data-database-map-filter="200"', self.script)
        self.assertIn('targetKind(target) !== "found"', self.script)
        self.assertIn('targetWineCount(target) >= 100', self.script)
        self.assertIn('targetWineCount(target) >= 200', self.script)

    def test_all_statuses_map_does_not_require_a_website(self):
        visible_targets = self.script.split("function visibleMapTargets(payload)", 1)[1].split(
            "function targetWineCount", 1
        )[0]
        self.assertNotIn("websiteUrl", visible_targets)

    def test_database_world_map_wraps_horizontally(self):
        self.assertNotIn("strictBounds", self.script)
        self.assertIn("DASHBOARD_WORLD_CENTER = { lat: 25, lng: 8 }", self.script)
        self.assertIn("DASHBOARD_WORLD_ZOOM = 2", self.script)
        self.assertIn("showDashboardWorldView()", self.script)
        self.assertNotIn("state.dashboardMap.fitBounds", self.script)

    def test_database_map_matches_search_map_frame(self):
        self.assertIn("width: 100%;\n      height: 430px;", self.script)

    def test_database_mode_fetches_missing_map_payload(self):
        self.assertIn("function hasActiveDatabaseMapData()", self.script)
        self.assertIn("!hasActiveDatabaseMapData()", self.script)

    def test_resource_panel_hides_internal_sample_interval(self):
        self.assertNotIn("samples / every", self.script)

    def test_resource_chart_uses_latest_250_five_second_samples(self):
        self.assertIn("samples.length <= 250", self.script)
        self.assertIn("Array.from({ length: 250 }", self.script)

    def test_collection_shows_worker_and_resource_limits(self):
        self.assertIn("workerConfig", self.script)
        self.assertIn("resourceGovernor", self.script)
        self.assertIn("Safety limits", self.script)
        self.assertIn("Controller", self.script)

    def test_restaurant_collection_shows_real_pipeline_steps(self):
        self.assertIn('aria-label="Restaurant collection pipeline"', self.script)
        self.assertIn("Maintain restaurant directory", self.script)
        self.assertIn("Prepare safe scan database", self.script)
        self.assertIn("Crawl and verify wine lists", self.script)
        self.assertIn("Publish completed database", self.script)

    def test_completed_inventory_supersedes_old_stale_progress(self):
        self.assertIn("progressSuperseded", self.script)
        self.assertIn("latestFinishTime > progressTime", self.script)


if __name__ == "__main__":
    unittest.main()
