import csv
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from metrics_analyzer import MetricsAnalyzer
from timeline_report import generate_timeline, prepare_stages


class StageFilterTests(unittest.TestCase):
    def test_fps_boundaries_follow_marker_time_instead_of_row_estimate(self):
        segments = [
            {"label_name":"初始阶段", "source_start_line":2, "source_end_line":4},
            {"label_name":"Scene", "source_start_line":5, "source_end_line":6},
            {"label_name":"Scene", "source_start_line":7, "source_end_line":9},
        ]
        stages = prepare_stages(segments, [
            {"name":"Scene", "source_line":5, "time_s":3},
            {"name":"Scene", "source_line":7, "time_s":5},
        ], list(range(2,10)))
        self.assertEqual([stage["is_marked"] for stage in stages], [False,True,True])
        self.assertEqual([stage["time_start_s"] for stage in stages], [0,3,5])
        self.assertEqual([stage["time_end_s"] for stage in stages], [3,5,None])
        self.assertEqual([stage["row_count"] for stage in stages], [3,2,3])
        self.assertNotEqual(stages[1]["id"], stages[2]["id"])

    def test_unmarked_capture_has_a_selectable_full_session_stage(self):
        stages = prepare_stages([], [], [2,3,4])
        self.assertEqual(len(stages),1)
        self.assertFalse(stages[0]["is_marked"])
        self.assertEqual(stages[0]["row_count"],3)
        self.assertEqual(prepare_stages([],[],[]),[])

    @unittest.skipUnless(shutil.which("node"), "Node is required for viewer behavior checks")
    def test_generated_viewer_filters_all_plots_without_modifying_cells(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root/"native.csv"
            with raw.open("w",newline="",encoding="utf-8") as stream:
                writer=csv.writer(stream)
                writer.writerow(["GPU % Utilization", "Read Total (Bytes/sec)"])
                writer.writerows([[value, value*1000] for value in [900,700,500,10,20,30,40,50]])
            fps = root/"fps.csv"
            with fps.open("w",newline="",encoding="utf-8") as stream:
                writer=csv.DictWriter(stream,fieldnames=["Elapsed (s)","FPS"])
                writer.writeheader()
                writer.writerows({"Elapsed (s)":time,"FPS":value}
                                 for time,value in [(1,900),(2,600),(3.5,30),(4.5,40),(5.5,50),(6.5,60)])
            result = MetricsAnalyzer().parse_sdp_csv(raw, labels=[
                {"name":"Scene A", "time_s":3, "source_line":5},
                {"name":"Scene B", "time_s":5, "source_line":7},
            ])
            output=root/"timeline.html"
            generate_timeline("test",result,output)
            data=json.loads(re.search(r"const report = (.*);",output.read_text(encoding="utf-8")).group(1))
            self.assertEqual(data["rawColumns"]["GPU % Utilization"][0],"900")
            self.assertEqual(data["sampleTimes"],[0,.2,.4,.6,.8,1,1.2,1.4])
            self.assertEqual(data["timeBasis"],"configured_sampling_interval")
            check=Path(__file__).with_name("stage_filter_check.cjs")
            run=subprocess.run([shutil.which("node"),str(check),str(output)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertIn("Stage filtering passed",run.stdout)

    def test_report_time_axis_respects_configured_period(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);raw=root/"native.csv"
            raw.write_text("Counter\n1.123456\n2.123456\n3.123456\n",encoding="utf-8")
            result=MetricsAnalyzer().parse_sdp_csv(raw,period_ms=500)
            output=root/"timeline.html"
            generate_timeline("time",result,output)
            data=json.loads(re.search(r"const report = (.*);",output.read_text(encoding="utf-8")).group(1))
            self.assertEqual(data["sampleTimes"],[0,.5,1])
            self.assertEqual(data["rawColumns"]["Counter"],["1.123456","2.123456","3.123456"])


if __name__=="__main__":
    unittest.main()
