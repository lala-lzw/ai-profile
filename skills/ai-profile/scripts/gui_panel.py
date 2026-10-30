#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AiProfile Skill - 类似 PerfDog 的桌面悬浮控制面板 (Tkinter GUI)
提供图形化界面：选择应用拉起 -> 点击开始 -> 输入文字打标签 -> 点击结束，自动打开交互式报告。
默认置顶窗口 (-topmost)，确保在 IDE 前方清晰可见。
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
        self.root.title("AiProfile - 移动端 GPU 硬件总线采样 (PerfDog 模式)")
        self.root.resizable(False, False)
        self.root.configure(bg="#161b22")

        # 屏幕正中央居中显示，并置顶抢焦点
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w, h = 520, 640
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        self.root.attributes("-topmost", True)
        self.root.update_idletasks()
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

        self.mgr = SessionManager()
        self.is_running = False
        self.start_time = 0.0
        self.installed_apps = []

        self._build_ui()
        self._check_initial_state()

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")

        # 配置 Combobox 样式
        style.configure("TCombobox", fieldbackground="#0d1117", background="#21262d", foreground="#c9d1d9")

        # 顶部标题栏
        top_frame = tk.Frame(self.root, bg="#0d1117", padx=16, pady=12)
        top_frame.pack(fill=tk.X)

        header_box = tk.Frame(top_frame, bg="#0d1117")
        header_box.pack(fill=tk.X)

        title_lbl = tk.Label(header_box, text="⚡ AiProfile GPU 硬件总线采样", font=("Segoe UI", 13, "bold"), fg="#58a6ff", bg="#0d1117")
        title_lbl.pack(side=tk.LEFT)

        topmost_chk = tk.Checkbutton(
            header_box,
            text="窗口置顶",
            font=("Segoe UI", 8),
            fg="#8b949e",
            bg="#0d1117",
            selectcolor="#161b22",
            activebackground="#0d1117",
            command=self._toggle_topmost
        )
        topmost_chk.select()
        topmost_chk.pack(side=tk.RIGHT)

        self.dev_lbl = tk.Label(top_frame, text="设备: 检测中... | 当前前台: 检测中...", font=("Segoe UI", 9), fg="#8b949e", bg="#0d1117")
        self.dev_lbl.pack(anchor="w", pady=(4, 0))

        # 中部控制容器
        ctrl_frame = tk.Frame(self.root, bg="#161b22", padx=20, pady=12)
        ctrl_frame.pack(fill=tk.X)

        # 1. 应用选择与启动区
        app_box = tk.LabelFrame(ctrl_frame, text=" 📱 选择测试应用 (支持自动拉起) ", font=("Segoe UI", 9, "bold"), fg="#58a6ff", bg="#161b22", padx=10, pady=8)
        app_box.pack(fill=tk.X, pady=(0, 10))

        self.app_var = tk.StringVar(value="正在扫描真机已安装应用...")
        self.app_combo = ttk.Combobox(app_box, textvariable=self.app_var, state="readonly", font=("Segoe UI", 9))
        self.app_combo.pack(fill=tk.X, pady=(0, 6))
        self.app_combo.bind("<<ComboboxSelected>>", self._on_app_selected)

        app_opt_frame = tk.Frame(app_box, bg="#161b22")
        app_opt_frame.pack(fill=tk.X)

        self.launch_var = tk.BooleanVar(value=True)
        self.launch_chk = tk.Checkbutton(
            app_opt_frame,
            text="开始时在手机上自动启动该游戏",
            variable=self.launch_var,
            font=("Segoe UI", 9),
            fg="#c9d1d9",
            bg="#161b22",
            selectcolor="#0d1117",
            activebackground="#161b22"
        )
        self.launch_chk.pack(side=tk.LEFT)

        refresh_btn = tk.Button(
            app_opt_frame,
            text="🔄 刷新列表",
            font=("Segoe UI", 8),
            bg="#21262d",
            fg="#8b949e",
            relief=tk.FLAT,
            command=self._load_apps
        )
        refresh_btn.pack(side=tk.RIGHT)

        # 2. 状态与计时
        status_frame = tk.Frame(ctrl_frame, bg="#161b22")
        status_frame.pack(fill=tk.X, pady=(0, 10))

        self.status_dot = tk.Label(status_frame, text="● 待机中", font=("Segoe UI", 11, "bold"), fg="#8b949e", bg="#161b22")
        self.status_dot.pack(side=tk.LEFT)

        self.timer_lbl = tk.Label(status_frame, text="00:00.0", font=("Consolas", 14, "bold"), fg="#c9d1d9", bg="#161b22")
        self.timer_lbl.pack(side=tk.RIGHT)

        # 3. 开始 / 结束大按钮
        btn_frame = tk.Frame(ctrl_frame, bg="#161b22")
        btn_frame.pack(fill=tk.X, pady=(0, 12))

        self.start_btn = tk.Button(
            btn_frame,
            text="🚀 启动并开始收集",
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

        # 4. 打标签输入区
        tag_box = tk.LabelFrame(ctrl_frame, text=" 🏷️ 实时打标签 (Marker) ", font=("Segoe UI", 9, "bold"), fg="#58a6ff", bg="#161b22", padx=10, pady=8)
        tag_box.pack(fill=tk.X)

        tag_input_frame = tk.Frame(tag_box, bg="#161b22")
        tag_input_frame.pack(fill=tk.X)

        self.tag_entry = tk.Entry(tag_input_frame, font=("Segoe UI", 10), bg="#0d1117", fg="#c9d1d9", insertbackground="white", relief=tk.SOLID, bd=1)
        self.tag_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8), ipady=3)
        self.tag_entry.bind("<Return>", lambda e: self._on_add_tag())

        self.tag_btn = tk.Button(
            tag_input_frame,
            text="打标签 (Enter)",
            font=("Segoe UI", 9, "bold"),
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
        preset_frame.pack(fill=tk.X, pady=(8, 0))
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

        # 5. 底部已打标签列表
        list_frame = tk.Frame(self.root, bg="#161b22", padx=20, pady=4)
        list_frame.pack(fill=tk.BOTH, expand=True)

        list_header = tk.Frame(list_frame, bg="#161b22")
        list_header.pack(fill=tk.X, pady=(0, 4))

        list_lbl = tk.Label(list_header, text="已记录的标签列表 (Timeline Markers):", font=("Segoe UI", 9), fg="#8b949e", bg="#161b22")
        list_lbl.pack(side=tk.LEFT)

        self.temp_lbl = tk.Label(list_header, text="瞬时温度: --°C", font=("Segoe UI", 9), fg="#f0883e", bg="#161b22")
        self.temp_lbl.pack(side=tk.RIGHT)

        self.tag_listbox = tk.Listbox(list_frame, font=("Consolas", 10), bg="#0d1117", fg="#c9d1d9", selectbackground="#1f6feb", relief=tk.SOLID, bd=1)
        self.tag_listbox.pack(fill=tk.BOTH, expand=True)

    def _toggle_topmost(self):
        cur = self.root.attributes("-topmost")
        self.root.attributes("-topmost", not cur)

    def _check_initial_state(self):
        def _bg():
            try:
                env = self.mgr.adb.prepare_device_env()
                pkg, _ = self.mgr.adb.get_foreground_app()
                self.root.after(0, lambda: self.dev_lbl.config(
                    text=f"设备: {env['model']} (Root: {env['has_root']}) | 当前前台: {pkg or '未检测到'}"
                ))
            except Exception as e:
                self.root.after(0, lambda: self.dev_lbl.config(text=f"ADB 检测失败: {e}"))
            self._load_apps()
        threading.Thread(target=_bg, daemon=True).start()

    def _load_apps(self):
        def _bg():
            apps = self.mgr.adb.get_installed_apps()
            self.installed_apps = apps
            options = ["⚡ [自动锁定当前真机前台应用]"]
            for a in apps:
                icon = "🎮" if a["is_game"] else "📱"
                fg_badge = " [前台运行中]" if a["is_foreground"] else ""
                options.append(f"{icon} {a['name']} ({a['package']}){fg_badge}")
            
            def _update():
                self.app_combo["values"] = options
                if options:
                    # 默认选中第一个或前台游戏
                    sel_idx = 0
                    for idx, a in enumerate(apps, 1):
                        if a["is_foreground"]:
                            sel_idx = idx
                            break
                    self.app_combo.current(sel_idx)
                    self._on_app_selected(None)

            self.root.after(0, _update)
        threading.Thread(target=_bg, daemon=True).start()

    def _on_app_selected(self, event):
        idx = self.app_combo.current()
        if idx <= 0:
            self.launch_var.set(False)
            self.start_btn.config(text="▶ 原地挂载开始收集")
        else:
            self.launch_var.set(True)
            self.start_btn.config(text="🚀 启动游戏并收集")

    def _get_chosen_package(self):
        idx = self.app_combo.current()
        if idx <= 0 or not self.installed_apps:
            return None
        return self.installed_apps[idx - 1]["package"]

    def _on_start(self):
        chosen_pkg = self._get_chosen_package()
        do_launch = self.launch_var.get() and (chosen_pkg is not None)

        self.start_btn.config(state=tk.DISABLED, bg="#21262d")
        self.status_dot.config(text="⏳ 正在初始化...", fg="#d29922")

        def _bg_start():
            try:
                session = self.mgr.start_session(
                    package=chosen_pkg,
                    tag="PerfDogSession",
                    launch=do_launch
                )
                self.root.after(0, lambda: self._on_start_success(session))
            except Exception as e:
                self.root.after(0, lambda: self._on_start_fail(str(e)))

        threading.Thread(target=_bg_start, daemon=True).start()

    def _on_start_success(self, session):
        self.is_running = True
        self.start_time = session["start_time"]

        self.stop_btn.config(state=tk.NORMAL, bg="#da3633")
        self.tag_btn.config(state=tk.NORMAL)
        self.app_combo.config(state="disabled")
        self.launch_chk.config(state="disabled")

        self.status_dot.config(text="● 正在高频采样中", fg="#3fb950")
        self.tag_listbox.delete(0, tk.END)

        self._tick_timer()

    def _on_start_fail(self, err_msg):
        self.start_btn.config(state=tk.NORMAL, bg="#238636")
        self.status_dot.config(text="● 待机中", fg="#8b949e")
        messagebox.showerror("启动失败", err_msg)

    def _tick_timer(self):
        if not self.is_running:
            return
        elapsed = time.time() - self.start_time
        mins = int(elapsed // 60)
        secs = elapsed % 60
        self.timer_lbl.config(text=f"{mins:02d}:{secs:04.1f}")

        # 每 2 秒刷一次瞬时温度
        if int(elapsed * 10) % 20 == 0:
            def _bg_temp():
                try:
                    t_res = self.mgr.adb.shell("cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null")
                    if t_res.ok and t_res.stdout.isdigit():
                        raw = float(t_res.stdout)
                        tc = raw / 1000.0 if raw > 1000 else raw
                        self.root.after(0, lambda: self.temp_lbl.config(text=f"瞬时温度: {tc:.1f}°C"))
                except Exception:
                    pass
            threading.Thread(target=_bg_temp, daemon=True).start()

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
        self.app_combo.config(state="readonly")
        self.launch_chk.config(state="normal")
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
