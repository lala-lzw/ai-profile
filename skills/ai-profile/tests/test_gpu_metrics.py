import base64
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from cli_data import read_cli_csv
from gpu_metrics import METRICS,console_gpu_summary,project_counters
from metrics_analyzer import MetricsAnalyzer
from report_engine import ReportEngine
from timeline_report import generate_timeline


class GpuMetricsTests(unittest.TestCase):
    def test_names_units_and_visible_cells_are_original_cli_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            raw=root/"native.csv"
            source=(b"GPU % Utilization,% Shaders Busy,Clocks / Second,Fragment Instructions / Second,Vendor Counter,\r\n"
                    b"125.000006,60.123456,80000000.123456,32000000000.654321,9007199254740993.000001,\r\n")
            raw.write_bytes(source)
            generate_timeline("raw",{"raw_csv":str(raw)},root/"timeline.html")
            html=(root/"timeline.html").read_text(encoding="utf-8")
            data=json.loads(re.search(r"const report = (.*);",html).group(1))
            self.assertEqual(data["rawColumns"]["Fragment Instructions / Second"],["32000000000.654321"])
            self.assertEqual(data["rawColumns"]["Vendor Counter"],["9007199254740993.000001"])
            self.assertEqual(data["sourceLines"],[2])
            self.assertEqual(base64.b64decode(data["sourceBase64"]),source)
            self.assertEqual(data["sourceSha256"],hashlib.sha256(source).hexdigest())
            self.assertTrue(all(metric.label==metric.column and metric.divisor==1 for metric in METRICS))
            self.assertTrue(all(chart["limit"] is None for chart in data["charts"]))
            self.assertEqual(data["findings"][0]["value"],"125.000006")
            projected=project_counters({"Clocks / Second":"80000000","Fragment Instructions / Second":"32000000000"})
            self.assertEqual(projected["Clocks / Second"],80000000)
            self.assertEqual(projected["Fragment Instructions / Second"],32000000000)
            self.assertNotIn("gpu_mhz",projected)

    def test_source_anomalies_remain_in_report_with_exact_line_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            raw=root/"native.csv"
            source=("GPU % Utilization,Avg Preemption Delay,Preemptions / second,\n"
                    "0.003214,4420390833203.615234,99287.734555,\n"
                    "NaN,0.000000,0.000000,\n")
            raw.write_text(source,encoding="utf-8")
            result=MetricsAnalyzer().parse_sdp_csv(raw)
            self.assertEqual(result["raw_data"]["rows"][0][1],"4420390833203.615234")
            self.assertEqual(result["raw_data"]["rows"][1][0],"NaN")
            self.assertNotIn("frame_metrics",result)
            self.assertNotIn("gpu_clk_mhz",result)
            ReportEngine.generate_single_report("raw",result,{}, {},root)
            summary=json.loads((root/"summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["rows"][0][1],"4420390833203.615234")
            self.assertEqual(summary["source_sha256"],hashlib.sha256(raw.read_bytes()).hexdigest())
            self.assertNotIn("gpu_summary",summary)
            flags=summary["review_flags"]
            self.assertTrue(any(flag["line"]==2 and flag["column"]=="Avg Preemption Delay" for flag in flags))
            self.assertTrue(any(flag["line"]==3 and flag["value"]=="NaN" for flag in flags))
            audit=(root/"data_audit.md").read_text(encoding="utf-8")
            self.assertIn("4420390833203.615234",audit)
            console=console_gpu_summary(result)
            self.assertIn("GPU % Utilization: NaN",console)
            self.assertNotIn("MHz",console)
            self.assertNotIn("MB/s",console)

    def test_labeled_csv_preserves_cells_and_marker_source_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);raw=root/"native.csv"
            raw.write_text("Counter,\n0001.123456,\n9007199254740993.000001,\n",encoding="utf-8")
            result=MetricsAnalyzer().parse_sdp_csv(raw,labels=[{"name":"Stage","time_s":100,"source_line":3}])
            self.assertEqual([segment["row_count"] for segment in result["segments"]],[1,1])
            labeled=read_cli_csv(result["labeled_csv"])
            self.assertEqual([row[2] for row in labeled["rows"]],["0001.123456","9007199254740993.000001"])
            self.assertEqual(result["segments"][1]["boundary_basis"],"latest_observed_cli_line")


if __name__=="__main__": unittest.main()
