import csv
import json
from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from fps_reader import FpsReader, FpsRecorder, candidate_layers, parse_latency, SOURCE
from metrics_analyzer import MetricsAnalyzer
from report_engine import ReportEngine


def response(text, ok=True):
    return SimpleNamespace(stdout=text,ok=ok,stderr="" if ok else "permission denied")


def latency(*timestamps):
    return "16666666\n"+"\n".join(f"{stamp-100}\t{stamp}\t{stamp-50}" for stamp in timestamps)


class FpsTests(unittest.TestCase):
    def test_counts_real_present_intervals_and_stale_buffer_is_zero(self):
        layer="SurfaceView[com.example.game/Main](BLAST)#5"
        first=1_000_000_000
        bridge=SimpleNamespace(shell=Mock(side_effect=[response(layer),
            response(latency(first,first+20_000_000)),
            response(latency(first,first+20_000_000,first+40_000_000,first+60_000_000)),
            response(latency(first,first+20_000_000,first+40_000_000,first+60_000_000)),
            response("",False)]))
        reader=FpsReader(bridge,"com.example.game",clock=lambda:1)
        self.assertIsNone(reader.read()["fps"])
        sample=reader.read()
        self.assertEqual(sample["fps"],50)
        self.assertEqual(sample["frame_count"],2)
        self.assertEqual(len(sample["frames"]),2)
        self.assertEqual(reader.read()["fps"],0)
        self.assertIsNone(reader.read()["fps"])

    def test_pending_frames_and_other_application_layers_are_ignored(self):
        text="16666666\n0 0 0\n1 9223372036854775807 2\n1 12345 2\n1 12345 2"
        self.assertEqual(parse_latency(text),[(1,12345,2)])
        layers=candidate_layers("\n".join([
            "Background for SurfaceView[com.example.game/Main]#1",
            "SurfaceView[com.example.game2/Main](BLAST)#2",
            "com.example.game/Main#3",
            "SurfaceView[com.example.game/Main](BLAST)#4"]),"com.example.game")
        self.assertEqual(layers,["SurfaceView[com.example.game/Main](BLAST)#4","com.example.game/Main#3"])

    def test_buffer_rollover_uses_observed_intervals_without_inventing_frames(self):
        bridge=SimpleNamespace(shell=Mock(side_effect=[response("SurfaceView[com.game/Main](BLAST)"),
            response(latency(1_000_000_000,1_020_000_000)),
            response(latency(2_000_000_000,2_020_000_000,2_040_000_000))]))
        reader=FpsReader(bridge,"com.game",clock=lambda:1)
        reader.read()
        sample=reader.read()
        self.assertEqual(sample["fps"],50)
        self.assertEqual(sample["status"],"buffer_window")
        self.assertEqual(sample["frame_count"],2)

    def test_saved_fps_and_raw_timestamps_reach_report_without_changing_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            raw=folder/"raw";raw.mkdir()
            cli=raw/"native.csv"
            source=b"GPU % Utilization,\r\n9.123456,\r\n"
            cli.write_bytes(source)
            recorder=FpsRecorder(folder,0)
            sample={"fps":50.0,"source":SOURCE,"layer":"SurfaceView[com.game/Main]",
                    "status":"ok","frame_count":2,"first_present_ns":1000000000,
                    "last_present_ns":1040000000,"frames":[(1,1020000000,2),(3,1040000000,4)]}
            recorder.append(sample,elapsed=1)
            recorder.append({**sample,"fps":None,"status":"unavailable","frames":[]},elapsed=2)
            with (raw/"fps.csv").open(encoding="utf-8") as stream:
                rows=list(csv.DictReader(stream))
            self.assertEqual([row["FPS"] for row in rows],["50.0",""])
            with (raw/"surfaceflinger_frames.csv").open(encoding="utf-8") as stream:
                frames=list(csv.DictReader(stream))
            self.assertEqual(frames[0]["actualPresentTime (ns)"],"1020000000")
            result=MetricsAnalyzer().parse_sdp_csv(cli)
            ReportEngine.generate_single_report("fps",result,{}, {},folder)
            html=(folder/"timeline.html").read_text(encoding="utf-8")
            report=json.loads(re.search(r"const report = (.*);",html).group(1))
            self.assertEqual(report["fpsSamples"],rows)
            self.assertNotIn("FPS",report["rawColumns"])
            self.assertEqual(cli.read_bytes(),source)


if __name__=="__main__":unittest.main()
