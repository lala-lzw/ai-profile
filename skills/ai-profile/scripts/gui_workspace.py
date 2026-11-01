"""AiProfile desktop workspace with manual recording and read-only previews."""

from collections import deque
import math
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
import webbrowser

from adb_bridge import AdbBridge
from gpu_metrics import CHARTS, METRICS, OVERVIEW, metric_for
from cli_data import cell_findings
from live_metrics import LiveMetricsReader
from fps_reader import FpsReader, FpsRecorder, SOURCE as FPS_SOURCE
from display_units import format_metric, format_number, scaled_spec
from session_manager import SessionManager

BG, SIDE, CARD, INPUT = "#101b23", "#14232d", "#192a35", "#203541"
LINE, TEXT, MUTED = "#2b4351", "#dce9ee", "#8aa5b3"
ACCENT, GOLD, RED = "#54c9ba", "#e4b66e", "#df7f7d"
COLORS = (ACCENT, GOLD, "#78aadd", "#a5c98b")


def format_value(value, unit="", digits=None):
    return "—" if value is None else str(value)


def clock_text(seconds):
    ticks = max(0, round(seconds*10))
    return f"{ticks//600:02d}:{ticks%600//10:02d}.{ticks%10}"


class LiveChart(tk.Frame):
    def __init__(self, parent, title, unit, series, ceiling=None, x_field="source_line"):
        super().__init__(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        self.unit, self.series, self.ceiling = unit, series, ceiling
        self.x_field = x_field
        self.period_ms = 200
        self.readable_units = True
        self.history, self.markers, self.hidden = [], [], set()
        self.window_s = 300
        self.waiting = "尚未开始采样 · 点击左侧开始"
        heading = tk.Frame(self, bg=CARD)
        heading.pack(fill=tk.X, padx=18, pady=(12, 2))
        tk.Label(heading, text=title, bg=CARD, fg=TEXT,
                 font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT)
        self.value_label = tk.Label(heading, text="—", bg=CARD, fg=ACCENT, font=("Consolas", 11))
        self.value_label.pack(side=tk.RIGHT)
        self.canvas = tk.Canvas(self, bg=CARD, height=174, highlightthickness=0)
        self.canvas.pack(fill=tk.X, padx=8)
        legend = tk.Frame(self, bg=CARD)
        legend.pack(fill=tk.X, padx=18, pady=(0, 10))
        for index, (key, label) in enumerate(series):
            color = COLORS[index % len(COLORS)]
            button = tk.Button(legend, text=label, bg=CARD, fg=color,
                               activebackground=CARD, activeforeground=TEXT, bd=0,
                               cursor="hand2", font=("Segoe UI", 9), wraplength=300, justify=tk.LEFT)
            button.configure(command=lambda k=key, b=button, c=color: self.toggle(k, b, c))
            button.grid(row=index//2,column=index%2,sticky="w",padx=(0,20),pady=2)
        legend.columnconfigure((0,1),weight=1)
        self.canvas.bind("<Configure>", lambda event: self.draw())
        self.canvas.bind("<Motion>", self.hover)
        self.canvas.bind("<Leave>", lambda event: self.canvas.delete("hover"))

    def toggle(self, key, button, color):
        if key in self.hidden:
            self.hidden.remove(key)
        else:
            self.hidden.add(key)
        button.configure(fg=MUTED if key in self.hidden else color)
        self.draw()

    def set_data(self, history, markers, window_s, waiting, period_ms=200):
        self.history, self.markers = list(history), markers
        self.window_s, self.waiting = window_s, waiting
        self.period_ms = period_ms
        latest = self.history[-1] if self.history else {}
        self.value_label.configure(text=" / ".join(format_metric(key,latest.get("cli_raw",{}).get(key),readable=self.readable_units)
                                                   for key, _ in self.series))
        self.draw()

    def elapsed_at(self, position):
        return position if self.x_field=="elapsed_s" else max(0,(position-2)*self.period_ms/1000)

    def bounds(self):
        if self.x_field == "elapsed_s":
            end = max(self.window_s or 1, self.history[-1][self.x_field] if self.history else 0)
            return max(0, end-self.window_s) if self.window_s else 0, end
        end = self.history[-1][self.x_field] if self.history else self.window_s or 300
        start = max(2,end-self.window_s+1) if self.window_s else self.history[0][self.x_field] if self.history else 2
        return start,max(start+1,end)

    def draw(self):
        canvas = self.canvas
        canvas.delete("all")
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if width < 100:
            return
        left, right, top, bottom = 145, width - 20, 16, height - 28
        start, end = self.bounds()
        visible = [sample for sample in self.history if start <= sample[self.x_field] <= end]
        values = [sample.get("cli_metrics",{}).get(key) for sample in visible for key,_ in self.series
                  if key not in self.hidden and sample.get("cli_metrics",{}).get(key) is not None]
        minimum,maximum = min(values+[0]),max(values+[0])
        if maximum==minimum: maximum=minimum+1
        scale = maximum+(maximum-minimum)*.05
        spec = scaled_spec(self.series[0][0],max(abs(minimum),abs(maximum))) if self.readable_units else {"divisor":1,"unit":""}
        x = lambda value: left + (value - start) / max(1, end - start) * (right - left)
        y = lambda value: bottom - (value-minimum) / (scale-minimum) * (bottom - top)
        for index in range(4):
            value = minimum+(scale-minimum) * index / 3
            py = y(value)
            canvas.create_line(left, py, right, py, fill=LINE)
            canvas.create_text(left - 10, py, anchor="e", text=format_number(value/spec["divisor"]) if self.readable_units else format(value,".8g"),
                               fill=MUTED, font=("Segoe UI", 8))
        canvas.create_text(8, 5, anchor="nw", text=spec["unit"] or "CLI raw", fill=MUTED, font=("Segoe UI", 8))
        for index in range(6):
            value = start + (end - start) * index / 5
            canvas.create_text(x(value), bottom + 16,
                               anchor="w" if index == 0 else "e" if index == 5 else "center",
                               text=clock_text(self.elapsed_at(value)),
                               fill=MUTED, font=("Consolas", 8))
        for marker in self.markers:
            moment=marker.get("source_line")
            if moment is not None and start<=moment<=end:
                px=x(moment)
                canvas.create_line(px,top,px,bottom,fill="#527e87",dash=(3,4))
                canvas.create_text(px,top+3,anchor="n",text=marker.get("name","")[:12],fill=MUTED,font=("Segoe UI",8))
        found = False
        for index, (key, _) in enumerate(self.series):
            if key in self.hidden:
                continue
            points = []
            for sample in visible:
                value = sample.get("cli_metrics",{}).get(key)
                if value is None:
                    if len(points) >= 4:
                        canvas.create_line(*points, fill=COLORS[index % len(COLORS)], width=2)
                    points = []
                    continue
                found = True
                points.extend((x(sample[self.x_field]), y(value)))
            if len(points) >= 4:
                canvas.create_line(*points, fill=COLORS[index % len(COLORS)], width=2)
            elif len(points) == 2:
                px, py = points
                canvas.create_oval(px - 2, py - 2, px + 2, py + 2, fill=COLORS[index % len(COLORS)], outline="")
        if not found:
            text = "点击图例显示曲线" if len(self.hidden) == len(self.series) else self.waiting
            canvas.create_text((left + right) / 2, (top + bottom) / 2,
                               text=text, fill=MUTED, font=("Segoe UI", 10))

    def hover(self, event):
        self.canvas.delete("hover")
        if not self.history:
            return
        start, end = self.bounds()
        width = self.canvas.winfo_width()
        moment = start + min(1, max(0, (event.x - 145) / max(1, width - 165))) * (end - start)
        visible = [sample for sample in self.history if start <= sample[self.x_field] <= end]
        if not visible:
            return
        sample = min(visible, key=lambda item: abs(item[self.x_field] - moment))
        prefix = clock_text(self.elapsed_at(sample[self.x_field]))
        if self.x_field!="elapsed_s":
            prefix += f"（估算） · CSV L{sample['source_line']}"
        text = prefix + "   " + "   ".join(
            f"{label}: {format_value(sample.get('cli_raw',{}).get(key))}" for key, label in self.series
            if key not in self.hidden)
        self.canvas.create_line(event.x, 14, event.x, self.canvas.winfo_height() - 28,
                                fill="#7396a5", dash=(3, 3), tags="hover")
        self.canvas.create_text(width - 20, 7, text=text, anchor="ne", fill=TEXT,
                                font=("Segoe UI", 9), tags="hover")


class PerfDogGui:
    def __init__(self, root, manager=None, *, monitor=True):
        self.root, self.mgr, self.monitor = root, manager or SessionManager(), monitor
        self.state, self.session = "idle", None
        self.markers, self.installed_apps, self.devices = [], [], []
        self.history = deque(maxlen=18000)
        self.fps_history = deque(maxlen=18000)
        self.last_fps = None
        self.events = queue.Queue()
        self.poll_stop = threading.Event()
        self.preview_thread = None
        self.generation = 0
        self.closed, self.display_paused = False, False
        self.start_time, self.elapsed = 0, 0
        self.sample_period_ms = 200
        self.report_path = None
        self.last_cli = {}
        self.last_source_line = None
        root.title("AiProfile · GPU 性能工作台")
        root.configure(bg=BG)
        root.minsize(1060, 700)
        width, height = min(1360, root.winfo_screenwidth()-80), min(880, root.winfo_screenheight()-100)
        root.geometry(f"{width}x{height}+{max(0,(root.winfo_screenwidth()-width)//2)}+{max(0,(root.winfo_screenheight()-height)//2)}")
        self._build_ui()
        self._restore_session()
        root.protocol("WM_DELETE_WINDOW", self._close)
        root.after(80, self._drain_events)
        root.after(100, self._tick)
        if monitor:
            self._refresh_devices()
            self._background("recent_report", self._find_recent_report)
        self._sync_controls()
        self._draw_charts()

    def _label(self, parent, text, *, fg=TEXT, font=None, **kwargs):
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=fg,
                        font=font or ("Segoe UI", 9), **kwargs)

    def _button(self, parent, text, command, *, primary=False):
        return tk.Button(parent, text=text, command=command, bg=ACCENT if primary else INPUT,
                         fg=BG if primary else TEXT, activebackground="#77d6c9" if primary else LINE,
                         activeforeground=BG if primary else TEXT, disabledforeground="#587381",
                         relief=tk.FLAT, bd=0, cursor="hand2", padx=12, pady=7,
                         font=("Segoe UI", 9, "bold" if primary else "normal"))

    def _check(self, parent, text, variable, command=None):
        return tk.Checkbutton(parent, text=text, variable=variable, command=command,
                              bg=parent.cget("bg"), fg=MUTED, selectcolor=INPUT,
                              activebackground=parent.cget("bg"), activeforeground=TEXT,
                              font=("Segoe UI", 9), bd=0, highlightthickness=0)

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=INPUT, background=INPUT, foreground=TEXT,
                        arrowcolor=MUTED, bordercolor=LINE, padding=5)
        style.map("TCombobox", fieldbackground=[("readonly", INPUT), ("disabled", SIDE)],
                  foreground=[("readonly", TEXT), ("disabled", MUTED)], selectbackground=[("readonly", INPUT)])
        style.configure("TNotebook", background=SIDE, borderwidth=0)
        style.configure("TNotebook.Tab", background=SIDE, foreground=MUTED, padding=(16, 8))
        style.map("TNotebook.Tab", background=[("selected", INPUT)], foreground=[("selected", ACCENT)])
        style.configure("Info.Treeview", background=SIDE, fieldbackground=SIDE, foreground=TEXT,
                        borderwidth=0, rowheight=27, font=("Segoe UI", 9))
        style.configure("Vertical.TScrollbar", background=LINE, troughcolor=BG, bordercolor=BG,
                        arrowcolor=MUTED)
        top = tk.Frame(self.root, bg=SIDE, padx=22, pady=13)
        top.pack(fill=tk.X)
        self._label(top, "∿", fg=ACCENT, font=("Segoe UI", 23, "bold")).pack(side=tk.LEFT, padx=(0,9))
        self._label(top, "AiProfile", font=("Segoe UI", 17, "bold")).pack(side=tk.LEFT)
        self._label(top, "  /  GPU 性能工作台", fg=MUTED, font=("Segoe UI", 11)).pack(side=tk.LEFT, padx=6)
        self.topmost_var = tk.BooleanVar(value=False)
        self._check(top, "窗口置顶", self.topmost_var,
                    lambda: self.root.attributes("-topmost", self.topmost_var.get())).pack(side=tk.RIGHT)
        self.connection_label = self._label(top, "●  检测设备中", fg=MUTED)
        self.connection_label.pack(side=tk.RIGHT, padx=20)
        body = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg=BG, sashwidth=6, bd=0)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=(12,0))
        sidebar = tk.Frame(body, bg=SIDE)
        body.add(sidebar, width=310, minsize=286, stretch="never")
        self.side_canvas = tk.Canvas(sidebar, bg=SIDE, highlightthickness=0, width=290)
        side_scroll = ttk.Scrollbar(sidebar, orient=tk.VERTICAL, command=self.side_canvas.yview)
        self.side_canvas.configure(yscrollcommand=side_scroll.set)
        side_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.side_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        side = tk.Frame(self.side_canvas, bg=SIDE, padx=14, pady=14)
        side_window = self.side_canvas.create_window((0,0),window=side,anchor="nw")
        self.side_frame = side
        side.bind("<Configure>",lambda event:self.side_canvas.configure(scrollregion=self.side_canvas.bbox("all")))
        self.side_canvas.bind("<Configure>",lambda event:self.side_canvas.itemconfigure(side_window,width=event.width))
        workspace = tk.Frame(body, bg=BG)
        body.add(workspace, minsize=720, stretch="always")
        header = tk.Frame(side, bg=SIDE)
        header.pack(fill=tk.X, pady=(0,8))
        self._label(header, "设备与目标应用", font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT)
        self.refresh_btn = self._button(header, "刷新", self._refresh_devices)
        self.refresh_btn.pack(side=tk.RIGHT)
        self.device_combo = ttk.Combobox(side, state="readonly", font=("Segoe UI", 9))
        self.device_combo.pack(fill=tk.X, pady=(0,10))
        self.device_combo.bind("<<ComboboxSelected>>", self._on_device_selected)
        self.app_combo = ttk.Combobox(side, state="readonly", font=("Segoe UI", 9))
        self.app_combo.pack(fill=tk.X)
        self.app_combo.bind("<<ComboboxSelected>>", self._on_app_selected)
        self.package_label = self._label(side, "连接设备后选择应用", fg=MUTED, anchor="w",
                                         justify=tk.LEFT, wraplength=254)
        self.package_label.pack(fill=tk.X, pady=(6,4))
        self.launch_var = tk.BooleanVar(value=False)
        self.launch_chk = self._check(side, "开始时在手机上启动所选应用", self.launch_var)
        self.launch_chk.pack(anchor="w", pady=(0,12))
        notebook = ttk.Notebook(side)
        notebook.pack(fill=tk.X, pady=(0,14))
        device_tab = tk.Frame(notebook, bg=SIDE)
        settings = tk.Frame(notebook, bg=SIDE, padx=8, pady=10)
        notebook.add(device_tab, text="设备信息")
        notebook.add(settings, text="采样设置")
        self.device_info = ttk.Treeview(device_tab, columns=("name","value"), show="", height=6,
                                       style="Info.Treeview", selectmode="none")
        self.device_info.column("name", width=82, stretch=False)
        self.device_info.column("value", width=160, stretch=True)
        self.device_info.pack(fill=tk.X, pady=8)
        for key,label in (("model","型号"),("android","Android"),("graphics_api","图形 API"),("serial","序列号"),
                          ("resolution","分辨率"),("temperature","设备温度")):
            self.device_info.insert("",tk.END,iid=key,values=(label,"—"))
        self.tag_var, self.period_var = tk.StringVar(value="AiProfileSession"), tk.StringVar(value="200")
        self._label(settings,"会话名称",fg=MUTED).grid(row=0,column=0,sticky="w",pady=5)
        self.tag_input = tk.Entry(settings,textvariable=self.tag_var,bg=INPUT,fg=TEXT,insertbackground=TEXT,bd=0,width=17)
        self.tag_input.grid(row=0,column=1,sticky="ew",padx=(8,0),ipady=5)
        self._label(settings,"采样间隔 ms",fg=MUTED).grid(row=1,column=0,sticky="w",pady=5)
        self.period_input = ttk.Combobox(settings,textvariable=self.period_var,values=("200","500","1000"),state="readonly",width=14)
        self.period_input.grid(row=1,column=1,sticky="ew",padx=(8,0))
        settings.columnconfigure(1,weight=1)
        self.auto_open_var = tk.BooleanVar(value=True)
        self._check(settings,"结束后打开分析报告",self.auto_open_var).grid(row=3,column=0,columnspan=2,sticky="w",pady=(8,0))
        control = tk.Frame(side,bg=INPUT,padx=14,pady=12)
        control.pack(fill=tk.X,pady=(0,14))
        self.status_label = self._label(control,"●  未开始采样",fg=MUTED)
        self.status_label.pack(anchor="w")
        self.timer_label = self._label(control,"00:00.0",font=("Consolas",27,"bold"))
        self.timer_label.pack(anchor="w",pady=(4,10))
        buttons = tk.Frame(control,bg=INPUT)
        buttons.pack(fill=tk.X)
        buttons.columnconfigure((0,1),weight=1)
        self.start_btn = self._button(buttons,"▶ 开始采样",self._on_start,primary=True)
        self.start_btn.grid(row=0,column=0,sticky="ew",padx=(0,4))
        self.stop_btn = self._button(buttons,"■ 结束采样",self._on_stop)
        self.stop_btn.grid(row=0,column=1,sticky="ew",padx=(4,0))
        tag_head = tk.Frame(side,bg=SIDE)
        tag_head.pack(fill=tk.X,pady=(0,8))
        self._label(tag_head,"阶段标签",font=("Segoe UI",10,"bold")).pack(side=tk.LEFT)
        self.marker_count = self._label(tag_head,"0 个",fg=MUTED)
        self.marker_count.pack(side=tk.RIGHT)
        tag_row = tk.Frame(side,bg=SIDE)
        tag_row.pack(fill=tk.X)
        self.tag_entry = tk.Entry(tag_row,bg=INPUT,fg=TEXT,insertbackground=TEXT,font=("Segoe UI",10),bd=0)
        self.tag_entry.pack(side=tk.LEFT,fill=tk.X,expand=True,ipady=8,padx=(0,6))
        self.tag_entry.bind("<Return>",lambda event:self._on_add_tag())
        self.tag_btn = self._button(tag_row,"+ 标记",self._on_add_tag)
        self.tag_btn.pack(side=tk.RIGHT)
        self.preset_buttons = []
        presets = tk.Frame(side,bg=SIDE)
        presets.pack(fill=tk.X,pady=8)
        for index,title in enumerate(("进入场景","战斗开始","特效爆发","切换画质")):
            button = self._button(presets,title,lambda value=title:self._quick_tag(value))
            button.grid(row=index//2,column=index%2,sticky="ew",padx=2,pady=2)
            self.preset_buttons.append(button)
        presets.columnconfigure((0,1),weight=1)
        self.tag_listbox = tk.Listbox(side,bg=BG,fg=TEXT,bd=0,highlightthickness=0,
                                      selectbackground=INPUT,height=4,font=("Segoe UI",9))
        self.tag_listbox.pack(fill=tk.BOTH,expand=True,pady=(0,4))
        toolbar = tk.Frame(workspace,bg=BG)
        toolbar.pack(fill=tk.X,padx=(6,4),pady=(0,12))
        self._label(toolbar,"GPU CLI 原始样本",font=("Segoe UI",13,"bold")).pack(side=tk.LEFT)
        self.preview_label = self._label(toolbar,"横轴时间 · GPU 按间隔估算",fg=MUTED)
        self.preview_label.pack(side=tk.LEFT,padx=14)
        self.report_btn = self._button(toolbar,"打开报告 ↗",self._open_report)
        self.report_btn.pack(side=tk.RIGHT)
        self.pause_btn = self._button(toolbar,"暂停曲线",self._toggle_pause)
        self.pause_btn.pack(side=tk.RIGHT,padx=8)
        tiles = tk.Frame(workspace,bg=BG)
        tiles.pack(fill=tk.X,padx=6,pady=(0,12))
        self.metric_labels = {}
        for index,column in enumerate(["FPS"]+[metric.column for metric in OVERVIEW[:4]]):
            key,title = column,column
            tile = tk.Frame(tiles,bg=CARD,padx=15,pady=13,highlightbackground=LINE,highlightthickness=1)
            tile.grid(row=0,column=index,sticky="nsew",padx=(0 if index==0 else 8,0))
            tiles.columnconfigure(index,weight=1)
            self._label(tile,title,fg=MUTED,wraplength=150,justify=tk.LEFT).pack(anchor="w")
            value = self._label(tile,"—",fg=COLORS[index % len(COLORS)],font=("Consolas",18,"bold"))
            value.pack(anchor="w",pady=(7,0))
            self.metric_labels[key] = value
        options = tk.Frame(workspace,bg=BG)
        options.pack(fill=tk.X,padx=8,pady=(0,10))
        self.group_var = tk.StringVar(value="GPU")
        for name in ("GPU","Shader","停顿 / 缓存","访存","系统","全部"):
            tk.Radiobutton(options,text=name,value=name,variable=self.group_var,command=self._filter_charts,
                           bg=BG,fg=MUTED,selectcolor=INPUT,activebackground=BG,activeforeground=ACCENT,
                           indicatoron=False,bd=0,padx=12,pady=6,font=("Segoe UI",9)).pack(side=tk.LEFT,padx=(0,4))
        self.window_var = tk.StringVar(value="最近 60 秒")
        window_box = ttk.Combobox(options,textvariable=self.window_var,values=("最近 60 秒","最近 180 秒","全程"),state="readonly",width=13)
        window_box.pack(side=tk.RIGHT)
        window_box.bind("<<ComboboxSelected>>",lambda event:self._draw_charts(force=True))
        self._label(options,"时间窗口",fg=MUTED).pack(side=tk.RIGHT,padx=10)
        self.readable_var=tk.BooleanVar(value=True)
        self._check(options,"易读单位",self.readable_var,self._refresh_units).pack(side=tk.RIGHT,padx=8)
        self.data_tabs = ttk.Notebook(workspace)
        self.data_tabs.pack(fill=tk.BOTH,expand=True,padx=(6,0))
        plot_tab = tk.Frame(self.data_tabs,bg=BG)
        raw_tab = tk.Frame(self.data_tabs,bg=BG,padx=10,pady=10)
        self.data_tabs.add(plot_tab,text="GPU 指标曲线")
        self.data_tabs.add(raw_tab,text="CLI 全量指标")
        raw_head = tk.Frame(raw_tab,bg=BG)
        raw_head.pack(fill=tk.X,pady=(0,10))
        self.raw_count = self._label(raw_head,"等待 CLI 数据",fg=MUTED)
        self.raw_count.pack(side=tk.LEFT)
        self.raw_search = tk.StringVar()
        raw_entry = tk.Entry(raw_head,textvariable=self.raw_search,bg=INPUT,fg=TEXT,
                             insertbackground=TEXT,bd=0,width=28)
        raw_entry.pack(side=tk.RIGHT,ipady=5)
        self._label(raw_head,"搜索指标",fg=MUTED).pack(side=tk.RIGHT,padx=8)
        raw_body = tk.Frame(raw_tab,bg=BG)
        raw_body.pack(fill=tk.BOTH,expand=True)
        style.configure("Info.Treeview.Heading",background=INPUT,foreground=TEXT,font=("Segoe UI",9,"bold"))
        self.raw_table = ttk.Treeview(raw_body,columns=("source","raw","review"),
                                     show="headings",style="Info.Treeview")
        for column,title,width in (("source","CLI 原始列名",360),("raw","CLI 原始值",230),("review","核查提示",340)):
            self.raw_table.heading(column,text=title)
            self.raw_table.column(column,width=width,minwidth=100,anchor="w" if column=="source" else "e")
        raw_scroll = ttk.Scrollbar(raw_body,orient=tk.VERTICAL,command=self.raw_table.yview)
        raw_xscroll = ttk.Scrollbar(raw_tab,orient=tk.HORIZONTAL,command=self.raw_table.xview)
        self.raw_table.tag_configure("review",foreground=GOLD)
        self.raw_table.configure(yscrollcommand=raw_scroll.set,xscrollcommand=raw_xscroll.set)
        raw_scroll.pack(side=tk.RIGHT,fill=tk.Y)
        self.raw_table.pack(fill=tk.BOTH,expand=True)
        raw_xscroll.pack(fill=tk.X)
        self.raw_search.trace_add("write",lambda *args:self._update_raw_table())
        chart_area = tk.Frame(plot_tab,bg=BG)
        chart_area.pack(fill=tk.BOTH,expand=True,padx=(6,0))
        self.chart_canvas = tk.Canvas(chart_area,bg=BG,highlightthickness=0)
        scroll = ttk.Scrollbar(chart_area,orient=tk.VERTICAL,command=self.chart_canvas.yview)
        self.chart_canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT,fill=tk.Y)
        self.chart_canvas.pack(side=tk.LEFT,fill=tk.BOTH,expand=True)
        self.chart_holder = tk.Frame(self.chart_canvas,bg=BG)
        chart_window = self.chart_canvas.create_window((0,0),window=self.chart_holder,anchor="nw")
        self.chart_holder.bind("<Configure>",lambda event:self.chart_canvas.configure(scrollregion=self.chart_canvas.bbox("all")))
        self.chart_canvas.bind("<Configure>",lambda event:self.chart_canvas.itemconfigure(chart_window,width=event.width))
        self.root.bind("<MouseWheel>",self._scroll)
        self.charts = []
        self.fps_chart = LiveChart(self.chart_holder,"FPS · SurfaceFlinger", "FPS", (("FPS","FPS · SurfaceFlinger"),), x_field="elapsed_s")
        for chart_id,section,title,unit,ceiling in CHARTS:
            series = tuple((metric.key,metric.label) for metric in METRICS if metric.chart==chart_id)
            chart = LiveChart(self.chart_holder,title,unit,series,ceiling)
            self.charts.append((section,chart))
        self._filter_charts()
        bottom = tk.Frame(self.root,bg=SIDE,padx=18,pady=7)
        bottom.pack(fill=tk.X)
        self.log_label = self._label(bottom,"连接设备，选择应用后点击开始采样。",fg=MUTED,anchor="w")
        self.log_label.pack(side=tk.LEFT,fill=tk.X,expand=True)
        self.frequency_label = self._label(bottom,"CLI 来源行 —",fg=MUTED)
        self.frequency_label.pack(side=tk.RIGHT)

    def _background(self, kind, function):
        def worker():
            try:
                self.events.put((kind,function(),None))
            except Exception as error:
                self.events.put((kind,None,str(error)))
        threading.Thread(target=worker,daemon=True).start()

    def _drain_events(self):
        if self.closed:
            return
        for _ in range(100):
            try:
                kind,result,error = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "devices": self._on_devices(result or [],error)
            elif kind == "apps": self._on_apps(result,error)
            elif kind == "start": self._on_start_fail(error) if error else self._on_start_success(result)
            elif kind == "stop": self._on_stop_fail(error) if error else self._on_stop_done(result)
            elif kind == "sample": self._on_sample(result)
            elif kind == "preview_error":
                generation,text = result
                if generation == self.generation and self.state == "recording":
                    self.log_label.configure(text=f"预览连接异常：{text[:100]} · 采样状态未改变",fg=GOLD)
            elif kind == "recent_report" and not error and result and not self.report_path:
                self.report_path = result
                self._sync_controls()
        self.root.after(100,self._drain_events)

    def _refresh_devices(self):
        if self.state in ("starting","recording","stopping"):
            return
        self.refresh_btn.configure(state=tk.DISABLED)
        self.connection_label.configure(text="●  检测设备中",fg=MUTED)
        def discover():
            result = AdbBridge().run("devices","-l",timeout=6)
            if not result.ok:
                raise RuntimeError(result.stderr or result.stdout)
            devices = []
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts)>1 and parts[1]=="device":
                    model = next((part.split(":",1)[1] for part in parts if part.startswith("model:")),parts[0])
                    devices.append({"serial":parts[0],"model":model})
            return devices
        self._background("devices",discover)

    def _on_devices(self, devices, error):
        self.devices = devices
        self.device_combo["values"] = [f"{item['model']} · {item['serial']}" for item in devices]
        if devices:
            index = next((i for i,item in enumerate(devices) if item["serial"]==self.mgr.adb.serial),0)
            self.device_combo.current(index)
            if self.state != "recording": self._on_device_selected()
            self.connection_label.configure(text=f"●  {devices[index]['model']}",fg=ACCENT)
        else:
            self.device_combo.set("未检测到已授权设备")
            self.app_combo.set("等待设备连接")
            self.connection_label.configure(text="●  设备未连接",fg=GOLD)
            self.log_label.configure(text=error or "未检测到已授权设备；连接手机后点击刷新。",fg=GOLD)
        self._sync_controls()

    def _on_device_selected(self, event=None):
        index = self.device_combo.current()
        if index<0 or self.state in ("starting","recording","stopping"):
            return
        device = self.devices[index]
        self.mgr.adb = AdbBridge(device["serial"])
        self.mgr.collector.adb = self.mgr.adb
        self._set_device_info("serial",device["serial"])
        self._set_device_info("model",device["model"])
        self.app_combo["values"] = ()
        self.app_combo.set("读取应用列表中…")
        self.installed_apps = []
        serial = device["serial"]
        def load():
            bridge = AdbBridge(serial)
            model = bridge.shell("getprop ro.product.model",timeout=5).stdout
            android = bridge.shell("getprop ro.build.version.release",timeout=5).stdout
            graphics_api = bridge.get_graphics_api(timeout=5)
            resolution = bridge.shell("wm size",timeout=5).stdout.splitlines()
            return {"serial":serial,"model":model,"android":android,"graphics_api":graphics_api,
                    "resolution":resolution[-1].partition(":")[2].strip() if resolution else "—",
                    "apps":bridge.get_installed_apps(force_refresh=True)}
        self._background("apps",load)
        self._sync_controls()

    def _on_apps(self, result, error):
        if error:
            self.app_combo.set("读取失败，请刷新重试")
            self.log_label.configure(text=f"读取应用失败：{error[:100]}",fg=GOLD)
            return
        if result["serial"] != self.mgr.adb.serial: return
        self.installed_apps = result["apps"]
        self.app_combo["values"] = ["自动锁定前台应用"] + [
            f"{app['name']}{'  [前台]' if app['is_foreground'] else ''}" for app in self.installed_apps]
        index = next((i for i,app in enumerate(self.installed_apps,1) if app["is_foreground"]),0)
        self.app_combo.current(index)
        for key in ("model","android","graphics_api","serial","resolution"):
            self._set_device_info(key,result.get(key))
        self._on_app_selected()
        self.log_label.configure(text="设备已就绪。点击开始后采集完整硬件数据，并显示实时预览。",fg=MUTED)
        self._sync_controls()

    def _set_device_info(self, key, value):
        label = self.device_info.item(key,"values")[0]
        self.device_info.item(key,values=(label,value or "—"))

    def _get_chosen_package(self):
        index = self.app_combo.current()-1
        return self.installed_apps[index]["package"] if 0<=index<len(self.installed_apps) else None

    def _on_app_selected(self, event=None):
        package = self._get_chosen_package()
        self.package_label.configure(text=package or "原地采集手机当前前台应用")
        self.launch_var.set(package is not None)

    def _sync_controls(self):
        busy = self.state in ("starting","recording","stopping")
        ready = bool(self.devices) and self.app_combo.current()>=0
        self.start_btn.configure(state=tk.NORMAL if not busy and ready else tk.DISABLED)
        self.stop_btn.configure(state=tk.NORMAL if self.state=="recording" else tk.DISABLED)
        for widget in (self.device_combo,self.app_combo,self.period_input):
            widget.configure(state="disabled" if busy else "readonly")
        for widget in (self.launch_chk,self.tag_input,self.refresh_btn):
            widget.configure(state=tk.DISABLED if busy else tk.NORMAL)
        for widget in (self.tag_entry,self.tag_btn,*self.preset_buttons):
            widget.configure(state=tk.NORMAL if self.state=="recording" else tk.DISABLED)
        self.report_btn.configure(state=tk.NORMAL if self.report_path else tk.DISABLED)
        self.pause_btn.configure(state=tk.NORMAL if self.history or self.state=="recording" else tk.DISABLED)

    def _on_start(self):
        if self.state in ("starting","recording","stopping"): return
        try:
            period = int(self.period_var.get())
            tag = self.tag_var.get().strip() or "AiProfileSession"
            if period<=0:
                raise ValueError("采样间隔必须为正数。")
            if any(char in tag for char in '<>:"/\\|?*') or tag in (".",".."):
                raise ValueError("会话名称不能含有路径分隔符或文件名特殊字符。")
        except ValueError as error:
            messagebox.showerror("采样设置无效",str(error),parent=self.root)
            return
        package = self._get_chosen_package()
        launch = bool(package) and self.launch_var.get()
        self.state = "starting"
        self.status_label.configure(text="●  正在初始化设备…",fg=GOLD)
        self._sync_controls()
        self._background("start",lambda:self.mgr.start_session(package=package,tag=tag,launch=launch,period_ms=period))

    def _on_start_success(self, session):
        self.session, self.state = session,"recording"
        self.sample_period_ms = session.get("period_ms", 200)
        self.markers = list(session.get("labels",[]))
        self.start_time = session["start_time"]
        self.elapsed = max(0,time.time()-self.start_time)
        self.history.clear()
        self.fps_history.clear()
        self.last_fps = None
        self.metric_labels["FPS"].configure(text="—")
        self.last_cli = {}
        self.last_source_line = None
        self._update_raw_table()
        self.display_paused = False
        self.pause_btn.configure(text="暂停曲线")
        self.tag_listbox.delete(0,tk.END)
        for marker in self.markers:
            self.tag_listbox.insert(tk.END,f"{clock_text(marker['time_s'])}   {marker['name']}")
        self.marker_count.configure(text=f"{len(self.markers)} 个")
        self.package_label.configure(text=session["package"])
        model = session.get("device_env",{}).get("model","已连接设备")
        self.connection_label.configure(text=f"●  {model}",fg=ACCENT)
        self._set_device_info("model",model)
        self._set_device_info("android",session.get("device_env",{}).get("android"))
        self._set_device_info("graphics_api",session.get("device_env",{}).get("graphics_api"))
        self._set_device_info("serial",session.get("serial") or self.mgr.adb.serial)
        self.status_label.configure(text="●  正在采样",fg=ACCENT)
        self.preview_label.configure(text="横轴时间 · GPU 按间隔估算")
        self.log_label.configure(text="采样已开始。可回车打标；右侧图表显示最近时段。",fg=MUTED)
        self._sync_controls()
        self._draw_charts(force=True)
        if self.monitor: self._start_preview()

    def _on_start_fail(self, error):
        self.state = "idle"
        self.status_label.configure(text="●  启动失败",fg=RED)
        self._sync_controls()
        messagebox.showerror("启动失败",error,parent=self.root)

    def _restore_session(self):
        session = self.mgr.get_current_session()
        if session:
            if session.get("serial"): self.mgr.adb.serial = session["serial"]
            self._on_start_success(session)
            self.log_label.configure(text="已恢复正在进行的采样会话；此前原始数据和标签保留。",fg=ACCENT)

    def _start_preview(self):
        self.poll_stop.set()
        self.poll_stop = threading.Event()
        stop,session = self.poll_stop,dict(self.session)
        self.generation += 1
        generation = self.generation
        reader = LiveMetricsReader(AdbBridge(self.mgr.adb.serial))
        fps_reader = FpsReader(AdbBridge(self.mgr.adb.serial), session["package"])
        fps_recorder = FpsRecorder(session["output_dir"], session["start_time"])
        def poll():
            while not stop.is_set():
                tick_start = time.monotonic()
                snapshot = {"counter_ready":False,"cli_metrics":{},"cli_raw":{}}
                try:
                    snapshot = reader.read(session)
                except Exception as error:
                    self.events.put(("preview_error",(generation,str(error)),None))
                try:
                    measurement = fps_reader.read()
                    elapsed = max(0,time.time()-session["start_time"])
                    if stop.is_set():
                        break
                    fps_recorder.append(measurement, elapsed)
                    snapshot["fps_sample"],snapshot["fps_elapsed_s"] = measurement,elapsed
                except Exception as error:
                    snapshot["fps_sample"] = {"fps":None,"source":FPS_SOURCE,"status":"unavailable","layer":""}
                    snapshot["fps_elapsed_s"] = max(0,time.time()-session["start_time"])
                    self.events.put(("preview_error",(generation,f"FPS: {error}"),None))
                if stop.is_set():
                    break
                self.events.put(("sample",(generation,snapshot),None))
                stop.wait(max(0.05,1-(time.monotonic()-tick_start)))
        self.preview_thread = threading.Thread(target=poll,daemon=True)
        self.preview_thread.start()

    def _on_sample(self, result):
        generation,snapshot = result
        if generation!=self.generation or self.state!="recording": return
        if "fps_sample" in snapshot:
            measurement = snapshot["fps_sample"]
            value = measurement.get("fps")
            self.last_fps = measurement
            self.metric_labels["FPS"].configure(text="—" if value is None else f"{value:.2f}")
            self.fps_history.append({"elapsed_s":snapshot["fps_elapsed_s"],"cli_metrics":{"FPS":value},
                                     "cli_raw":{"FPS":"—" if value is None else repr(value)}})
            self._draw_fps()
        if not snapshot.get("counter_ready") or snapshot.get("source_line") is None:
            self.log_label.configure(text="等待 CLI 写入完整原始行… · FPS 来源：SurfaceFlinger",fg=MUTED)
            return
        self.last_cli = snapshot.get("cli_raw",{})
        source_line = snapshot["source_line"]
        if snapshot.get("reset_stream"):
            self.history.clear()
        for sample in snapshot.get("samples",[snapshot]):
            if not self.history or sample["source_line"]>self.history[-1]["source_line"]:
                self.history.append(sample)
            elif sample["source_line"]==self.history[-1]["source_line"]:
                self.history[-1]=sample
        self.last_source_line = source_line
        for key,label in self.metric_labels.items():
            if key!="FPS": label.configure(text=format_metric(key,self.last_cli.get(key),readable=self.readable_var.get()))
        self._update_raw_table()
        self.frequency_label.configure(text=f"CLI 来源行 {source_line}")
        findings = snapshot.get("findings",[])
        self.log_label.configure(text=f"CSV 第 {source_line} 行 · {len(findings)} 项待核实 · 原值保留" if findings else f"CSV 第 {source_line} 行 · 已补齐新增原始样本",fg=GOLD if findings else MUTED)
        self._sync_controls()
        self._draw_charts()

    def _on_stop(self):
        if self.state!="recording": return
        self.state = "stopping"
        self.poll_stop.set()
        self.generation += 1
        self.status_label.configure(text="●  正在生成报告…",fg=GOLD)
        self.log_label.configure(text="正在停止采样、拉取原始数据并生成离线报告…",fg=GOLD)
        self._sync_controls()
        def finish():
            if self.preview_thread:
                self.preview_thread.join(timeout=10)
            return self.mgr.stop_session()
        self._background("stop",finish)

    def _on_stop_fail(self, error):
        session = self.mgr.get_current_session()
        self.state = "recording" if session else "idle"
        self.status_label.configure(text="●  结束失败，可重试" if session else "●  报告生成失败",fg=RED)
        if session and self.monitor: self._start_preview()
        self._sync_controls()
        messagebox.showerror("结束采样失败",error,parent=self.root)

    def _on_stop_done(self, result):
        self.state,self.session = "completed",None
        self.report_path = Path(result["timeline_html"])
        self.status_label.configure(text="●  采样完成",fg=ACCENT)
        self.log_label.configure(text=f"报告已生成：{self.report_path.parent.name} · {result['labels_count']} 个标记",fg=ACCENT)
        self._sync_controls()
        if not self.devices and self.monitor: self._refresh_devices()
        if self.auto_open_var.get(): self._open_report()

    def _on_add_tag(self):
        text = self.tag_entry.get().strip()
        if not text or self.state!="recording": return
        try:
            marker = self.mgr.add_marker(text, source_line=self.last_source_line)
        except Exception as error:
            messagebox.showerror("打标签失败",str(error),parent=self.root)
            return
        self.markers.append(marker)
        self.tag_listbox.insert(tk.END,f"{clock_text(marker['time_s'])}   {marker['name']}")
        self.tag_listbox.see(tk.END)
        self.tag_entry.delete(0,tk.END)
        self.marker_count.configure(text=f"{len(self.markers)} 个")
        self._draw_charts(force=True)

    def _quick_tag(self, text):
        if self.state=="recording":
            self.tag_entry.delete(0,tk.END)
            self.tag_entry.insert(0,text)
            self._on_add_tag()

    def _tick(self):
        if self.closed: return
        if self.state=="recording": self.elapsed = time.time()-self.start_time
        self.timer_label.configure(text=clock_text(self.elapsed))
        self.root.after(100,self._tick)

    def _draw_charts(self, force=False):
        if self.display_paused and not force: return
        seconds = {"最近 60 秒":60,"最近 180 秒":180,"全程":None}[self.window_var.get()]
        period_ms = self.sample_period_ms
        window = max(1,round(seconds*1000/period_ms)) if seconds else None
        waiting = "等待该指标数据" if self.state in ("recording","stopping") else "尚未开始采样 · 点击左侧开始"
        for _,chart in self.charts:
            chart.readable_units=self.readable_var.get()
            chart.set_data(self.history,self.markers,window,waiting,period_ms)
        self._draw_fps(force=force)

    def _draw_fps(self, force=False):
        if self.display_paused and not force:
            return
        window = {"最近 60 秒":60,"最近 180 秒":180,"全程":None}[self.window_var.get()]
        self.fps_chart.set_data(self.fps_history,[],window,"等待目标应用帧呈现数据")

    def _refresh_units(self):
        for column,label in self.metric_labels.items():
            if column!="FPS":
                label.configure(text=format_metric(column,self.last_cli.get(column),readable=self.readable_var.get()))
        self._draw_charts(force=True)

    def _visible_sections(self):
        return {"GPU":{"gpu","shader","stalls","bandwidth"},"Shader":{"shader"},
                "停顿 / 缓存":{"stalls"},"访存":{"bandwidth"},"系统":{"system","cpu","memory","temperature"},
                "全部":None}[self.group_var.get()]

    def _filter_charts(self):
        sections = self._visible_sections()
        self.fps_chart.pack_forget()
        if sections is None or "gpu" in sections:
            self.fps_chart.pack(fill=tk.X,pady=(0,12))
        for category,chart in self.charts:
            chart.pack_forget()
            if sections is None or category in sections:
                chart.pack(fill=tk.X,pady=(0,12))
        self.chart_canvas.yview_moveto(0)
        self._draw_charts(force=True)
        self._update_raw_table()

    def _update_raw_table(self):
        if not hasattr(self,"raw_table"):
            return
        query = self.raw_search.get().lower()
        rows = []
        for index,(column,value) in enumerate(self.last_cli.items()):
            metric = metric_for(column,index)
            if query and query not in f"{column} {metric.label}".lower():
                continue
            reasons=cell_findings(column,value)
            rows.append((column,value,"；".join(reasons)))
        children = self.raw_table.get_children()
        # Reuse rows so scroll position and selection survive a live refresh.
        for index,row in enumerate(rows):
            if index<len(children): self.raw_table.item(children[index],values=row,tags=("review",) if row[2] else ())
            else: self.raw_table.insert("",tk.END,values=row,tags=("review",) if row[2] else ())
        for item in children[len(rows):]: self.raw_table.delete(item)
        self.raw_count.configure(text=f"CSV 第 {self.last_source_line} 行 · {len(rows)} / {len(self.last_cli)} 个 CLI 指标" if self.last_cli else "等待 CLI 计数器数据")

    def _toggle_pause(self):
        self.display_paused = not self.display_paused
        self.pause_btn.configure(text="继续曲线" if self.display_paused else "暂停曲线")
        self.log_label.configure(text="仅暂停曲线显示，完整采样继续。" if self.display_paused else "曲线显示已恢复。",fg=GOLD if self.display_paused else MUTED)
        if not self.display_paused: self._draw_charts(force=True)

    def _scroll(self, event):
        if str(event.widget).startswith(str(self.chart_holder)) or event.widget==self.chart_canvas:
            self.chart_canvas.yview_scroll(-int(event.delta/120),"units")
        elif event.widget!=self.tag_listbox and (str(event.widget).startswith(str(self.side_frame)) or event.widget==self.side_canvas):
            self.side_canvas.yview_scroll(-int(event.delta/120),"units")

    def _find_recent_report(self):
        folder = Path.cwd()/"Docs"/"Benchmarks"/"GPU"
        reports = list(folder.rglob("timeline.html")) if folder.is_dir() else []
        return max(reports,key=lambda path:path.stat().st_mtime) if reports else None

    def _open_report(self):
        if self.report_path and self.report_path.exists():
            webbrowser.open(self.report_path.resolve().as_uri())
        elif self.report_path:
            messagebox.showerror("报告不存在",str(self.report_path),parent=self.root)

    def _close(self):
        if self.state in ("starting","stopping"):
            messagebox.showinfo("操作进行中","请等待当前采样操作完成后关闭面板。",parent=self.root)
            return
        if self.state=="recording" and not messagebox.askyesno(
            "采样仍在进行","关闭面板后，设备上的采样仍会继续。\n重新打开可恢复会话，是否仅关闭面板？",parent=self.root
        ): return
        self.closed = True
        self.poll_stop.set()
        self.root.destroy()


def main():
    root = tk.Tk()
    PerfDogGui(root)
    root.update_idletasks()
    root.deiconify()
    root.lift()
    root.mainloop()
