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
        output_dir: Optional[Path] = None
    ) -> dict[str, Any]:
        """启动持续采样会话 (类似 PerfDog 点击开始)"""
        if self.is_session_active():
            raise RuntimeError("已有正在运行的采样会话！请先调用 stop 结束它，或删除 ~/.aiprofile_session.json。")

        dev_env = self.adb.prepare_device_env()
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

    def add_marker(self, label_name: str) -> dict[str, Any]:
        """为当前时刻记录标签 (类似 PerfDog 点击打标签)"""
        session = self.get_current_session()
        if not session:
            raise RuntimeError("当前没有正在运行的采样会话，无法打标签！请先 start。")

        elapsed = round(time.time() - session["start_time"], 2)
        marker = {
            "name": label_name.strip(),
            "time_s": elapsed,
            "timestamp_iso": datetime.now().isoformat()
        }

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

        # 优雅通知 sdpcli flush 并拉取 CSV
        self.collector.stop_continuous(remote_tmp_dir, raw_csv)

        # 补充截图与内存信息
        screen_png = out_dir / "capture.png"
        self.adb.capture_screenshot(screen_png)
        mem_info = self.adb.get_process_memory(session["package"])

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
