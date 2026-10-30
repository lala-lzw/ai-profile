import csv
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from timeline_report import generate_timeline


class TimelineReportTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)

    def build(self, rows, **extra):
        source = self.root / "samples.csv"
        with source.open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.writer(stream)
            writer.writerow(["Time (s)", "Read Total (Bytes/sec)", "Write Total (Bytes/sec)", "GPU % Utilization"])
            writer.writerows(rows)
        output = self.root / "timeline.html"
        generate_timeline("test", {"labeled_csv": str(source), **extra}, output)
        html = output.read_text(encoding="utf-8")
        payload = json.loads(re.search(r"const report = (.*);", html).group(1))
        return html, payload

    def test_missing_and_nonfinite_values_are_gaps_and_zero_remains_valid(self):
        html, data = self.build([
            [0, 0, 1024**2, 0],
            [0.2, "", "NaN", "Infinity"],
            [0.4, 2*1024**2, 0, 20],
        ], gpu_util_pct=10)
        self.assertEqual(data["rawColumns"]["Read Total (Bytes/sec)"],["0","",str(2*1024**2)])
        self.assertEqual(data["rawColumns"]["GPU % Utilization"],["0","Infinity","20"])
        self.assertTrue(any(item["value"]=="NaN" for item in data["findings"]))
        self.assertNotIn("% Shaders Busy",data["rawColumns"])
        self.assertTrue(all(chart["limit"] is None for chart in data["charts"]))

    def test_tags_and_labels_cannot_break_out_of_script(self):
        text = '</script><img src=x onerror="alert(1)">'
        html, data = self.build([[0, 1, 2, 3]], labels=[{"name": text, "time_s": 0}],
                                segments=[{"label_name": text, "end_time_s": 0.2}])
        self.assertNotIn(text, html)
        self.assertEqual(data["labels"][0]["name"], text)
        self.assertEqual(data["segments"][0]["label_name"], text)
        self.assertEqual(html.count("</script>"), 1)
        self.assertNotRegex(html, r'<(?:script|link|img)[^>]+(?:src|href)="https?://')

    def test_long_recordings_keep_tail_and_brief_spikes(self):
        rows = [[i*0.2, (900 if i == 777 else 1)*1024**2, 0, 1] for i in range(1801)]
        html, data = self.build(rows)
        values=data["rawColumns"]["Read Total (Bytes/sec)"]
        self.assertEqual(len(values),1801)
        self.assertEqual(values[777],str(900*1024**2))
        self.assertEqual(data["sourceLines"][-1],1802)
        self.assertEqual(data["sampleCount"],1801)

    def test_empty_capture_generates_offline_view_with_no_invented_metrics(self):
        output = self.root / "empty.html"
        generate_timeline("empty", {}, output)
        data = json.loads(re.search(r"const report = (.*);", output.read_text(encoding="utf-8")).group(1))
        self.assertEqual(data["sampleCount"], 0)
        self.assertEqual(data["overview"],[])
        self.assertEqual(data["rawColumns"],{})


if __name__ == "__main__":
    unittest.main()
