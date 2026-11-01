#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AiProfile Skill - PerfDog 交互式会话管理器 (SessionManager)
维护采样生命周期状态：点击开始 -> 随时打标 -> 点击结束，持久化会话并生成分段画像。
"""

import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    from adb_bridge import AdbBridge
    from sdp_collector import SdpCollector
    from metrics_analyzer import MetricsAnalyzer
    from report_engine import ReportEngine
except ImportError:
    from .adb_bridge import AdbBridge
    from .sdp_collector import SdpCollector
    from .metrics_analyzer import MetricsAnalyzer
    from .report_engine import ReportEngine

SESSION_STATE_FILE = Path(os.path.expanduser("~/.aiprofile_session.json"))

class SessionManager:
    def __init__(self, adb: Optional[AdbBridge] = None):
        self.adb = adb or AdbBridge()
        self.collector = SdpCollector(self.adb)

    def is_session_active(self) -> bool:
        """检查当前是否有活跃的采样会话"""
        if not SESSION_STATE_FILE.exists():
            return False
        try:
            data = json.loads(SESSION_STATE_FILE.read_text(encoding="utf-8"))
            return data.get("active", False)
        except Exception:
            return False

    def get_current_session(self) -> Optional[dict[str, Any]]:
        if not self.is_session_active():
            return None
        try:
            return json.loads(SESSION_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return None

    def start_session(
        self,
        package: Optional[str] = None,
        tag: Optional[str] = None,
        period_ms: int = 200,
        fps: float = 60.0,
        launch: bool = False,
        output_dir: Optional[Path] = None
    ) -> dict[str, Any]:
        """启动持续采样会话 (类似 PerfDog 点击开始)"""
        if self.is_session_active():
            raise RuntimeError("已有正在运行的采样会话！请先调用 stop 结束它，或删除 ~/.aiprofile_session.json。")

        dev_env = self.adb.prepare_device_env()
        
        # 若指定了包名且要求先启动游戏
        if package and launch:
            print(f"[Device] 正在真机上启动游戏: {package}...")
            self.adb.launch_app(package)
            time.sleep(2.0)

        if not package:
            fg_pkg, fg_act = self.adb.get_foreground_app()
            if not fg_pkg:
                raise RuntimeError("未指定包名且真机无活跃前台应用，请先在手机上打开游戏！")
            package = fg_pkg

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_tag = tag or "LiveSession"
        out = output_dir or Path(f"Docs/Benchmarks/GPU/aiprofile_{ts}/{run_tag}")
        out.mkdir(parents=True, exist_ok=True)

        remote_tmp_dir = f"/data/local/tmp/gdp_sdpcli/session_{int(time.time() * 1000)}"
        start_time = time.time()

        proc = self.collector.start_continuous(remote_tmp_dir, period_ms=period_ms)

        session_state = {
            "active": True,
            "serial": self.adb.serial,
            "package": package,
            "tag": run_tag,
            "period_ms": period_ms,
            "fps": fps,
            "start_time": start_time,
            "output_dir": str(out.resolve()),
            "remote_tmp_dir": remote_tmp_dir,
            "device_env": dev_env,
            "labels": []
        }

        SESSION_STATE_FILE.write_text(json.dumps(session_state, ensure_ascii=False, indent=2), encoding="utf-8")
        return session_state

    def add_marker(self, label_name: str, source_line: Optional[int] = None) -> dict[str, Any]:
        """为当前时刻记录标签 (类似 PerfDog 点击打标签)"""
        session = self.get_current_session()
        if not session:
            raise RuntimeError("当前没有正在运行的采样会话，无法打标签！请先 start。")

        elapsed = round(time.time() - session["start_time"], 2)
        marker = {
            "name": (label_name or "").strip() or "Marker",
            "time_s": elapsed,
            "timestamp_iso": datetime.now().isoformat()
        }
        if source_line is not None:
            marker["source_line"] = int(source_line)

        session["labels"].append(marker)
        SESSION_STATE_FILE.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
        return marker

    def stop_session(self) -> dict[str, Any]:
        """停止当前会话，拉取数据并生成分段画像报表 (类似 PerfDog 点击结束)"""
        session = self.get_current_session()
        if not session:
            raise RuntimeError("当前没有运行中的采样会话！")

        out_dir = Path(session["output_dir"])
        raw_csv = out_dir / "raw" / f"sdp_{session['tag']}.csv"
        remote_tmp_dir = session["remote_tmp_dir"]

        # 上一次 stop 已拉到本地但后续步骤失败时，直接复用，不再依赖设备端（已被清理）
        if raw_csv.exists() and raw_csv.stat().st_size > 0:
            print(f"[AiProfile] 本地已有原始数据，跳过拉取: {raw_csv}")
        else:
            try:
                self.collector.stop_continuous(remote_tmp_dir, raw_csv)
            except Exception as exc:
                raise RuntimeError(
                    f"{exc}\n"
                    "会话仍保持未结束，可重新连接设备后再次 stop；"
                    "若数据确已不可恢复，用 abort 放弃该会话。"
                ) from exc

        # 截图与内存仅作补充信息，失败不应阻止出报告
        try:
            self.adb.capture_screenshot(out_dir / "capture.png")
        except Exception as exc:
            print(f"[AiProfile] 截图失败，已跳过: {exc}")
        try:
            mem_info = self.adb.get_process_memory(session["package"])
        except Exception as exc:
            print(f"[AiProfile] 内存信息获取失败，已跳过: {exc}")
            mem_info = {"total_pss_mb": 0.0, "graphics_pss_mb": 0.0}

        # 进行分段标签分析
        analyzer = MetricsAnalyzer(fps_baseline=session["fps"])
        metrics_res = analyzer.parse_sdp_csv(
            raw_csv,
            labels=session["labels"],
            period_ms=session["period_ms"]
        )

        # 生成 Markdown 与 HTML 图表
        rep_path = ReportEngine.generate_single_report(
            session["tag"],
            metrics_res,
            session["device_env"],
            mem_info,
            out_dir
        )

        # 清除活跃会话标记
        if SESSION_STATE_FILE.exists():
            SESSION_STATE_FILE.unlink()

        return {
            "report_path": rep_path,
            "timeline_html": out_dir / "timeline.html",
            "labeled_csv": metrics_res.get("labeled_csv"),
            "metrics": metrics_res,
            "labels_count": len(session["labels"]),
            "duration_s": round(time.time() - session["start_time"], 1)
        }

    def describe_session(self) -> Optional[dict[str, Any]]:
        """返回当前会话的概要（含已进行时长与输出目录），无会话时返回 None"""
        session = self.get_current_session()
        if not session:
            return None
        return {
            "package": session.get("package"),
            "tag": session.get("tag"),
            "serial": session.get("serial"),
            "period_ms": session.get("period_ms"),
            "elapsed_s": round(time.time() - session.get("start_time", time.time()), 1),
            "labels": [m.get("name") for m in session.get("labels", [])],
            "output_dir": session.get("output_dir"),
        }

    def abort_session(self) -> Optional[dict[str, Any]]:
        """放弃当前会话：停掉设备端采样并清除状态。已拉取到本地的数据不会被删除。"""
        info = self.describe_session()
        try:
            self.adb.shell("killall -9 sdpcli 2>/dev/null")
        except Exception:
            pass  # 设备已断连时仍要能清除本地状态
        if SESSION_STATE_FILE.exists():
            SESSION_STATE_FILE.unlink()
        return info
