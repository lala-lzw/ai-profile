"""随意使用场景的容错：忘记结束、设备断连、标签不规整。"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import compare_perfdog as cp
import session_manager as sm
from adb_bridge import CommandResult
from sdp_collector import SdpCollector

EXAMPLE = Path(__file__).resolve().parents[3] / "examples" / "iqoo10-demo"
PERFDOG = EXAMPLE / "perfdog" / "perfdog_gpu_counters.csv"


def make_summary(labels, segments=None, rows=50, fps=()):
    return {"period_ms_configured": 200, "rows": [[0]] * rows, "labels": labels,
            "segments": segments or [], "fps_samples": [{"Elapsed (s)": str(t)} for t in fps]}


class ResolveWindowTests(unittest.TestCase):
    def test_no_labels_uses_whole_run(self):
        w = cp.resolve_window(make_summary([], rows=100, fps=[1.0, 19.0]))
        self.assertEqual((w["gpu_start"], w["gpu_end"]), (0.0, 20.0))
        self.assertFalse(w["has_end"])
        self.assertTrue(w["notes"])

    def test_single_label_runs_to_end(self):
        labels = [{"name": "a", "time_s": 5.0}]
        segments = [{"label_name": "head", "start_time_s": 0.0, "end_time_s": 4.0},
                    {"label_name": "a", "start_time_s": 4.0, "end_time_s": 10.0}]
        w = cp.resolve_window(make_summary(labels, segments, rows=50, fps=[1.0, 11.0]))
        self.assertEqual(w["gpu_start"], 4.0)
        self.assertEqual(w["gpu_end"], 10.0)
        self.assertEqual(w["fps_start"], 5.0)
        self.assertFalse(w["has_end"])

    def test_duplicate_names_pick_by_position(self):
        labels = [{"name": "x", "time_s": 2.0}, {"name": "x", "time_s": 6.0}, {"name": "x", "time_s": 9.0}]
        segments = [{"label_name": "head", "start_time_s": 0.0}] + [
            {"label_name": "x", "start_time_s": s} for s in (1.8, 5.7, 8.8)]
        w = cp.resolve_window(make_summary(labels, segments), "x", "x")
        self.assertEqual((w["gpu_start"], w["gpu_end"]), (1.8, 8.8))
        self.assertTrue(w["has_end"])

    def test_unknown_label_gives_readable_error(self):
        with self.assertRaises(ValueError) as ctx:
            cp.resolve_window(make_summary([{"name": "a", "time_s": 1.0}]), "nope")
        self.assertIn("nope", str(ctx.exception))

    def test_example_session_without_end_label_still_compares(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            summary = json.loads((EXAMPLE / "summary.json").read_text(encoding="utf-8"))
            summary["labels"] = summary["labels"][:1]
            summary["segments"] = summary["segments"][:2]
            (tmp / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
            results, meta = cp.build(tmp, PERFDOG, 5.0, "calibrated")
            self.assertEqual(meta["align"], "shift")
            self.assertEqual(len(results), 29)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class FakeAdb:
    serial = None

    def __init__(self, fail=False):
        self.fail = fail
        self.commands = []

    def shell(self, command, **_):
        self.commands.append(command)
        if self.fail:
            raise OSError("device offline")
        return CommandResult(0, "", "")


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.state = self.tmp / "session.json"
        patcher = mock.patch.object(sm, "SESSION_STATE_FILE", self.state)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def write_session(self, **extra):
        session = {"active": True, "package": "com.example.demo", "tag": "T", "period_ms": 200, "fps": 60.0,
                   "start_time": 0.0, "output_dir": str(self.tmp / "out"), "remote_tmp_dir": "/tmp/x",
                   "device_env": {}, "labels": [], "serial": None}
        session.update(extra)
        self.state.write_text(json.dumps(session), encoding="utf-8")

    def manager(self, adb=None):
        with mock.patch.object(sm, "SdpCollector"):
            return sm.SessionManager(adb or FakeAdb())

    def test_empty_marker_falls_back_to_default_name(self):
        self.write_session(start_time=__import__("time").time())
        marker = self.manager().add_marker("   ")
        self.assertEqual(marker["name"], "Marker")

    def test_abort_clears_state_even_when_device_is_gone(self):
        self.write_session()
        info = self.manager(FakeAdb(fail=True)).abort_session()
        self.assertEqual(info["package"], "com.example.demo")
        self.assertFalse(self.state.exists())

    def test_abort_without_session_is_noop(self):
        self.assertIsNone(self.manager().abort_session())

    def test_describe_lists_labels_and_output(self):
        self.write_session(labels=[{"name": "a", "time_s": 1}])
        info = self.manager().describe_session()
        self.assertEqual(info["labels"], ["a"])
        self.assertIn("out", info["output_dir"])

    def test_failed_pull_keeps_session_active_for_retry(self):
        self.write_session()
        mgr = self.manager()
        mgr.collector.stop_continuous.side_effect = RuntimeError("拉取失败")
        with self.assertRaises(RuntimeError) as ctx:
            mgr.stop_session()
        self.assertIn("再次 stop", str(ctx.exception))
        self.assertTrue(self.state.exists())


class PullSafetyTests(unittest.TestCase):
    def test_remote_data_is_kept_when_pull_fails(self):
        class Adb:
            serial = None

            def __init__(self):
                self.commands = []

            def shell(self, command, **_):
                self.commands.append(command)
                out = "/data/x/a.csv\n" if command.startswith("find") else ""
                return CommandResult(0, out, "")

            def run(self, *args, **_):
                return CommandResult(1, "", "device offline")

        adb = Adb()
        collector = SdpCollector(adb)
        tmp = Path(tempfile.mkdtemp())
        try:
            with mock.patch("time.sleep"), self.assertRaises(RuntimeError):
                collector.stop_continuous("/data/x", tmp / "raw" / "out.csv")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertFalse(any(c.startswith("rm -rf /data/x") for c in adb.commands))


if __name__ == "__main__":
    unittest.main()
