import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_SCRIPT = ROOT / "public" / "dashboardfix.js"


class DashboardViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = DASHBOARD_SCRIPT.read_text(encoding="utf-8")

    def test_navigation_has_three_clear_views(self):
        self.assertIn('["search", "Star Wine Search"]', self.script)
        self.assertIn('["database", "Database"]', self.script)
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
        self.assertNotIn("resourcePanelMarkup", database)
        self.assertIn("resourcePanelMarkup", collection)
        self.assertNotIn('id="dashboardDbMap"', collection)

    def test_database_map_only_updates_while_database_view_is_active(self):
        self.assertIn('state.activeView !== "database"', self.script)
        self.assertNotIn('state.activeView !== "dashboard"', self.script)


if __name__ == "__main__":
    unittest.main()
