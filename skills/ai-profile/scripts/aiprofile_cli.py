#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AiProfile Skill - 统一命令行与入口脚本 (Unified CLI)

用法示例：
1. 【PerfDog 交互模式】点击即开始，回车即打标签，敲 q 即结束：
   python aiprofile_cli.py record --tag "大世界实测"

2. 【PerfDog 悬浮窗 GUI】像 PerfDog 一样打开桌面图形小窗口控制：
   python aiprofile_cli.py gui

3. 【分立命令控制】适合自动化脚本或 Agent 工具链：
   python aiprofile_cli.py start [--package com.xxx.game] [--tag "Boss战"]
   python aiprofile_cli.py mark "释放全屏技能"
   python aiprofile_cli.py stop

4. 【固定时长快照采样】
   python aiprofile_cli.py run --duration 3.0 --period 200 --tag "极高配"

5. 【截帧相机聚合过滤】
   python aiprofile_cli.py filter-camera <raw_csv> --out <filtered_csv>
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from adb_bridge import AdbBridge
from sdp_collector import SdpCollector
from metrics_analyzer import MetricsAnalyzer
from report_engine import ReportEngine
from camera_filter import CameraFilter
from session_manager import SessionManager
from gpu_metrics import console_gpu_summary, console_gpu_segment

def run_interactive_record(
    package: Optional[str] = None,
    tag: Optional[str] = None,
    period_ms: int = 200,
    fps: float = 60.0,
    output_dir: Optional[Path] = None
):
    mgr = SessionManager()
    do_launch = False

    # 若未在命令行显式指定包名，列出手机已安装应用让用户交互式选择
    if not package:
        dev_env = mgr.adb.prepare_device_env()
        fg_pkg, _ = mgr.adb.get_foreground_app()
        apps = mgr.adb.get_installed_apps()

        print("\n" + "=" * 70)
        print(f"  📱 真机设备: {dev_env['model']} | 已安装游戏与应用列表")
        print("=" * 70)
        print(f"  [0] ⚡ 原地挂载当前真机前台应用: {fg_pkg or '未检测到'}")
        
        display_apps = apps[:15]
        for idx, a in enumerate(display_apps, 1):
            icon = "🎮" if a["is_game"] else "📱"
            fg_tag = " [★当前前台]" if a["is_foreground"] else ""
            print(f"  [{idx:2d}] {icon} {a['name']:<24s} ({a['package']}){fg_tag}")
        print("-" * 70)
        
        try:
            raw_in = input("👉 请输入序号选择要启动测试的应用 (直接回车默认 0 原地挂载): ").strip()
            if raw_in.isdigit() and 1 <= int(raw_in) <= len(display_apps):
                chosen = display_apps[int(raw_in) - 1]
                package = chosen["package"]
                do_launch = True
                print(f"[Device] 用户选择了应用: {chosen['name']} ({package})，将在真机上自动拉起！")
            else:
                package = fg_pkg
                do_launch = False
                print(f"[Device] 使用当前前台应用: {package}")
        except (EOFError, KeyboardInterrupt):
            package = fg_pkg
            do_launch = False

    session = mgr.start_session(
        package=package,
        tag=tag,
        period_ms=period_ms,
        fps=fps,
        launch=do_launch,
        output_dir=output_dir
    )

    dev = session["device_env"]
    print("\n" + "=" * 70)
    print("  🚀 AiProfile - 移动端 GPU 硬件计数器采样 (PerfDog 交互录制模式)")
    print("=" * 70)
    print(f"[Device] 设备: {dev['model']} (Root: {dev['has_root']}, SELinux: {dev['selinux']})")
    print(f"[App]    目标应用: {session['package']}")
    print(f"[Status] ● 正在高频持续采样中 (采样周期: {period_ms}ms)...")
    print("\n【操作指南】")
    print("  • 直接输入文字并按回车 -> 为当前时刻打标签 (Marker)")
    print("    例如: '进入副本'、'释放大招'、'团战爆发'、'切高画质'")
    print("  • 输入 'q' / 'stop' 或按 Ctrl+C -> 结束采集并生成分段画像报表")
    print("-" * 70 + "\n")

    try:
        while True:
            prompt = f"[{time.time() - session['start_time']:5.1f}s] > "
            sys.stdout.write(prompt)
            sys.stdout.flush()

            line = sys.stdin.readline()
            if not line:
                break
            text = line.strip()

            if text.lower() in ("q", "quit", "stop", "exit"):
                break
            elif text:
                m = mgr.add_marker(text)
                print(f"  [✓ 打标成功] +{m['time_s']:.1f}s -> 【🏷️ {text}】\n")
    except KeyboardInterrupt:
        print("\n\n[AiProfile] 收到中断信号，正在收尾...")

    print("\n[AiProfile] 正在从设备拉取数据、切分时间轴并生成分段画像报表...")
    res = mgr.stop_session()

    print("\n" + "=" * 70)
    print("  🎉 性能采样与分段对账完成！")
    print("=" * 70)
    print(f"-> 采样总时长: {res['duration_s']} 秒 | 记录标签: {res['labels_count']} 个")
    print(f"-> 对账报告: {res['report_path'].resolve()}")
    print(f"-> 交互式走势图: {res['timeline_html'].resolve()}")
    if res.get("labeled_csv"):
        print(f"-> 带标签 CSV: {res['labeled_csv']}")

    ov = res["metrics"]
    print("\n" + console_gpu_summary(ov))

    segs = ov.get("segments", [])
    if segs:
        print(f"\n[PerfDog 分段标签对比]")
        for s in segs:
            print(f"   {s['label_name']} (CSV L{s['source_start_line']}～L{s['source_end_line']}) -> {console_gpu_segment(s)}")
    print("=" * 70 + "\n")

