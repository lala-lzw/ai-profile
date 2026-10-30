from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from adb_bridge import AdbBridge
from sdp_collector import SdpCollector


CONSOLE_PROBE = "import ctypes; print(int(bool(ctypes.windll.kernel32.GetConsoleWindow())))"


@unittest.skipUnless(sys.platform == "win32", "Windows console behavior")
class BackgroundProcessTests(unittest.TestCase):
    def test_adb_command_child_has_no_console_and_keeps_output(self):
        bridge = AdbBridge()
        bridge.serial = None
        bridge.adb_bin = sys.executable
        result = bridge.run("-c", CONSOLE_PROBE, timeout=10)
        self.assertTrue(result.ok, result.stderr)
        self.assertEqual(result.stdout, "0")

    def test_continuous_collector_child_has_no_console_and_keeps_output(self):
        bridge = SimpleNamespace(adb_bin=sys.executable, serial=None, shell=lambda cmd: None)
        collector = SdpCollector(bridge)
        spawn = subprocess.Popen

        def spawn_console_probe(command, **kwargs):
            # Exercise the collector's process options without starting a device capture.
            self.assertEqual(command[1], "shell")
            return spawn([sys.executable, "-c", CONSOLE_PROBE], **kwargs)

        with patch.object(collector, "prepare_device_daemon"), patch(
            "sdp_collector.subprocess.Popen", side_effect=spawn_console_probe
        ):
            with collector.start_continuous("/unused-test-directory") as process:
                stdout, stderr = process.communicate(timeout=10)
                self.assertEqual(process.returncode, 0, stderr)
                self.assertEqual(stdout.strip(), "0")


if __name__ == "__main__":
    unittest.main()
