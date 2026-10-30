#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AiProfile Skill - 通用报告生成引擎 (ReportEngine)
负责生成单模式报告、多画质梯次横向对比表、PerfDog 标签分段画像表及单文件时间轴交互式 HTML 走势图。
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

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
        html_path = output_dir / "timeline.html"

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
                "temperature_c": analyzer_res.get("temperature_c", 0.0),
                "ubwc_pct": analyzer_res["ubwc_compressed_pct"]
            },
            "segments": analyzer_res.get("segments", []),
            "labels": analyzer_res.get("labels", []),
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
        lines.append(f"- **显存占用 (Graphics PSS)**: `{memory_info.get('graphics_pss_mb', 0)} MB` | **总物理内存 (Total PSS)**: `{memory_info.get('total_pss_mb', 0)} MB`")
        if analyzer_res.get("labeled_csv"):
            lines.append(f"- **带标签原始 CSV**: `{Path(analyzer_res['labeled_csv']).name}`")
        lines.append(f"- **交互式时间轴图表**: [`timeline.html`](timeline.html)\n")

        # 1. 核心硬件总线物理指标
        lines.append("## 1. 核心全景硬件物理指标（整场测试均值）\n")
        lines.append("| 硬件指标项 | sdpcli 每秒均值 | **单帧整帧值 (除以 FPS)** | GUI 截帧对齐列名 | 架构与瓶颈解析 |")
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

        # 2. PerfDog 模式分段标签画像
        segments = analyzer_res.get("segments", [])
        if segments:
            lines.append("\n## 2. PerfDog 标签分段画像对比 (Segmented Comparison)\n")
            lines.append("| 阶段标签 | 时间区间 | 时长 | 样本数 | DDR 读带宽 | DDR 写带宽 | **总物理带宽** | **单帧带宽** | GPU 频点 | 均温 | UBWC 压缩率 |")
            lines.append("| :--- | :---: | :---: | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
            for seg in segments:
                name = seg.get("label_name", "-")
                t_range = f"{seg.get('start_time_s', 0)}s ~ {seg.get('end_time_s', 0)}s"
                dur = f"{seg.get('duration_s', 0)}s"
                cnt = seg.get("row_count", 0)
                r_bw = f"{seg.get('read_bw_sec_mb', 0)} MB/s"
                w_bw = f"{seg.get('write_bw_sec_mb', 0)} MB/s"
                tot_bw = f"`{seg.get('total_bw_sec_mb', 0)} MB/s`"
                f_bw = f"**`{seg.get('total_bw_frame_mb', 0)} MB/帧`**"
                clk = f"{seg.get('gpu_clk_mhz', 0)} MHz"
                temp = f"{seg.get('temperature_c', 0):.1f}°C" if seg.get('temperature_c') else "-"
                ubwc = f"{seg.get('ubwc_compressed_pct', 0)}%"
                lines.append(f"| **🏷️ {name}** | {t_range} | {dur} | {cnt} | {r_bw} | {w_bw} | {tot_bw} | {f_bw} | {clk} | {temp} | {ubwc} |")

        # 3. 硬件效率与停顿分析
        lines.append("\n## 3. 硬件单元效率与停顿分析\n")
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
            lines.append("\n## 4. 自动化瓶颈诊断\n")
            for d in analyzer_res["diagnosis"]:
                lines.append(f"- ⚠️ {d}")

        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        # 生成离线交互式 timeline.html
        ReportEngine._generate_timeline_html(tag, analyzer_res, html_path)
        return md_path

    @staticmethod
    def _generate_timeline_html(tag: str, analyzer_res: dict[str, Any], html_path: Path):
        """生成单文件完全离线的 HTML5 Canvas 交互式时间轴走势图 (含 PerfDog 标签指示线)"""
        segments = analyzer_res.get("segments", [])
        labels = analyzer_res.get("labels", [])
        labeled_csv = analyzer_res.get("labeled_csv")

        # 从 labeled_csv 中抽取时序数据采样点 (最多下采样至 600 点以保证流畅渲染)
        times, bw_reads, bw_writes, clks, temps, row_labels = [], [], [], [], [], []
        if labeled_csv and Path(labeled_csv).exists():
            import csv
            with open(labeled_csv, "r", encoding="utf-8-sig", errors="ignore") as f:
                r = csv.DictReader(f)
                rows = list(r)
                step = max(1, len(rows) // 600)
                for i in range(0, len(rows), step):
                    item = rows[i]
                    try:
                        t = float(item.get("Time (s)", 0.0))
                        lbl = item.get("PerfDog Label", "")
                        r_bytes = float(item.get("Read Total (Bytes/sec)", 0.0) or 0.0)
                        w_bytes = float(item.get("Write Total (Bytes/sec)", 0.0) or 0.0)
                        clk_s = float(item.get("Clocks / Second", 0.0) or 0.0)
                        tmp = float(item.get("Temperature", 0.0) or 0.0)

                        times.append(round(t, 2))
                        row_labels.append(lbl)
                        bw_reads.append(round(r_bytes / (1024 * 1024), 2))
                        bw_writes.append(round(w_bytes / (1024 * 1024), 2))
                        clks.append(round(clk_s / 1e6, 1))
                        temps.append(round(tmp, 1))
                    except (ValueError, TypeError):
                        pass

        # 组装 HTML
        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>AiProfile - {tag} 交互式时间轴</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0d1117; color: #c9d1d9; margin: 0; padding: 24px; }}
  .container {{ max-width: 1200px; margin: 0 auto; }}
  .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #30363d; padding-bottom: 16px; margin-bottom: 20px; }}
  h1 {{ margin: 0; font-size: 24px; color: #58a6ff; }}
  .badge {{ background: #238636; color: white; padding: 4px 10px; border-radius: 12px; font-size: 13px; font-weight: bold; }}
  .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; margin-bottom: 24px; }}
  canvas {{ width: 100%; height: 380px; display: block; }}
  .legend {{ display: flex; gap: 20px; margin-top: 12px; font-size: 13px; }}
  .legend-item {{ display: flex; align-items: center; gap: 6px; }}
  .dot {{ width: 12px; height: 12px; border-radius: 3px; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 14px; }}
  th, td {{ padding: 10px 14px; text-align: left; border-bottom: 1px solid #30363d; }}
  th {{ background: #21262d; color: #8b949e; }}
  tr:hover {{ background: #1f242c; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>📈 {tag} · 硬件性能时间轴走势图</h1>
    <span class="badge">PerfDog 标签模式</span>
  </div>

  <div class="card">
    <div style="font-weight: 600; margin-bottom: 12px; color: #8b949e;">硬件总线带宽与温度实时走势 (带标签指示线)</div>
    <canvas id="timelineChart"></canvas>
    <div class="legend">
      <div class="legend-item"><span class="dot" style="background:#58a6ff;"></span> 读总线带宽 (MB/s)</div>
      <div class="legend-item"><span class="dot" style="background:#a371f7;"></span> 写总线带宽 (MB/s)</div>
      <div class="legend-item"><span class="dot" style="background:#f0883e;"></span> 温度 (°C)</div>
      <div class="legend-item"><span class="dot" style="background:#2ea043;"></span> 🏷️ 阶段标签 (Marker)</div>
    </div>
  </div>

  <div class="card">
    <div style="font-weight: 600; margin-bottom: 12px; color: #8b949e;">分段标签性能统计表</div>
    <table>
      <thead>
        <tr>
          <th>标签阶段</th>
          <th>时间区间</th>
          <th>持续时间</th>
          <th>样本数</th>
          <th>读物理带宽</th>
          <th>写物理带宽</th>
          <th>总物理带宽</th>
          <th>单帧带宽</th>
          <th>GPU 频点</th>
        </tr>
      </thead>
      <tbody>
"""
        for seg in segments:
            html_content += f"""
        <tr>
          <td><strong>🏷️ {seg.get('label_name', '-')}</strong></td>
          <td>{seg.get('start_time_s', 0)}s ~ {seg.get('end_time_s', 0)}s</td>
          <td>{seg.get('duration_s', 0)}s</td>
          <td>{seg.get('row_count', 0)}</td>
          <td>{seg.get('read_bw_sec_mb', 0)} MB/s</td>
          <td>{seg.get('write_bw_sec_mb', 0)} MB/s</td>
          <td style="color:#58a6ff; font-weight:bold;">{seg.get('total_bw_sec_mb', 0)} MB/s</td>
          <td style="color:#3fb950; font-weight:bold;">{seg.get('total_bw_frame_mb', 0)} MB/帧</td>
          <td>{seg.get('gpu_clk_mhz', 0)} MHz</td>
        </tr>
"""
        html_content += f"""
      </tbody>
    </table>
  </div>
</div>

<script>
const times = {json.dumps(times)};
const rBw = {json.dumps(bw_reads)};
const wBw = {json.dumps(bw_writes)};
const temps = {json.dumps(temps)};
const labels = {json.dumps(labels)};

const canvas = document.getElementById('timelineChart');
const ctx = canvas.getContext('2d');

function resize() {{
  canvas.width = canvas.parentElement.clientWidth * window.devicePixelRatio;
  canvas.height = 380 * window.devicePixelRatio;
  draw();
}}
window.addEventListener('resize', resize);

function draw() {{
  const w = canvas.width, h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  if (!times.length) return;

  const padL = 60, padR = 60, padT = 30, padB = 40;
  const plotW = w - padL - padR, plotH = h - padT - padB;

  const maxBw = Math.max(10, ...rBw, ...wBw) * 1.15;
  const maxT = times[times.length - 1] || 1;

  // 网格线
  ctx.strokeStyle = '#21262d';
  ctx.lineWidth = 1;
  for (let i = 0; i <= 5; i++) {{
    const y = padT + (plotH / 5) * i;
    ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(w - padR, y); ctx.stroke();
    ctx.fillStyle = '#8b949e'; ctx.font = `${{11 * window.devicePixelRatio}}px sans-serif`;
    ctx.fillText(`${{Math.round(maxBw * (1 - i / 5))}} MB/s`, 10, y + 4);
  }}

  function getX(t) {{ return padL + (t / maxT) * plotW; }}
  function getY(v) {{ return padT + plotH - (v / maxBw) * plotH; }}

  // 绘制曲线
  function drawLine(arr, color) {{
    ctx.strokeStyle = color;
    ctx.lineWidth = 2 * window.devicePixelRatio;
    ctx.beginPath();
    for (let i = 0; i < times.length; i++) {{
      const x = getX(times[i]);
      const y = getY(arr[i] || 0);
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }}
    ctx.stroke();
  }}

  drawLine(rBw, '#58a6ff');
  drawLine(wBw, '#a371f7');

  // 绘制 PerfDog 标签指示竖线与 Badge
  labels.forEach((lbl, idx) => {{
    const lx = getX(lbl.time_s);
    ctx.strokeStyle = '#2ea043';
    ctx.setLineDash([4 * window.devicePixelRatio, 4 * window.devicePixelRatio]);
    ctx.beginPath(); ctx.moveTo(lx, padT); ctx.lineTo(lx, h - padB); ctx.stroke();
    ctx.setLineDash([]);

    // Badge
    ctx.fillStyle = '#238636';
    const text = '🏷️ ' + (lbl.name || 'Marker');
    ctx.font = `bold ${{11 * window.devicePixelRatio}}px sans-serif`;
    const tw = ctx.measureText(text).width;
    ctx.fillRect(lx - tw / 2 - 6, padT - 18, tw + 12, 20 * window.devicePixelRatio);
    ctx.fillStyle = '#ffffff';
    ctx.fillText(text, lx - tw / 2, padT - 4);
  }});
}}

setTimeout(resize, 50);
</script>
</body>
</html>
"""
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
