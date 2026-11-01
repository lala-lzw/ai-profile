from pathlib import Path
import sys
import unittest
from unittest.mock import Mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from adb_bridge import AdbBridge, CommandResult


class DeviceMetadataTests(unittest.TestCase):
    def test_graphics_api_decodes_opengles_and_vulkan_features(self):
        bridge = AdbBridge()
        responses = {
            "getprop ro.opengles.version": CommandResult(0, "196610", ""),
            "pm list features": CommandResult(0, "feature:android.hardware.vulkan.level\n", ""),
        }
        bridge.shell = Mock(side_effect=lambda command, timeout=None: responses[command])
        self.assertEqual(bridge.get_graphics_api(), "OpenGL ES 3.2 / Vulkan")

    def test_prepare_device_env_keeps_android_and_graphics_metadata(self):
        bridge = AdbBridge()
        responses = {
            "getprop ro.product.model": CommandResult(0, "iQOO 10", ""),
            "getprop ro.build.version.release": CommandResult(0, "15", ""),
            "getprop ro.opengles.version": CommandResult(0, "196610", ""),
            "pm list features": CommandResult(0, "feature:android.hardware.vulkan.version\n", ""),
            "getenforce": CommandResult(0, "Enforcing", ""),
        }
        bridge.shell = Mock(side_effect=lambda command, timeout=None: responses[command])
        bridge.su_shell = Mock(return_value=CommandResult(1, "", "not permitted"))
        env = bridge.prepare_device_env()
        self.assertEqual(env["android"], "15")
        self.assertEqual(env["graphics_api"], "OpenGL ES 3.2 / Vulkan")


if __name__ == "__main__":
    unittest.main()
