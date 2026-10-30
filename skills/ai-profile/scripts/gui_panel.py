#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AiProfile Skill - 类似 PerfDog 的桌面悬浮控制面板 (Tkinter GUI)
提供图形化界面：点击开始 -> 输入文字打标签 -> 点击结束，自动打开交互式报告。
"""

import os
import sys
import threading
import time
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from session_manager import SessionManager

class PerfDogGui:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("AiProfile - 硬件性能采集 (PerfDog 模式)")
        self.root.geometry("480x520")
        self.root.resizable(False, False)
        self.root.configure(bg="#161b22")

        self.mgr = SessionManager()
        self.is_running = False
        self.start_time = 0.0

        self._build_ui()
        self._check_initial_state()

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")

        # 顶部标题栏
        top_frame = tk.Frame(self.root, bg="#0d1117", padx=16, pady=12)
        top_frame.pack(fill=tk.X)

        title_lbl = tk.Label(top_frame, text="⚡ AiProfile GPU 硬件总线采样", font=("Segoe UI", 13, "bold"), fg="#58a6ff", bg="#0d1117")
        title_lbl.pack(anchor="w")

        self.dev_lbl = tk.Label(top_frame, text="设备: 检测中... | 前台: 检测中...", font=("Segoe UI", 9), fg="#8b949e", bg="#0d1117")
        self.dev_lbl.pack(anchor="w", pady=(4, 0))

        # 中部控制区
        ctrl_frame = tk.Frame(self.root, bg="#161b22", padx=20, pady=16)
        ctrl_frame.pack(fill=tk.X)

        # 状态与计时
        status_frame = tk.Frame(ctrl_frame, bg="#161b22")
        status_frame.pack(fill=tk.X, pady=(0, 12))

        self.status_dot = tk.Label(status_frame, text="● 待机中", font=("Segoe UI", 11, "bold"), fg="#8b949e", bg="#161b22")
        self.status_dot.pack(side=tk.LEFT)

        self.timer_lbl = tk.Label(status_frame, text="00:00.0", font=("Consolas", 14, "bold"), fg="#c9d1d9", bg="#161b22")
        self.timer_lbl.pack(side=tk.RIGHT)

        # 开始 / 结束大按钮
        btn_frame = tk.Frame(ctrl_frame, bg="#161b22")
        btn_frame.pack(fill=tk.X, pady=(0, 16))

        self.start_btn = tk.Button(
            btn_frame,
            text="▶ 开始收集 (Start)",
            font=("Segoe UI", 11, "bold"),
            bg="#238636",
            fg="white",
            activebackground="#2ea043",
            relief=tk.FLAT,
            height=2,
            command=self._on_start
        )
        self.start_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        self.stop_btn = tk.Button(
            btn_frame,
            text="⏹ 结束收集 (Stop)",
            font=("Segoe UI", 11, "bold"),
            bg="#da3633",
            fg="white",
            activebackground="#f85149",
            relief=tk.FLAT,
            height=2,
            state=tk.DISABLED,
            command=self._on_stop
        )
        self.stop_btn.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(6, 0))

        # 打标签输入区
        tag_box = tk.LabelFrame(ctrl_frame, text=" 🏷️ 打标签 (Marker) ", font=("Segoe UI", 9, "bold"), fg="#58a6ff", bg="#161b22", padx=10, pady=10)
        tag_box.pack(fill=tk.X)

        tag_input_frame = tk.Frame(tag_box, bg="#161b22")
        tag_input_frame.pack(fill=tk.X)

        self.tag_entry = tk.Entry(tag_input_frame, font=("Segoe UI", 11), bg="#0d1117", fg="#c9d1d9", insertbackground="white", relief=tk.SOLID, bd=1)
        self.tag_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8), ipady=4)
        self.tag_entry.bind("<Return>", lambda e: self._on_add_tag())

        self.tag_btn = tk.Button(
            tag_input_frame,
            text="打标签 (Enter)",
            font=("Segoe UI", 10, "bold"),
            bg="#1f6feb",
            fg="white",
            activebackground="#388bfd",
            relief=tk.FLAT,
            state=tk.DISABLED,
            command=self._on_add_tag
        )
        self.tag_btn.pack(side=tk.RIGHT)

        # 快速标签预设按钮
        preset_frame = tk.Frame(tag_box, bg="#161b22")
        preset_frame.pack(fill=tk.X, pady=(10, 0))
        for p in ("进入大世界", "释放大招", "团战爆发", "场景加载", "切换极高画质"):
            b = tk.Button(
                preset_frame,
                text=p,
                font=("Segoe UI", 8),
                bg="#21262d",
                fg="#8b949e",
                relief=tk.FLAT,
                command=lambda t=p: self._quick_tag(t)
            )
            b.pack(side=tk.LEFT, padx=2)

        # 底部已打标签列表
        list_frame = tk.Frame(self.root, bg="#161b22", padx=20, pady=4)
        list_frame.pack(fill=tk.BOTH, expand=True)

        list_lbl = tk.Label(list_frame, text="已记录的标签列表 (Timeline Markers):", font=("Segoe UI", 9), fg="#8b949e", bg="#161b22")
        list_lbl.pack(anchor="w", pady=(0, 4))

        self.tag_listbox = tk.Listbox(list_frame, font=("Consolas", 10), bg="#0d1117", fg="#c9d1d9", selectbackground="#1f6feb", relief=tk.SOLID, bd=1)
        self.tag_listbox.pack(fill=tk.BOTH, expand=True)

    def _check_initial_state(self):
        def _bg():
            try:
                env = self.mgr.adb.prepare_device_env()
                pkg, _ = self.mgr.adb.get_foreground_app()
                self.root.after(0, lambda: self.dev_lbl.config(
                    text=f"设备: {env['model']} (Root: {env['has_root']}) | 前台: {pkg or '未检测到'}"
                ))
            except Exception as e:
                self.root.after(0, lambda: self.dev_lbl.config(text=f"ADB 检测失败: {e}"))
        threading.Thread(target=_bg, daemon=True).start()

    def _on_start(self):
        try:
            session = self.mgr.start_session(tag="PerfDogSession")
            self.is_running = True
            self.start_time = session["start_time"]

            self.start_btn.config(state=tk.DISABLED, bg="#21262d")
            self.stop_btn.config(state=tk.NORMAL, bg="#da3633")
            self.tag_btn.config(state=tk.NORMAL)
            self.status_dot.config(text="● 正在高频采样中", fg="#3fb950")
            self.tag_listbox.delete(0, tk.END)

            self._tick_timer()
        except Exception as e:
            messagebox.showerror("启动失败", str(e))

    def _tick_timer(self):
        if not self.is_running:
            return
        elapsed = time.time() - self.start_time
        mins = int(elapsed // 60)
        secs = elapsed % 60
        self.timer_lbl.config(text=f"{mins:02d}:{secs:04.1f}")
        self.root.after(100, self._tick_timer)

    def _on_add_tag(self):
        text = self.tag_entry.get().strip()
        if not text or not self.is_running:
            return
        try:
            m = self.mgr.add_marker(text)
            self.tag_listbox.insert(tk.END, f"[{m['time_s']:5.1f}s] 🏷️ {text}")
            self.tag_listbox.see(tk.END)
            self.tag_entry.delete(0, tk.END)
        except Exception as e:
            messagebox.showerror("打标签失败", str(e))

    def _quick_tag(self, text: str):
        if not self.is_running:
            return
        self.tag_entry.delete(0, tk.END)
        self.tag_entry.insert(0, text)
        self._on_add_tag()

    def _on_stop(self):
        self.is_running = False
        self.status_dot.config(text="⏳ 正在拉取数据与生成报告...", fg="#d29922")
        self.stop_btn.config(state=tk.DISABLED, bg="#21262d")
        self.tag_btn.config(state=tk.DISABLED)

        def _worker():
            try:
                res = self.mgr.stop_session()
                self.root.after(0, lambda: self._on_stop_done(res))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("结束失败", str(e)))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_stop_done(self, res: dict):
        self.status_dot.config(text="✔ 测试完成", fg="#58a6ff")
        self.start_btn.config(state=tk.NORMAL, bg="#238636")
        html_file = res["timeline_html"]

        msg = (
            f"采样完成！总耗时: {res['duration_s']}s | 记录标签: {res['labels_count']} 个\n\n"
            f"报告文件:\n{res['report_path']}\n\n"
            "是否立即在浏览器中打开交互式时间轴走势图？"
        )
        if messagebox.askyesno("测试完成", msg):
            if html_file.exists():
                webbrowser.open(str(html_file.resolve()))

def main():
    root = tk.Tk()
    app = PerfDogGui(root)
    root.mainloop()

if __name__ == "__main__":
    main()
