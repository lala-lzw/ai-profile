#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AiProfile Skill - 通用 Snapdragon Profiler (sdpcli) 硬件总线采样采集器
直接驱动 Adreno GPU 物理性能计数器（DDR 读写带宽、时钟、UBWC、ALU、片元、温度、CPU频点等）。
支持像 PerfDog 一样的连续采样生命周期（开始收集 -> 随时打标 -> 结束收集并落盘）。
"""

import os
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

try:
    from adb_bridge import AdbBridge
except ImportError:
    from .adb_bridge import AdbBridge

# 设备端部署目录与二进制
REMOTE_SDPCLI_DIR = "/data/local/tmp/gdp_sdpcli"
REMOTE_SDPCLI_BIN = f"{REMOTE_SDPCLI_DIR}/sdpcli"

# 核心全景硬件物理指标集合（覆盖 GPU 读写总线、UBWC 压缩、片元/顶点指令、ALU、时钟、CPU频点与利用率、温度、内存）
DEFAULT_METRIC_IDS = (
    "1,4,5,8,9,10,11,12,13,18,22,23,24,26,27,28,29,30,31,32,33,38,41,"
    "49,51,52,53,54,55,56,57,58,59,60,61,65,67,68,69,80,81,84,85,88,91,"
    "94,97,100,103,106,108,109,110,111"
)

class SdpCollector:
    def __init__(self, adb: AdbBridge):
        self.adb = adb
        self.local_binary = self._find_local_binary()

    @staticmethod
    def _find_local_binary() -> Optional[Path]:
        """定位宿主机上的 Android aarch64 sdpcli 二进制及其依赖库"""
        configured = os.environ.get("SDPCLI_PATH")
        if configured:
            path = Path(configured).expanduser()
            if path.is_dir():
                path = path / "sdpcli"
            if path.is_file():
                return path

        home = Path.home()
        roots = [home / ".aiprofile" / "sdpcli"]
        for env_name in ("LOCALAPPDATA", "APPDATA"):
            base = os.environ.get(env_name)
            if base:
                roots.append(Path(base) / "Qualcomm" / "SnapdragonProfilerCLI" / "Android")
        roots.append(home / "Qualcomm" / "SnapdragonProfilerCLI" / "Android")
        roots.append(home / ".local" / "share" / "Qualcomm" / "SnapdragonProfilerCLI" / "Android")

        for root in roots:
            direct = root / "sdpcli"
            if direct.is_file():
                return direct
            if root.is_dir():
                # 版本目录如 2026.8.0；按目录名倒序，优先较新的版本。
                versions = sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name, reverse=True)
                for version_dir in versions:
                    candidate = version_dir / "sdpcli"
                    if candidate.is_file():
                        return candidate

        return None

    def is_available(self) -> bool:
        """检查设备端是否已有可执行二进制，或宿主机是否具备推送源"""
        chk = self.adb.shell(f"test -x {REMOTE_SDPCLI_BIN} && echo ready")
        if chk.ok and "ready" in chk.stdout:
            return True
        return self.local_binary is not None and self.local_binary.is_file()

    def prepare_device_daemon(self) -> bool:
        """确保设备端 /data/local/tmp/gdp_sdpcli 目录就绪并包含完整的 sdpcli 运行套件"""
        chk = self.adb.shell(f"test -x {REMOTE_SDPCLI_BIN} && echo ready")
        if chk.ok and "ready" in chk.stdout:
            return True

        if not self.local_binary or not self.local_binary.is_file():
            raise FileNotFoundError(
                "设备上未就绪 sdpcli，且宿主机未找到 Android sdpcli 预编译包。"
                "请安装 SnapdragonProfilerCLI 或设置 SDPCLI_PATH。"
            )

        self.adb.shell(f"mkdir -p {REMOTE_SDPCLI_DIR}")
        self.adb.run("push", str(self.local_binary), REMOTE_SDPCLI_BIN)
        source_dir = self.local_binary.parent
        for name in ("libsysmon.so", "libsysmondomain.so", "libsysmondomainV2.so", "libsysmonslpi.so"):
            library = source_dir / name
            if library.is_file():
                self.adb.run("push", str(library), f"{REMOTE_SDPCLI_DIR}/{name}")

        self.adb.shell(f"chmod -R 777 {REMOTE_SDPCLI_DIR}")
        return True

    def start_continuous(
        self,
        remote_tmp_dir: str,
        period_ms: int = 200,
        metric_ids: Optional[str] = None
    ) -> subprocess.Popen:
        """
        在设备端启动无固定时长的持续物理采样（类似 PerfDog 点击开始）
        采用 SIGINT 可控中断，确保停止时数据完整刷新落盘。
        """
        self.prepare_device_daemon()
        self.adb.shell("killall -9 sdpcli 2>/dev/null")
        self.adb.shell(f"rm -rf {remote_tmp_dir} && mkdir -p {remote_tmp_dir}")

        selected_metrics = metric_ids or DEFAULT_METRIC_IDS
        command = (
            f"cd {REMOTE_SDPCLI_DIR} && "
            f"LD_LIBRARY_PATH={REMOTE_SDPCLI_DIR} "
            f"./sdpcli r c -p {period_ms} -o {remote_tmp_dir} '{selected_metrics}'"
        )

        adb_cmd = [self.adb.adb_bin]
        if self.adb.serial:
            adb_cmd.extend(["-s", self.adb.serial])
        adb_cmd.extend(["shell", command])

        proc = subprocess.Popen(
            adb_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return proc

    def stop_continuous(
        self,
        remote_tmp_dir: str,
        output_csv: Path,
        proc: Optional[subprocess.Popen] = None,
        timeout: float = 15.0
    ) -> Path:
        """
        停止持续采样（类似 PerfDog 点击结束），优雅通知 sdpcli 刷新缓冲区并拉取最终 CSV
        """
        # 发送 SIGINT 让 sdpcli 优雅 flush 缓冲区
        self.adb.shell("killall -2 sdpcli 2>/dev/null")
        time.sleep(1.2)

        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=2.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

        # 确保全部终止
        self.adb.shell("killall -9 sdpcli 2>/dev/null")

        # 查找生成的 CSV
        listing = self.adb.shell(f"find {remote_tmp_dir} -maxdepth 1 -type f -name '*.csv'")
        remote_csv = next((line.strip() for line in listing.stdout.splitlines() if line.strip().endswith(".csv")), "")

        if not remote_csv:
            self.adb.shell(f"rm -rf {remote_tmp_dir}")
            raise RuntimeError(f"采样停止后未在 {remote_tmp_dir} 中找到生成的 CSV 文件。")

        output_csv.parent.mkdir(parents=True, exist_ok=True)
        pull_res = self.adb.run("pull", remote_csv, str(output_csv), timeout=timeout)

        if not pull_res.ok or not output_csv.exists() or output_csv.stat().st_size == 0:
            # 保留设备端数据，让用户重连后可再次执行 stop 重试
            raise RuntimeError(
                f"从设备拉取 CSV 失败: {pull_res.stderr or pull_res.stdout}。"
                f"设备端数据仍保留在 {remote_csv}，重新连接后再次执行 stop 即可重试。"
            )

        self.adb.shell(f"rm -rf {remote_tmp_dir}")
        return output_csv

    def capture(
        self,
        package: str,
        output_csv: Path,
        duration_s: float = 3.0,
        period_ms: int = 200,
        metric_ids: Optional[str] = None,
        warmup_s: float = 1.0,
    ) -> Path:
        """指定固定时长的采样便捷接口"""
        if warmup_s > 0:
            time.sleep(warmup_s)

        ts = int(time.time() * 1000)
        remote_tmp_dir = f"{REMOTE_SDPCLI_DIR}/run_{ts}"
        proc = self.start_continuous(remote_tmp_dir, period_ms=period_ms, metric_ids=metric_ids)

        start_time = time.time()
        last_heartbeat = start_time
        poll_interval = 2.0 if duration_s >= 60.0 else 0.5
        expected_rows = int(duration_s * 1000 / period_ms)

        while True:
            time.sleep(poll_interval)
            elapsed = time.time() - start_time

            if duration_s >= 30.0 and (time.time() - last_heartbeat >= 15.0):
                pct = min(100.0, (elapsed / duration_s) * 100.0)
                temp_c = 0.0
                t_res = self.adb.shell("cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null")
                if t_res.ok and t_res.stdout.isdigit():
                    raw_t = float(t_res.stdout)
                    temp_c = raw_t / 1000.0 if raw_t > 1000 else raw_t

                print(
                    f"[Profile 进度 {pct:4.1f}%] 已采 {elapsed:5.1f}s / {duration_s:.0f}s | "
                    f"瞬时温度: {temp_c:.1f}°C"
                )
                last_heartbeat = time.time()

            if elapsed >= duration_s:
                break

        return self.stop_continuous(remote_tmp_dir, output_csv, proc=proc)
