#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AiProfile Skill - 通用 Snapdragon Profiler (sdpcli) 硬件总线采样采集器
直接驱动 Adreno GPU 物理性能计数器（DDR 读写带宽、时钟、UBWC、ALU、片元、温度、CPU频点等）。
采用 Host-side 异步进程管理，支持超长周期（如 30min+）与高频率（如 5Hz/10Hz，100ms~200ms）持续采样，
具备超时自愈、实时心跳监控与自动落盘回收能力。
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
        if configured and Path(configured).is_file():
            return Path(configured)

        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidate = Path(local_app_data) / "Qualcomm" / "SnapdragonProfilerCLI" / "Android" / "2026.8.0" / "sdpcli"
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

    def capture(
        self,
        package: str,
        output_csv: Path,
        duration_s: float = 3.0,
        period_ms: int = 200,
        metric_ids: Optional[str] = None,
        warmup_s: float = 1.0,
    ) -> Path:
        """
        执行硬件物理计数器采样并导出 CSV
        - duration_s: 采样持续时间（秒），如 1800 代表 30 分钟
        - period_ms: 采样间隔（毫秒），如 200 代表每秒 5 次 (5 Hz)
        - metric_ids: 待采样的指标 ID 列表
        """
        self.prepare_device_daemon()

        if warmup_s > 0:
            time.sleep(warmup_s)

        output_csv.parent.mkdir(parents=True, exist_ok=True)
        selected_metrics = metric_ids or DEFAULT_METRIC_IDS

        # 清理旧的残留 sdpcli
        self.adb.shell("killall -9 sdpcli 2>/dev/null")

        ts = int(time.time() * 1000)
        remote_tmp_dir = f"{REMOTE_SDPCLI_DIR}/run_{ts}"
        self.adb.shell(f"mkdir -p {remote_tmp_dir}")

        duration_ms = int(duration_s * 1000)
        expected_rows = int(duration_ms / period_ms)

        command = (
            f"cd {REMOTE_SDPCLI_DIR} && "
            f"LD_LIBRARY_PATH={REMOTE_SDPCLI_DIR} "
            f"./sdpcli r c -d {duration_ms} -p {period_ms} -o {remote_tmp_dir} '{selected_metrics}'"
        )

        adb_cmd = [self.adb.adb_bin]
        if self.adb.serial:
            adb_cmd.extend(["-s", self.adb.serial])
        adb_cmd.extend(["shell", command])

        # 在宿主机端启动异步子进程执行 ADB 会话
        proc = subprocess.Popen(
            adb_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

        start_time = time.time()
        last_heartbeat = start_time
        poll_interval = 2.0 if duration_s >= 60.0 else 0.5
        remote_csv = ""
        row_count = 0

        # 监控进度与心跳
        while True:
            time.sleep(poll_interval)
            elapsed = time.time() - start_time

            # 检查是否有 CSV 生成
            if not remote_csv:
                listing = self.adb.shell(f"find {remote_tmp_dir} -maxdepth 1 -type f -name '*.csv'")
                for line in listing.stdout.splitlines():
                    if line.strip().endswith(".csv"):
                        remote_csv = line.strip()
                        break

            # 若是长周期采样（>=30秒），定期汇报心跳、行数与真机温度
            if duration_s >= 30.0 and (time.time() - last_heartbeat >= 15.0):
                pct = min(100.0, (elapsed / duration_s) * 100.0)
                temp_c = 0.0
                t_res = self.adb.shell("cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null")
                if t_res.ok and t_res.stdout.isdigit():
                    raw_t = float(t_res.stdout)
                    temp_c = raw_t / 1000.0 if raw_t > 1000 else raw_t

                if remote_csv:
                    wc = self.adb.shell(f"wc -l {remote_csv}")
                    parts = wc.stdout.strip().split()
                    if parts and parts[0].isdigit():
                        row_count = max(0, int(parts[0]) - 1)

                print(
                    f"[Profile 进度 {pct:4.1f}%] 已采 {elapsed:5.1f}s / {duration_s:.0f}s | "
                    f"样本: {row_count:5d}/{expected_rows:5d} 行 | 瞬时温度: {temp_c:.1f}°C"
                )
                last_heartbeat = time.time()

            # 时间达到采样时长后优雅结束
            if elapsed >= duration_s + 0.5:
                break

        # 终结进程并杀死设备端采样
        try:
            proc.terminate()
            proc.wait(timeout=2.0)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

        self.adb.shell("killall -9 sdpcli 2>/dev/null")

        # 确定最终 remote_csv
        if not remote_csv:
            listing = self.adb.shell(f"find {remote_tmp_dir} -maxdepth 1 -type f -name '*.csv'")
            for line in listing.stdout.splitlines():
                if line.strip().endswith(".csv"):
                    remote_csv = line.strip()
                    break

        if not remote_csv:
            self.adb.shell(f"rm -rf {remote_tmp_dir}")
            raise RuntimeError("sdpcli 采样未生成有效 CSV 文件。")

        # 获取最终行数
        wc_final = self.adb.shell(f"wc -l {remote_csv}")
        if wc_final.ok and wc_final.stdout.strip():
            parts = wc_final.stdout.strip().split()
            if parts and parts[0].isdigit():
                row_count = max(0, int(parts[0]) - 1)

        # 拉取文件到本地
        pull_res = self.adb.run("pull", remote_csv, str(output_csv), timeout=max(30.0, duration_s * 0.1 + 30.0))
        self.adb.shell(f"rm -rf {remote_tmp_dir}")

        if not pull_res.ok or not output_csv.exists() or output_csv.stat().st_size == 0:
            raise RuntimeError(f"从设备拉取 CSV 失败: {pull_res.stderr or pull_res.stdout}")

        total_elapsed = time.time() - start_time
        file_size_kb = output_csv.stat().st_size / 1024.0
        print(f"[Profile] 采样完成！总耗时: {total_elapsed:.1f}s | 生成数据: {output_csv.name} ({file_size_kb:.1f} KB, 共 {row_count} 行样本)")
        return output_csv
