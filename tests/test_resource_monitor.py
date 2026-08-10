import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import resource_monitor


class FinishedProcess:
    pid = os.getpid()

    def poll(self):
        return 0


class ResourceMonitorTests(unittest.TestCase):
    def test_cpu_percent_uses_total_and_idle_deltas(self):
        self.assertEqual(resource_monitor.cpu_percent((100, 40), (200, 70)), 70.0)
        self.assertIsNone(resource_monitor.cpu_percent(None, (200, 70)))

    def test_process_tree_usage_includes_descendants(self):
        usages = {10: (100, 1_000), 11: (40, 500), 12: (20, 250)}
        children = {10: [11, 12], 11: [], 12: []}
        with mock.patch.object(
            resource_monitor, "process_usage", side_effect=lambda pid: usages[pid]
        ), mock.patch.object(
            resource_monitor, "process_children", side_effect=lambda pid: children[pid]
        ):
            ticks, rss = resource_monitor.process_tree_usage(10)

        self.assertEqual(ticks, 160)
        self.assertEqual(rss, 1_750)

    def test_monitor_writes_a_bounded_run_history(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            history_path = directory / "resource-history.json"
            progress_path = directory / "guide-progress.json"
            progress_path.write_text(
                json.dumps(
                    {
                        "runId": 17,
                        "startedAt": "2026-08-10T02:04:49+00:00",
                        "phase": "testing",
                        "sourceCandidatesProcessed": 12,
                        "sourceCandidatesTotal": 40,
                    }
                ),
                encoding="utf-8",
            )

            result = resource_monitor.monitor_process(
                FinishedProcess(),
                history_path=history_path,
                progress_path=progress_path,
                interval_seconds=5,
            )

            payload = json.loads(history_path.read_text(encoding="utf-8"))
            self.assertEqual(result, 0)
            self.assertEqual(payload["runId"], 17)
            self.assertEqual(payload["samples"][0]["phase"], "testing")
            self.assertEqual(payload["samples"][0]["sourceCandidatesProcessed"], 12)
            self.assertEqual(payload["samples"][0]["sourceCandidatesTotal"], 40)
            self.assertIn("diskPercent", payload["samples"][0])
            self.assertEqual(payload["exitCode"], 0)


if __name__ == "__main__":
    unittest.main()
