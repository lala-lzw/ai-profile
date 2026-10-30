import csv
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from metrics_analyzer import MetricsAnalyzer
from report_engine import ReportEngine


class ReportingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.output = Path(self.temp_dir.name)
        self.raw_csv = self.output / "raw.csv"
        with self.raw_csv.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["Read Total (Bytes/sec)", "Write Total (Bytes/sec)"])
            writer.writerows([
                [10 * 1024**2, 2 * 1024**2],
                [20 * 1024**2, 4 * 1024**2],
                [30 * 1024**2, 6 * 1024**2],
            ])

    def assert_timeline_series(self, metrics):
        ReportEngine.generate_single_report("test", metrics, {}, {}, self.output)
        html = (self.output / "timeline.html").read_text(encoding="utf-8")
        data=json.loads(re.search(r"const report = (.*);",html).group(1))
        self.assertEqual(data["sourceLines"],[2,3,4])
        self.assertEqual(data["rawColumns"]["Read Total (Bytes/sec)"],[str(value*1024**2) for value in (10,20,30)])
        self.assertEqual(data["rawColumns"]["Write Total (Bytes/sec)"],[str(value*1024**2) for value in (2,4,6)])

    def test_unmarked_recording_keeps_timeline_and_full_session_summary(self):
        for labels in (None, []):
            with self.subTest(labels=labels):
                metrics = MetricsAnalyzer().parse_sdp_csv(
                    self.raw_csv, labels=labels, period_ms=500
                )
                self.assertEqual(metrics["labels"], [])
                self.assertEqual(len(metrics["segments"]), 1)
                segment = metrics["segments"][0]
                self.assertEqual(segment["label_name"], "全程")
                self.assertEqual(segment["row_count"], 3)
                self.assertEqual(segment["duration_s"], 1.5)
                self.assertEqual(segment["source_start_line"],2)
                self.assertEqual(segment["source_end_line"],4)
                self.assertNotIn("total_bw_sec_mb",segment)
                self.assert_timeline_series(metrics)

    def test_marked_recording_preserves_segment_boundaries_and_curves(self):
        labels = [{"name": "Boss", "time_s": 0.5}]
        metrics = MetricsAnalyzer().parse_sdp_csv(
            self.raw_csv, labels=labels, period_ms=500
        )
        self.assertEqual(metrics["labels"], labels)
        self.assertEqual(
            [(s["label_name"], s["row_count"]) for s in metrics["segments"]],
            [("初始阶段", 1), ("Boss", 2)],
        )
        self.assert_timeline_series(metrics)


if __name__ == "__main__":
    unittest.main()
