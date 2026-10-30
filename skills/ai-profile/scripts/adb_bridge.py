#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AiProfile Skill - 通用 ADB 设备管理与系统监控桥接器 (AdbBridge)
完全与游戏项目解耦，支持任意 Android 设备的 Root 提权、SELinux 放行、前台检测、内存/帧率监控与屏幕抓取。
"""

import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

class AdbBridge:
    def __init__(self, serial: Optional[str] = None):
        self.serial = serial or os.environ.get("ANDROID_SERIAL")
        self.adb_bin = shutil.which("adb") or "adb"

    def run(self, *args: str, timeout: Optional[float] = None) -> CommandResult:
        cmd = [self.adb_bin]
        if self.serial:
            cmd.extend(["-s", self.serial])
        cmd.extend(args)
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return CommandResult(proc.returncode, proc.stdout.strip(), proc.stderr.strip())

    def shell(self, cmd: str, timeout: Optional[float] = None) -> CommandResult:
        return self.run("shell", cmd, timeout=timeout)

    def su_shell(self, cmd: str, timeout: Optional[float] = None) -> CommandResult:
        safe = cmd.replace('"', '\\"')
        return self.shell(f'su -c "{safe}"', timeout=timeout)

    def prepare_device_env(self) -> dict[str, Any]:
        """检查并准备设备底层环境：Root、SELinux Permissive、FastRPC 权限"""
        res = self.shell("getprop ro.product.model")
        model = res.stdout if res.ok else "Unknown"

        su_test = self.su_shell("id")
        has_root = su_test.ok and "uid=0" in su_test.stdout

        selinux = "Unknown"
        if has_root:
            self.su_shell("setenforce 0")
            s_res = self.shell("getenforce")
            selinux = s_res.stdout if s_res.ok else "Unknown"
        else:
            s_res = self.shell("getenforce")
            selinux = s_res.stdout if s_res.ok else "Unknown"

        return {
            "model": model,
            "has_root": has_root,
            "selinux": selinux
        }

    def get_foreground_app(self) -> tuple[Optional[str], Optional[str]]:
        """检测当前真机前台运行的包名和主 Activity"""
        res = self.shell("dumpsys window displays")
        if res.ok:
            m = re.search(r"mCurrentFocus=Window\{[^\}]*\s+([a-zA-Z0-9._]+)/([a-zA-Z0-9._]+)", res.stdout)
            if m:
                return m.group(1), m.group(2)

        res = self.shell("dumpsys activity top")
        if res.ok:
            for line in res.stdout.splitlines():
                if "ACTIVITY" in line and "/" in line:
                    parts = line.strip().split()
                    for p in parts:
                        if "/" in p and not p.startswith("/"):
                            pkg, act = p.split("/", 1)
                            return pkg, act
        return None, None

    def capture_screenshot(self, local_path: Path) -> bool:
        """从设备截取当前屏幕并保存到本地"""
        remote_tmp = "/data/local/tmp/aiprofile_screen.png"
        self.shell(f"screencap -p {remote_tmp}")
        local_path.parent.mkdir(parents=True, exist_ok=True)
        res = self.run("pull", remote_tmp, str(local_path))
        self.shell(f"rm -f {remote_tmp}")
        return res.ok and local_path.exists()

    def get_process_memory(self, package: str) -> dict[str, float]:
        """获取应用当前内存占用：Total PSS 与 Graphics PSS (MB)"""
        res = self.shell(f"dumpsys meminfo {package}")
        if not res.ok:
            return {"total_pss_mb": 0.0, "graphics_pss_mb": 0.0}

        total_pss = 0.0
        graphics_pss = 0.0
        for line in res.stdout.splitlines():
            line_clean = line.strip()
            if line_clean.startswith("TOTAL PSS:") or line_clean.startswith("TOTAL:"):
                m = re.search(r"TOTAL(?:\s+PSS)?:\s+(\d+)", line_clean)
                if m:
                    total_pss = float(m.group(1)) / 1024.0
            elif "Graphics:" in line:
                m = re.search(r"Graphics:\s+(\d+)", line)
                if m:
                    graphics_pss = float(m.group(1)) / 1024.0

        return {
            "total_pss_mb": round(total_pss, 2),
            "graphics_pss_mb": round(graphics_pss, 2)
        }

    def get_gpu_status(self) -> dict[str, Any]:
        """获取 Adreno GPU 当前工作频点、利用率和温度"""
        freq_mhz = 0.0
        busy_pct = 0.0
        temp_c = 0.0

        f_res = self.su_shell("cat /sys/class/kgsl/kgsl-3d0/gpuclk")
        if f_res.ok and f_res.stdout.isdigit():
            freq_mhz = round(float(f_res.stdout) / 1e6, 2)

        b_res = self.su_shell("cat /sys/class/kgsl/kgsl-3d0/gpubusy")
        if b_res.ok:
            parts = b_res.stdout.strip().split()
            if len(parts) >= 2:
                busy = float(parts[0])
                total = float(parts[1])
                if total > 0:
                    busy_pct = round(busy / total * 100.0, 2)

        t_res = self.shell("cat /sys/class/thermal/thermal_zone0/temp")
        if t_res.ok and t_res.stdout.isdigit():
            raw_t = float(t_res.stdout)
            temp_c = round(raw_t / 1000.0 if raw_t > 1000 else raw_t, 1)

        return {
            "gpu_freq_mhz": freq_mhz,
            "gpu_busy_pct": busy_pct,
            "temperature_c": temp_c
        }

