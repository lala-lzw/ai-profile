#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AiProfile Skill - 通用 Snapdragon Profiler (sdpcli) 硬件总线采样采集器
驱动 Adreno GPU 物理性能计数器（DDR 读写带宽、时钟、UBWC、ALU、片元）。
"""

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Optional
try:
    from adb_bridge import AdbBridge
except ImportError:
    from .adb_bridge import AdbBridge

DEFAULT_SDPCLI_PATH = Path(r"C:\Program Files\Qualcomm\Snapdragon Profiler\sdpcli.exe")
DEVICE_PROFILE_DIR = "/data/local/tmp/SnapdragonProfiler"

DEFAULT_GPU_METRICS = (
    "Clocks / Second",
    "GPU % Utilization",
    "GPU % Bus Busy",
    "% Texture Fetch Stall",
    "L1 Texture Cache Miss Per Pixel",
    "% Texture L1 Miss",
    "% Texture L2 Miss",
    "% Stalled on System Memory",
    "% Instruction Cache Miss",
    "Average Vertices / Polygon",
    "% Wave Context Occupancy",
    "% Shaders Busy",
    "% Shaders Stalled",
    "Fragments Shaded / Second",
    "Vertex Instructions / Second",
    "Fragment Instructions / Second",
    "Fragment ALU Instructions / Sec (Full)",
    "Fragment ALU Instructions / Sec (Half)",
    "Fragment EFU Instructions / Second",
    "Textures / Vertex",
    "Textures / Fragment",
    "% Time Shading Fragments",
    "% Shader ALU Capacity Utilized",
    "% Texture Pipes Busy",
    "Read Total (Bytes/sec)",
    "Write Total (Bytes/sec)",
    "Texture Memory Read BW (Bytes/Second)",
    "Vertex Memory Read (Bytes/Second)",
    "SP Memory Read (Bytes/Second)",
    "Avg Bytes / Fragment",
    "Avg Bytes / Vertex",
    "Preemptions / second",
    "Avg Preemption Delay",
    "% Image Read L2 Hit",
    "Global Memory Atomic Instructions",
    "Local Memory Load Instructions",
    "Global Memory Load Instructions",
    "Global Image Uncompressed Data Read BW (Bytes/sec)",
    "Global Image Compressed Data Read BW (Bytes/sec)",
)

class SdpCollector:
    def __init__(self, adb: AdbBridge, sdpcli_bin: Optional[Path] = None):
        self.adb = adb
        self.sdpcli_bin = sdpcli_bin or DEFAULT_SDPCLI_PATH
        if not self.sdpcli_bin.exists():
            which_sdp = shutil.which("sdpcli")
            if which_sdp:
                self.sdpcli_bin = Path(which_sdp)

    def is_available(self) -> bool:
        return self.sdpcli_bin.exists()

    def prepare_device_daemon(self) -> bool:
        """确保设备上 SnapdragonProfiler 守护程序已就绪并运行"""
        chk = self.adb.shell(f"ls {DEVICE_PROFILE_DIR}/target")
        if not chk.ok or "target" not in chk.stdout:
            host_dir = self.sdpcli_bin.parent / "target"
            if host_dir.exists():
                self.adb.run("push", str(host_dir), DEVICE_PROFILE_DIR)
                self.adb.shell(f"chmod -R 777 {DEVICE_PROFILE_DIR}")

        p_check = self.adb.shell("pidof target")
        if not p_check.ok or not p_check.stdout.strip():
            self.adb.su_shell(f"{DEVICE_PROFILE_DIR}/target &")
            time.sleep(1.0)

        return True

    def capture(
        self,
        package: str,
        output_csv: Path,
        duration_s: float = 3.0,
        period_ms: int = 200,
        metrics: Optional[tuple[str, ...]] = None,
        warmup_s: float = 1.0
    ) -> Path:
        """执行硬件物理计数器采样并导出 CSV"""
        if not self.is_available():
            raise FileNotFoundError(f"未找到 sdpcli.exe: {self.sdpcli_bin}")

        self.prepare_device_daemon()

        if warmup_s > 0:
            time.sleep(warmup_s)

        output_csv.parent.mkdir(parents=True, exist_ok=True)
        selected_metrics = metrics or DEFAULT_GPU_METRICS
        metric_args = [f"-m {m}" for m in selected_metrics]

        cmd = [
            str(self.sdpcli_bin),
            "profile",
            "-p", package,
            "-t", str(int(duration_s)),
            "-f", str(period_ms),
            "-c", str(output_csv),
            *metric_args
        ]

        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

        if not output_csv.exists() or output_csv.stat().st_size == 0:
            raise RuntimeError(f"sdpcli 采样失败，未生成有效 CSV 文件。\nStdout: {proc.stdout}\nStderr: {proc.stderr}")

        return output_csv
