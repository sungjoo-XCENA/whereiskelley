import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import guide_discover_wine_lists as discover


class ParallelCollectionTests(unittest.TestCase):
    def test_saved_targets_run_concurrently_with_worker_limit(self):
        state = {"active": 0, "peak": 0}
        lock = threading.Lock()

        def fake_collect(target, _watches, _max_links, _replace_existing):
            with lock:
                state["active"] += 1
                state["peak"] = max(state["peak"], state["active"])
            time.sleep(0.03)
            with lock:
                state["active"] -= 1
            return {
                "target": target,
                "sources": 1,
                "lines": 2,
                "error": "",
                "failed": False,
            }

        rows = [
            {"id": index, "name": f"Restaurant {index}", "website_url": f"https://{index}.example"}
            for index in range(24)
        ]
        with mock.patch.object(discover, "collect_saved_target", side_effect=fake_collect), mock.patch.object(
            discover, "write_live_progress"
        ):
            result = discover.collect_saved_targets_parallel(
                object(), rows, [], 60, True, 12, 1, "2026-08-07 00:00:00", 24
            )

        self.assertEqual(result, (24, 24, 48, 0))
        self.assertGreaterEqual(state["peak"], 8)
        self.assertLessEqual(state["peak"], 12)


if __name__ == "__main__":
    unittest.main()
