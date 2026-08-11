import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import app


class LiveSearchRefreshTests(unittest.TestCase):
    def setUp(self):
        app.SEARCH_REFRESH_CACHE.clear()

    def test_region_and_all_pages_are_fetched_in_parallel(self):
        active = 0
        max_active = 0
        active_lock = threading.Lock()

        def fetch_page(page, query, region):
            nonlocal active, max_active
            self.assertEqual(query, "Rayas")
            self.assertEqual(region, "japan")
            with active_lock:
                active += 1
                max_active = max(max_active, active)
            if page > 1:
                time.sleep(0.03)
            with active_lock:
                active -= 1
            return {
                "meta": {"last_page": 4},
                "data": [
                    {"item_type": "wine_list_line", "item_id": f"line-{page}"}
                ],
            }

        connection = MagicMock()
        context = MagicMock()
        context.__enter__.return_value = connection
        context.__exit__.return_value = False

        with (
            patch.object(app.sync_search_api, "init_db"),
            patch.object(app.sync_search_api, "fetch_search_page", side_effect=fetch_page) as fetch,
            patch.object(app.sync_search_api, "prefetch_payload_locations"),
            patch.object(app.sync_search_api, "connect", return_value=context),
            patch.object(app.sync_search_api, "persist_search_payload", return_value=(1, 0)),
        ):
            result = app.refresh_from_search_api("Rayas", "all", 0, 200, "japan")

        self.assertEqual(fetch.call_count, 4)
        self.assertGreater(max_active, 1)
        self.assertEqual(result["region"], "japan")
        self.assertEqual(result["pages"], 4)
        self.assertEqual(result["entries"], 4)
        self.assertTrue(result["complete"])


if __name__ == "__main__":
    unittest.main()
