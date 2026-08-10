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
    def test_discovery_finishes_before_deferred_pdf_extraction(self):
        state = {"active": 0, "peak": 0, "discovered": 0, "html_scanned": 0, "pdf_started_after_html": False}
        lock = threading.Lock()

        def fake_discover(target, _max_links):
            with lock:
                state["active"] += 1
                state["peak"] = max(state["peak"], state["active"])
            time.sleep(0.03)
            with lock:
                state["active"] -= 1
                state["discovered"] += 1
            return {
                "target": target,
                "candidates": [
                    {"url": f"https://{target['id']}.example/list.{'pdf' if target['id'] % 2 else 'html'}", "score": 100}
                ],
                "crawl_limit_reached": False,
                "error": "",
                "failed": False,
            }

        def fake_scan(target, link, _watches):
            with lock:
                self.assertEqual(state["discovered"], 24)
                if link["url"].endswith(".pdf"):
                    state["pdf_started_after_html"] = state["html_scanned"] == 12
                else:
                    state["html_scanned"] += 1
            return {
                "target": target,
                "link": link,
                "sources": 1,
                "lines": 2,
                "error": "",
                "needs_review": False,
            }

        rows = [
            {"id": index, "name": f"Restaurant {index}", "website_url": f"https://{index}.example"}
            for index in range(24)
        ]
        con = mock.MagicMock()
        with mock.patch.object(discover, "discover_saved_target", side_effect=fake_discover), mock.patch.object(
            discover, "scan_saved_source", side_effect=fake_scan
        ), mock.patch.object(discover, "write_live_progress"):
            result = discover.collect_saved_targets_parallel(
                con, rows, [], 60, True, 12, 6, 3, 1, "2026-08-07 00:00:00", 24
            )

        self.assertEqual(result, (24, 24, 48, 0))
        self.assertGreaterEqual(state["peak"], 8)
        self.assertLessEqual(state["peak"], 12)
        self.assertTrue(state["pdf_started_after_html"])

    def test_phase_eta_uses_recent_phase_throughput(self):
        with mock.patch.object(discover.time, "time", return_value=200.0):
            payload = discover.phase_timing_payload(
                100.0,
                completed=50,
                total=100,
                samples=[(180.0, 30), (200.0, 50)],
            )

        self.assertEqual(payload["phaseProcessed"], 50)
        self.assertEqual(payload["phaseTotal"], 100)
        self.assertEqual(payload["phaseEstimatedRemainingSeconds"], 50)
        self.assertEqual(payload["phaseThroughputPerMinute"], 60.0)


if __name__ == "__main__":
    unittest.main()