def run_profile_task(
    package: Optional[str] = None,
    tag: Optional[str] = None,
    attach: bool = True,
    duration: float = 3.0,
    period: int = 200,
    fps: float = 60.0,
    output_dir: Optional[Path] = None
) -> Path:
    adb = AdbBridge()
    dev_env = adb.prepare_device_env()
    print(f"[Device] 设备: {dev_env['model']} | Root: {dev_env['has_root']} | SELinux: {dev_env['selinux']}")

    if not package:
        fg_pkg, fg_act = adb.get_foreground_app()
        if not fg_pkg:
            raise RuntimeError("未指定 --package，且未检测到真机前台运行的任何应用！请先在手机上打开游戏。")
        package = fg_pkg
        print(f"[App] 自动锁定真机前台应用: {package} ({fg_act})")
    else:
        print(f"[App] 目标应用: {package}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_tag = tag or "ProfileRun"
    out = output_dir or Path(f"Docs/Benchmarks/GPU/aiprofile_{ts}/{run_tag}")
    out.mkdir(parents=True, exist_ok=True)

    collector = SdpCollector(adb)
    if not collector.is_available():
        raise FileNotFoundError("未检测到 Snapdragon Profiler，请确认配置。")

    raw_csv = out / "raw" / f"sdp_{run_tag}.csv"
    screen_png = out / "capture.png"

    # 截图与内存采集
    adb.capture_screenshot(screen_png)
    mem_info = adb.get_process_memory(package)

    print(f"[GPU] 正在对应用 {package} 原地执行 {duration} 秒 GPU 硬件计数器采样 (采样周期 {period}ms)...")
    collector.capture(package, raw_csv, duration_s=duration, period_ms=period, warmup_s=1.0)

    # 分析与报表
    analyzer = MetricsAnalyzer(fps_baseline=fps)
    metrics_res = analyzer.parse_sdp_csv(raw_csv, period_ms=period)
    rep_path = ReportEngine.generate_single_report(run_tag, metrics_res, dev_env, mem_info, out)

    print(f"\n[DONE] 测试完成！")
    print(f"       -> 报告路径: {rep_path.resolve()}")
    print(console_gpu_summary(metrics_res))
    print(f"       -> Graphics PSS 快照: {mem_info['graphics_pss_mb']} MB | 应用 Total PSS: {mem_info['total_pss_mb']} MB")

    return out

def main():
    parser = argparse.ArgumentParser(description="AiProfile Skill - 统一移动端 GPU 硬件性能自动化分析工具 (支持 PerfDog 模式)")
    subparsers = parser.add_subparsers(dest="cmd")

    # 1. 类似 PerfDog 的交互式录制模式
    rec_p = subparsers.add_parser("record", help="【PerfDog 交互录制模式】回车打标签，敲 q 结束")
    rec_p.add_argument("--package", help="目标应用包名 (省略则自动锁定前台应用)", default=None)
    rec_p.add_argument("--tag", help="本次测试标签名称", default="PerfDogRecord")
    rec_p.add_argument("--period", type=int, default=200, help="采样周期 (毫秒，默认 200，即每秒 5 次)")
    rec_p.add_argument("--fps", type=float, default=60.0, help="兼容参数；原始数据模式不作 FPS 折算")
    rec_p.add_argument("--out", type=Path, default=None, help="自定义产物输出目录")

    # 2. 类似 PerfDog 的桌面悬浮窗 GUI
    subparsers.add_parser("gui", help="【PerfDog 桌面小窗口】打开悬浮控制面板进行点击/打标")

    # 3. 分立生命周期命令 (适合自动化脚本与快捷命令)
    start_p = subparsers.add_parser("start", help="后台启动采样会话")
    start_p.add_argument("--package", help="目标应用包名 (省略则自动锁定当前前台)", default=None)
    start_p.add_argument("--tag", help="会话标签", default="LiveSession")
    start_p.add_argument("--period", type=int, default=200, help="采样周期 (ms，默认 200)")
    start_p.add_argument("--fps", type=float, default=60.0, help="兼容参数；原始数据模式不作 FPS 折算")
    start_p.add_argument("--launch", action="store_true", default=False, help="启动前先在手机上拉起该游戏")
    start_p.add_argument("--out", type=Path, default=None, help="输出目录")

    mark_p = subparsers.add_parser("mark", help="为当前活跃会话打标签")
    mark_p.add_argument("label", nargs="?", default="Marker", type=str, help="标签文本 (如 '鸿都城', '放技能')")

    stop_p = subparsers.add_parser("stop", help="停止活跃会话，拉取数据并产出报表")
    stop_p.add_argument("--no-open", action="store_true", default=False, help="完成后不自动在浏览器打开走势图")

    # 4. 固定时长单次采样
    run_p = subparsers.add_parser("run", help="执行固定时长的 GPU Profile 物理采样")
    run_p.add_argument("--package", help="目标应用包名 (若省略则自动获取前台应用)", default=None)
    run_p.add_argument("--tag", help="单次采样的标签名称 (如 '鸿都城_高配')", default=None)
    run_p.add_argument("--attach", action="store_true", default=True, help="原地挂载 (不重启应用，默认开启)")
    run_p.add_argument("--duration", type=float, default=3.0, help="采样时长 (秒，默认 3.0)")
    run_p.add_argument("--period", type=int, default=200, help="采样周期 (毫秒，默认 200)")
    run_p.add_argument("--fps", type=float, default=60.0, help="兼容参数；原始数据模式不作 FPS 折算")
    run_p.add_argument("--out", type=Path, default=None, help="自定义产物输出目录")

    # 5. 截帧过滤
    filter_p = subparsers.add_parser("filter-camera", help="截帧 CSV 相机聚合过滤")
    filter_p.add_argument("csv_path", type=Path, help="Snapdragon Profiler 导出的原始 CSV 文件")
    filter_p.add_argument("--out", type=Path, default=None, help="过滤后输出的 CSV 文件路径")

    args = parser.parse_args()

    if args.cmd == "record":
        run_interactive_record(
            package=args.package,
            tag=args.tag,
            period_ms=args.period,
            fps=args.fps,
            output_dir=args.out
        )
    elif args.cmd == "gui":
        from gui_panel import main as gui_main
        gui_main()
    elif args.cmd == "start":
        mgr = SessionManager()
        if mgr.is_session_active():
            cur = mgr.get_current_session()
            print(f"[AiProfile] ⚠️ 当前已有一个正在运行的采样会话！")
            print(f"-> 目标应用: {cur.get('package')}")
            print(f"-> 打标签命令: profile-mark <标签名>")
            print(f"-> 结束命令:   profile-stop")
            return

        try:
            s = mgr.start_session(
                package=args.package,
                tag=args.tag,
                period_ms=args.period,
                fps=args.fps,
                launch=args.launch,
                output_dir=args.out
            )
            print("\n" + "=" * 65)
            print(f"  🚀 AiProfile - 硬件性能采样已启动！")
            print("=" * 65)
            print(f"-> 目标应用: {s['package']}")
            print(f"-> 采样频率: 每秒 {1000/s['period_ms']:.1f} 次 ({s['period_ms']}ms 周期)")
            print(f"-> 打标签:   profile-mark <标签名称>  (或 aiprofile mark <标签>)")
            print(f"-> 结束采样: profile-stop             (或 aiprofile stop)")
            print("-" * 65 + "\n")
        except Exception as e:
            print(f"[AiProfile 启动失败]: {e}")

    elif args.cmd == "mark":
        mgr = SessionManager()
        if not mgr.is_session_active():
            print("[AiProfile] ⚠️ 当前没有正在运行的采样会话！请先执行 profile-start。")
            return
        m = mgr.add_marker(args.label)
        print(f"[AiProfile] 🏷️ 成功记录时间轴标签: +{m['time_s']:.1f}s -> 【{m['name']}】")

    elif args.cmd == "stop":
        mgr = SessionManager()
        if not mgr.is_session_active():
            print("[AiProfile] ⚠️ 当前没有运行中的采样会话！")
            return

        print("\n[AiProfile] ⏹ 正在停止采样、拉取数据并切分分段画像...")
        try:
            res = mgr.stop_session()
            print("\n" + "=" * 65)
            print("  🎉 采样完成并已产出完整报表！")
            print("=" * 65)
            print(f"-> 采样总时长: {res['duration_s']} 秒 | 记录标签: {res['labels_count']} 个")
            print(f"-> 报告文件:   {res['report_path'].resolve()}")
            print(f"-> 走势图表:   {res['timeline_html'].resolve()}")
            if res.get("labeled_csv"):
                print(f"-> 增强 CSV:   {Path(res['labeled_csv']).name}")

            ov = res["metrics"]
            print("\n" + console_gpu_summary(ov))

            segs = ov.get("segments", [])
            if segs:
                print(f"\n[PerfDog 标签分段对比]")
                for s in segs:
                    print(f"   {s['label_name']} (CSV L{s['source_start_line']}～L{s['source_end_line']}) -> {console_gpu_segment(s)}")
            print("=" * 65 + "\n")

            if not args.no_open and res["timeline_html"].exists():
                import webbrowser
                webbrowser.open(str(res["timeline_html"].resolve()))
        except Exception as e:
            print(f"[AiProfile 结束失败]: {e}")
    elif args.cmd == "run":
        run_profile_task(
            package=args.package,
            tag=args.tag,
            attach=args.attach,
            duration=args.duration,
            period=args.period,
            fps=args.fps,
            output_dir=args.out
        )
    elif args.cmd == "filter-camera":
        res = CameraFilter.extract_cameras_and_sum(args.csv_path, args.out)
        print(f"相机聚合成功: 包含 {len(res['cameras'])} 个相机节点，已写入: {res['filtered_csv']}")
        tot = res['total']
        print(f"-> 整帧 Clocks: {tot.get('Clocks', 0):,}")
        print(f"-> 整帧读总访存: {float(tot.get('Read Total (Bytes)', 0))/(1024*1024):.2f} MB")
        print(f"-> 整帧写总访存: {float(tot.get('Write Total (Bytes)', 0))/(1024*1024):.2f} MB")
        print(f"-> 着色片元数: {float(tot.get('Fragments Shaded', 0))/1e6:.2f} M")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
