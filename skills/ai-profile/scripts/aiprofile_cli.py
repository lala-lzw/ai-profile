#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AiProfile Skill - 统一命令行与入口脚本 (Unified CLI)

用法示例：
1. 【PerfDog 交互模式】点击即开始，回车即打标签，敲 q 即结束：
   python C:/Users/user/.gemini/config/skills/ai-profile/scripts/aiprofile_cli.py record --tag "大世界实测"

2. 【PerfDog 悬浮窗 GUI】像 PerfDog 一样打开桌面图形小窗口控制：
   python C:/Users/user/.gemini/config/skills/ai-profile/scripts/aiprofile_cli.py gui

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
    print("  🚀 AiProfile - 移动端 GPU 硬件总线实测 (PerfDog 交互录制模式)")
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
    print(f"\n[整场物理均值]")
    print(f"   DDR 读写总带宽: {ov['total_bw_sec_mb']} MB/s (单帧 {ov['total_bw_frame_mb']} MB/帧)")
    print(f"   UBWC 压缩率: {ov['ubwc_compressed_pct']}% | GPU 频点: {ov['gpu_clk_mhz']} MHz | 均温: {ov.get('temperature_c', 0):.1f}°C")

    segs = ov.get("segments", [])
    if segs:
        print(f"\n[PerfDog 分段标签对比]")
        for s in segs:
            print(f"   🏷️ {s['label_name']:12s} ({s['duration_s']}s) -> DDR带宽: {s['total_bw_sec_mb']:6.1f} MB/s ({s['total_bw_frame_mb']:4.1f} MB/帧) | 频点: {s['gpu_clk_mhz']} MHz")
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

    print(f"[GPU] 正在对应用 {package} 原地执行 {duration} 秒硬件总线计数器采样 (采样周期 {period}ms)...")
    collector.capture(package, raw_csv, duration_s=duration, period_ms=period, warmup_s=1.0)

    # 分析与报表
    analyzer = MetricsAnalyzer(fps_baseline=fps)
    metrics_res = analyzer.parse_sdp_csv(raw_csv, period_ms=period)
    rep_path = ReportEngine.generate_single_report(run_tag, metrics_res, dev_env, mem_info, out)

    print(f"\n[DONE] 测试完成！")
    print(f"       -> 报告路径: {rep_path.resolve()}")
    print(f"       -> DDR 物理读写带宽: {metrics_res['total_bw_sec_mb']} MB/s (单帧 {metrics_res['total_bw_frame_mb']} MB/帧)")
    print(f"       -> 纹理读取带宽: {metrics_res['tex_read_sec_mb']} MB/s")
    print(f"       -> UBWC 硬件无损压缩率: {metrics_res['ubwc_compressed_pct']}%")
    print(f"       -> 显存占用: {mem_info['graphics_pss_mb']} MB | 物理总内存: {mem_info['total_pss_mb']} MB")

    return out

def main():
    parser = argparse.ArgumentParser(description="AiProfile Skill - 统一移动端 GPU 硬件性能自动化分析工具 (支持 PerfDog 模式)")
    subparsers = parser.add_subparsers(dest="cmd")

    # 1. 类似 PerfDog 的交互式录制模式
    rec_p = subparsers.add_parser("record", help="【PerfDog 交互录制模式】回车打标签，敲 q 结束")
    rec_p.add_argument("--package", help="目标应用包名 (省略则自动锁定前台应用)", default=None)
    rec_p.add_argument("--tag", help="本次测试标签名称", default="PerfDogRecord")
    rec_p.add_argument("--period", type=int, default=200, help="采样周期 (毫秒，默认 200，即每秒 5 次)")
    rec_p.add_argument("--fps", type=float, default=60.0, help="基准帧率 (默认 60.0)")
    rec_p.add_argument("--out", type=Path, default=None, help="自定义产物输出目录")

    # 2. 类似 PerfDog 的桌面悬浮窗 GUI
    subparsers.add_parser("gui", help="【PerfDog 桌面小窗口】打开悬浮控制面板进行点击/打标")

    # 3. 分立生命周期命令 (适合自动化脚本)
    start_p = subparsers.add_parser("start", help="后台启动采样会话")
    start_p.add_argument("--package", help="目标应用包名", default=None)
    start_p.add_argument("--tag", help="会话标签", default="LiveSession")
    start_p.add_argument("--period", type=int, default=200, help="采样周期 (ms)")
    start_p.add_argument("--fps", type=float, default=60.0, help="基准帧率")
    start_p.add_argument("--out", type=Path, default=None, help="输出目录")

    mark_p = subparsers.add_parser("mark", help="为当前活跃会话打标签")
    mark_p.add_argument("label", type=str, help="标签文本 (如 'Boss战', '放技能')")

    subparsers.add_parser("stop", help="停止活跃会话，拉取数据并产出报表")

    # 4. 固定时长单次采样
    run_p = subparsers.add_parser("run", help="执行固定时长的 GPU Profile 物理采样")
    run_p.add_argument("--package", help="目标应用包名 (若省略则自动获取前台应用)", default=None)
    run_p.add_argument("--tag", help="单次采样的标签名称 (如 '鸿都城_高配')", default=None)
    run_p.add_argument("--attach", action="store_true", default=True, help="原地挂载 (不重启应用，默认开启)")
    run_p.add_argument("--duration", type=float, default=3.0, help="采样时长 (秒，默认 3.0)")
    run_p.add_argument("--period", type=int, default=200, help="采样周期 (毫秒，默认 200)")
    run_p.add_argument("--fps", type=float, default=60.0, help="单帧物理折算基准帧率 (默认 60.0)")
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
        s = mgr.start_session(
            package=args.package,
            tag=args.tag,
            period_ms=args.period,
            fps=args.fps,
            output_dir=args.out
        )
        print(f"[AiProfile] 会话已启动！")
        print(f"-> 目标应用: {s['package']}")
        print(f"-> 采样周期: {s['period_ms']}ms")
        print(f"-> 打标签命令: python aiprofile_cli.py mark <标签名称>")
        print(f"-> 结束命令:   python aiprofile_cli.py stop")
    elif args.cmd == "mark":
        mgr = SessionManager()
        m = mgr.add_marker(args.label)
        print(f"[AiProfile] 打标签成功: +{m['time_s']:.1f}s -> 【🏷️ {m['name']}】")
    elif args.cmd == "stop":
        mgr = SessionManager()
        res = mgr.stop_session()
        print(f"[AiProfile] 会话已结束并完成汇总！")
        print(f"-> 采样时长: {res['duration_s']}s | 标签数: {res['labels_count']}")
        print(f"-> 报告路径: {res['report_path']}")
        print(f"-> 时间轴图表: {res['timeline_html']}")
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
