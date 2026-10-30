#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AiProfile Skill - 统一命令行与入口脚本 (Unified CLI)

用法示例：
1. 原地挂载采样 (自动锁定前台应用，采样 3 秒)：
   python C:/Users/user/.gemini/config/skills/ai-profile/scripts/aiprofile_cli.py run --attach --tag "高配测试"

2. 指定包名采样：
   python C:/Users/user/.gemini/config/skills/ai-profile/scripts/aiprofile_cli.py run --package com.xxx.game --attach --tag "极高配"

3. 截帧相机聚合过滤：
   python C:/Users/user/.gemini/config/skills/ai-profile/scripts/aiprofile_cli.py filter-camera <path_to_raw_csv> --out <path_to_filtered_csv>
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from adb_bridge import AdbBridge
from sdp_collector import SdpCollector
from metrics_analyzer import MetricsAnalyzer
from report_engine import ReportEngine
from camera_filter import CameraFilter

def run_profile_task(
    package: Optional[str] = None,
    tag: Optional[str] = None,
    attach: bool = True,
    duration: float = 3.0,
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
        raise FileNotFoundError("未检测到 Snapdragon Profiler (sdpcli.exe)，请确认安装路径。")

    raw_csv = out / "raw" / f"sdp_{run_tag}.csv"
    screen_png = out / "capture.png"

    # 截图与内存采集
    adb.capture_screenshot(screen_png)
    mem_info = adb.get_process_memory(package)

    print(f"[GPU] 正在对应用 {package} 原地执行 {duration} 秒硬件总线计数器采样...")
    collector.capture(package, raw_csv, duration_s=duration, warmup_s=1.0)

    # 分析与报表
    analyzer = MetricsAnalyzer(fps_baseline=fps)
    metrics_res = analyzer.parse_sdp_csv(raw_csv)
    rep_path = ReportEngine.generate_single_report(run_tag, metrics_res, dev_env, mem_info, out)

    print(f"\n[DONE] 测试完成！")
    print(f"       -> 报告路径: {rep_path.resolve()}")
    print(f"       -> DDR 物理读写带宽: {metrics_res['total_bw_sec_mb']} MB/s (单帧 {metrics_res['total_bw_frame_mb']} MB/帧)")
    print(f"       -> 纹理读取带宽: {metrics_res['tex_read_sec_mb']} MB/s")
    print(f"       -> UBWC 硬件无损压缩率: {metrics_res['ubwc_compressed_pct']}%")
    print(f"       -> 显存占用: {mem_info['graphics_pss_mb']} MB | 物理总内存: {mem_info['total_pss_mb']} MB")

    return out

def main():
    parser = argparse.ArgumentParser(description="AiProfile Skill - 统一移动端 GPU 硬件性能自动化分析工具")
    subparsers = parser.add_subparsers(dest="cmd")

    run_p = subparsers.add_parser("run", help="执行 GPU Profile 物理采样")
    run_p.add_argument("--package", help="目标应用包名 (若省略则自动获取前台应用)", default=None)
    run_p.add_argument("--tag", help="单次采样的标签名称 (如 '鸿都城_高配')", default=None)
    run_p.add_argument("--attach", action="store_true", default=True, help="原地挂载 (不重启应用，默认开启)")
    run_p.add_argument("--duration", type=float, default=3.0, help="采样时长 (秒，默认 3.0)")
    run_p.add_argument("--fps", type=float, default=60.0, help="单帧物理折算基准帧率 (默认 60.0)")
    run_p.add_argument("--out", type=Path, default=None, help="自定义产物输出目录")

    filter_p = subparsers.add_parser("filter-camera", help="截帧 CSV 相机聚合过滤")
    filter_p.add_argument("csv_path", type=Path, help="Snapdragon Profiler 导出的原始 CSV 文件")
    filter_p.add_argument("--out", type=Path, default=None, help="过滤后输出的 CSV 文件路径")

    args = parser.parse_args()

    if args.cmd == "run":
        run_profile_task(
            package=args.package,
            tag=args.tag,
            attach=args.attach,
            duration=args.duration,
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

