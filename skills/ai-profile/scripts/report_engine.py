#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AiProfile Skill - 通用报告生成引擎 (ReportEngine)
负责生成单模式报告、多画质梯次横向对比表及结构化 summary.json。
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

class ReportEngine:
    @staticmethod
    def generate_single_report(
        tag: str,
        analyzer_res: dict[str, Any],
        device_info: dict[str, Any],
        memory_info: dict[str, float],
        output_dir: Path
    ) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        md_path = output_dir / "summary.md"
        json_path = output_dir / "summary.json"

        now_utc = datetime.now(timezone.utc).isoformat()
        fm = analyzer_res["frame_metrics"]

        dump_data = {
            "timestamp_utc": now_utc,
            "tag": tag,
            "device": device_info,
            "memory": memory_info,
            "gpu_summary": {
                "total_bw_mb_s": analyzer_res["total_bw_sec_mb"],
                "total_bw_mb_frame": analyzer_res["total_bw_frame_mb"],
                "read_bw_mb_s": analyzer_res["read_bw_sec_mb"],
                "write_bw_mb_s": analyzer_res["write_bw_sec_mb"],
                "tex_read_mb_s": analyzer_res["tex_read_sec_mb"],
                "gpu_util_pct": analyzer_res["gpu_util_pct"],
                "gpu_clock_mhz": analyzer_res["gpu_clk_mhz"],
                "ubwc_pct": analyzer_res["ubwc_compressed_pct"]
            },
            "diagnosis": analyzer_res["diagnosis"],
            "raw_metrics": analyzer_res["frame_metrics"]
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(dump_data, f, ensure_ascii=False, indent=2)

        lines = []
        lines.append(f"# `{tag}` 硬件总线性能与单帧对账报告\n")
        lines.append(f"- **测试时间 (UTC)**: `{now_utc}`")
        lines.append(f"- **测试设备**: `{device_info.get('model', 'Unknown')}` (Root: {device_info.get('has_root')}, SELinux: {device_info.get('selinux')})")
        lines.append(f"- **换算基准**: `{analyzer_res['fps_baseline']}` FPS | 采样有效行数: `{analyzer_res['row_count']}` 行")
        lines.append(f"- **显存占用 (Graphics PSS)**: `{memory_info.get('graphics_pss_mb', 0)} MB` | **总物理内存 (Total PSS)**: `{memory_info.get('total_pss_mb', 0)} MB`\n")

        lines.append("## 1. 核心硬件总线物理指标（可直接与 Snapdragon Profiler GUI 截帧求和对比）\n")
        lines.append("| 硬件指标项 | sdpcli 每秒均值 | **单帧整帧值 (已除以 FPS)** | GUI 截帧对齐列名 | 架构与瓶颈解析 |")
        lines.append("| :--- | ---: | ---: | :--- | :--- |")

        def _row(h_name, label, unit, gui_col, note=""):
            m = fm.get(h_name, {})
            if "sec_mb" in m:
                lines.append(f"| **{label}** | `{m.get('sec_mb', 0)} MB/s` | **`{m.get('frame_mb', 0)} MB/帧`** | `{gui_col}` | {note} |")
            elif "sec_m" in m:
                lines.append(f"| **{label}** | `{m.get('sec_m', 0)} M/s` | **`{m.get('frame_m', 0)} M/帧`** | `{gui_col}` | {note} |")

        _row("Read Total (Bytes/sec)", "整帧总读带宽", "MB", "Read Total (Bytes)", "GPU 读 DRAM 物理流量")
        _row("Write Total (Bytes/sec)", "整帧总写带宽", "MB", "Write Total (Bytes)", "RT / Framebuffer 写 DDR 物理流量")
        _row("Texture Memory Read BW (Bytes/Second)", "纹理内存读取带宽", "MB", "Texture Memory Read BW", "贴图采样总线开销")
        _row("Vertex Memory Read (Bytes/Second)", "顶点内存读取带宽", "MB", "Vertex Memory Read", "几何顶点总线开销（通常 1:1 穿透）")
        _row("Clocks / Second", "GPU 工作时钟周期", "M", "Clocks", "硬件主频与执行周期")
        _row("Fragments Shaded / Second", "着色片元总数", "M", "Fragments Shaded", "光栅化片元像素总量")
        _row("Vertex Instructions / Second", "顶点着色指令数", "M", "Vertex Instructions", "顶点着色开销")
        _row("Fragment Instructions / Second", "片元着色总指令数", "M", "Fragment Instructions", "片元着色开销")
        _row("Fragment ALU Instructions / Sec (Half)", "半精度 FP16 ALU 指令", "M", "Fragment ALU Instructions (Half)", "移动端优化推荐使用半精度")

        lines.append("\n## 2. 硬件单元效率与停顿分析\n")
        lines.append("| 指标名称 | mean | p95 | 物理意义 |")
        lines.append("| :--- | ---: | ---: | :--- |")
        raw = analyzer_res["raw_stats"]
        for k, label, note in [
            ("GPU % Utilization", "GPU 核心利用率 (%)", "GPU 整体负荷水位"),
            ("GPU % Bus Busy", "GPU 总线繁忙度 (%)", "总线带宽饱和程度"),
            ("% Shaders Busy", "着色器计算繁忙度 (%)", "Shader ALU 活跃占比"),
            ("% Texture Pipes Busy", "纹理管线繁忙度 (%)", "纹理采样单元负载"),
            ("% Texture Fetch Stall", "纹理取指停顿率 (%)", "因等贴图数据返回造成的着色器等待"),
            ("Global Image Compressed Data Read BW (Bytes/sec)", "UBWC 无损压缩率 (%)", f"实测无损压缩率: {analyzer_res['ubwc_compressed_pct']}%")
        ]:
            if k == "Global Image Compressed Data Read BW (Bytes/sec)":
                lines.append(f"| **{label}** | `{analyzer_res['ubwc_compressed_pct']}%` | - | {note} |")
            elif k in raw:
                lines.append(f"| **{label}** | `{raw[k]['mean']}%` | `{raw[k]['p95']}%` | {note} |")

        if analyzer_res["diagnosis"]:
            lines.append("\n## 3. 自动化瓶颈诊断\n")
            for d in analyzer_res["diagnosis"]:
                lines.append(f"- ⚠️ {d}")

        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return md_path

    @staticmethod
    def generate_comparison_report(
        tag_results: dict[str, dict[str, Any]],
        output_path: Path
    ) -> Path:
        """生成多档画质横向对比大表"""
        lines = []
        lines.append("# 多档画质硬件性能横向梯度对比总表\n")
        tags = list(tag_results.keys())

        header = ["核心指标项"] + [f"**{t}**" for t in tags] + ["增幅规律与瓶颈诊断"]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("| " + " | ".join([":---"] + [":---:"] * len(tags) + [":---"]) + " |")

        def _cmp_row(label, key_path, unit="", is_ratio=False):
            vals = []
            for t in tags:
                cur = tag_results[t]
                for p in key_path:
                    cur = cur.get(p, {})
                v = cur if isinstance(cur, (int, float)) else 0.0
                vals.append(v)

            row = [f"**{label}**"]
            for v in vals:
                if unit == "MB":
                    row.append(f"`{v:.2f} MB/s`")
                elif unit == "MB/帧":
                    row.append(f"**`{v:.2f} MB/帧`**")
                elif unit == "M":
                    row.append(f"`{v:.2f} M/s`")
                elif unit == "%":
                    row.append(f"`{v:.1f}%`")
                elif unit == "MHz":
                    row.append(f"`{v:.1f} MHz`")
                else:
                    row.append(f"`{v}`")

            note = ""
            if len(vals) >= 2 and vals[0] > 0:
                growth = (vals[-1] - vals[0]) / vals[0] * 100.0
                note = f"极高比低配增长 **{growth:+.1f}%**"
            row.append(note)
            lines.append("| " + " | ".join(row) + " |")

        _cmp_row("总线总物理带宽 (Total BW)", ["analyzer", "total_bw_sec_mb"], "MB")
        _cmp_row("单帧总线物理带宽 (MB/帧)", ["analyzer", "total_bw_frame_mb"], "MB/帧")
        _cmp_row("DDR 物理读带宽 (Read BW)", ["analyzer", "read_bw_sec_mb"], "MB")
        _cmp_row("DDR 物理写带宽 (Write BW)", ["analyzer", "write_bw_sec_mb"], "MB")
        _cmp_row("纹理采样读取 (Texture Read)", ["analyzer", "tex_read_sec_mb"], "MB")
        _cmp_row("GPU 核心利用率 (Util)", ["analyzer", "gpu_util_pct"], "%")
        _cmp_row("GPU 工作时钟 (Clock)", ["analyzer", "gpu_clk_mhz"], "MHz")
        _cmp_row("显存占用 (Graphics PSS)", ["memory", "graphics_pss_mb"], "MB")
        _cmp_row("UBWC 硬件无损压缩率", ["analyzer", "ubwc_compressed_pct"], "%")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return output_path

