import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import guide_discover_wine_lists as discover
import resource_governor


class ParallelCollectionTests(unittest.TestCase):
    def test_discovery_and_source_validation_overlap(self):
        state = {"active": 0, "peak": 0, "discovered": 0, "source_started_before_discovery_done": False}
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
                state["source_started_before_discovery_done"] = (
                    state["source_started_before_discovery_done"] or state["discovered"] < 24
                )
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
        with mock.patch.object(discover, "ProcessPoolExecutor", discover.ThreadPoolExecutor), mock.patch.object(
            discover, "discover_saved_target", side_effect=fake_discover
        ), mock.patch.object(
            discover, "scan_saved_source", side_effect=fake_scan
        ), mock.patch.object(discover, "write_live_progress"):
            result = discover.collect_saved_targets_parallel(
                con, rows, [], 60, True, 12, 6, 3, 1, "2026-08-07 00:00:00", 24
            )

        self.assertEqual(result, (24, 24, 48, 0))
        self.assertGreaterEqual(state["peak"], 4)
        self.assertLessEqual(state["peak"], 12)
        self.assertTrue(state["source_started_before_discovery_done"])

    def test_bounded_futures_never_queues_the_whole_collection(self):
        state = {"peak": 0}
        governor = mock.Mock()
        governor.wait_for_capacity.return_value = {}
        governor.capacity_available.return_value = True
        governor.pending_limit.side_effect = lambda workers: workers * 2

        def submit(pool, item):
            future = pool.submit(lambda value: value, item)
            state["peak"] = max(state["peak"], 1)
            return future

        with discover.ThreadPoolExecutor(max_workers=4) as executor:
            results = list(resource_governor.bounded_futures(
                executor, range(100), submit, 4, governor
            ))

        self.assertEqual(len(results), 100)
        self.assertGreater(governor.pending_limit.call_count, 1)

    def test_resource_governor_reduces_concurrency_at_cpu_target(self):
        governor = resource_governor.AdaptiveResourceGovernor(sample_seconds=60, control_seconds=60)
        governor.snapshot.update(cpuPercent=82, memoryPercent=40, networkPressurePercent=0)
        governor.last_sample_at = time.monotonic()
        governor.last_control_at = time.monotonic()
        governor.dispatch_fraction = 1.0
        self.assertEqual(governor.pending_limit(100), 80)
        governor.snapshot["cpuPercent"] = 92
        self.assertEqual(governor.pending_limit(100), 50)

    def test_resource_governor_increases_concurrency_below_cpu_target(self):
        governor = resource_governor.AdaptiveResourceGovernor(sample_seconds=60, control_seconds=0.01)
        governor.snapshot.update(cpuPercent=30, memoryPercent=20, networkPressurePercent=0)
        governor.last_sample_at = time.monotonic()
        governor.last_control_at = 0
        self.assertEqual(governor.pending_limit(100), 75)
        self.assertEqual(governor.snapshot["dispatchPercent"], 75.0)

    def test_resource_governor_stops_new_work_at_memory_limit(self):
        governor = resource_governor.AdaptiveResourceGovernor(sample_seconds=60)
        governor.snapshot.update(cpuPercent=40, memoryPercent=80, networkPressurePercent=0)
        governor.last_sample_at = time.monotonic()
        self.assertEqual(governor.pending_limit(96), 1)
        self.assertEqual(governor.snapshot["reason"], "memory reached its safety limit")

    def test_resource_governor_halves_concurrency_on_remote_pressure(self):
        governor = resource_governor.AdaptiveResourceGovernor(sample_seconds=60)
        governor.snapshot.update(cpuPercent=30, memoryPercent=40)
        governor.last_sample_at = time.monotonic()
        for _index in range(20):
            governor.report("HTTP Error 429: Too Many Requests")
        self.assertEqual(governor.pending_limit(96), 48)

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
