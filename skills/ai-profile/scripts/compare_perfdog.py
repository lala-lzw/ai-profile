#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AiProfile 与 PerfDog 导出表的对照分析。

读取 AiProfile 会话目录（summary.json）和 PerfDog 导出的 .xlsx，按同名 GPU 计数器配对，
对齐时间轴后按固定窗口取均值，输出 Pearson r、涨跌同向率、对称均值差异和对照图。
仅依赖标准库；--plot 需要 matplotlib。不修改任何原始数据。

用法：
  python compare_perfdog.py <会话目录> <PerfDog.xlsx> --out-dir 输出目录 --plot
"""

import argparse
import csv
import json
import math
import re
import statistics
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

# 图中展示的指标：名称 -> (中文标题, 显示除数, 显示单位)
PLOT_METRICS = {
    "FPS": ("帧率 FPS", 1.0, "fps"),
    "Read Total (Bytes/sec)": ("GPU 总读带宽", 1e6, "MB/s"),
    "Write Total (Bytes/sec)": ("GPU 总写带宽", 1e6, "MB/s"),
    "Fragment Instructions / Second": ("片元指令 / 秒", 1e9, "G 指令/s"),
    "Clocks / Second": ("GPU 周期计数 / 秒", 1e6, "M cycles/s"),
    "GPU % Bus Busy": ("GPU 总线忙碌", 1.0, "%"),
    "% Shaders Stalled": ("着色器停顿", 1.0, "%"),
    "Fragment ALU Instructions / Sec (Full)": ("片元全精度 ALU 指令 / 秒", 1e9, "G 指令/s"),
}


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def column_letter(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def read_perfdog_csv(path: Path):
    """读取精简 CSV（表头与 PerfDog 导出一致：Num、time、FPS、GPU Counter:<组>:<名称>）。"""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        table = list(csv.reader(handle))
    headers = {column_letter(i): name for i, name in enumerate(table[0])}
    samples = [{column_letter(i): cell for i, cell in enumerate(row)} for row in table[1:] if row]
    samples = [r for r in samples if number(r.get("A")) is not None and number(r.get("B")) is not None]
    return headers, samples


def read_perfdog(path: Path):
    """读取 PerfDog 导出表（.xlsx 第一张工作表或精简 .csv），返回 (列名映射, 数据行列表)。"""
    if path.suffix.lower() == ".csv":
        return read_perfdog_csv(path)
    with zipfile.ZipFile(path) as archive:
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            strings = ["".join(si.itertext()) for si in root.findall("m:si", NS)]
        tree = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    rows = []
    for row in tree.findall("m:sheetData/m:row", NS):
        values = {}
        for cell in row:
            column = re.sub(r"\d+", "", cell.attrib["r"])
            kind = cell.attrib.get("t")
            if kind == "s":
                value = strings[int(cell.find("m:v", NS).text)]
            elif kind == "inlineStr":
                value = "".join(cell.find("m:is", NS).itertext())
            else:
                v = cell.find("m:v", NS)
                value = v.text if v is not None else ""
            values[column] = value
        rows.append(values)
    header_index = next(i for i, r in enumerate(rows) if r.get("A") == "Num" and r.get("B") == "time")
    headers = rows[header_index]
    samples = [r for r in rows[header_index + 1:] if number(r.get("A")) is not None and number(r.get("B")) is not None]
    return headers, samples


def bin_means(points, start, end, width):
    """points: [(秒, 值)]；返回每个 width 秒窗口的均值，无有效值为 None。"""
    count = math.ceil((end - start) / width)
    sums = [0.0] * count
    counts = [0] * count
    for t, v in points:
        if v is None or t < start or t > end:
            continue
        j = min(count - 1, int((t - start) // width))
        sums[j] += v
        counts[j] += 1
    return [sums[i] / counts[i] if counts[i] else None for i in range(count)]


def quantile(sorted_values, q):
    pos = (len(sorted_values) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def compare_series(a, b):
    """a: AiProfile 窗口均值，b: PerfDog 窗口均值，返回统计字典。"""
    pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    n = len(pairs)
    if n < 3:
        return dict(n=n, r=None, direction=None, direction_n=0, gap=None, mean_ai=None, mean_perfdog=None)
    av = [p[0] for p in pairs]
    bv = [p[1] for p in pairs]
    try:
        r = statistics.correlation(av, bv)
    except statistics.StatisticsError:
        r = None  # 某一侧为常数
    sa, sb = sorted(av), sorted(bv)
    ta = (quantile(sa, 0.95) - quantile(sa, 0.05)) * 0.02
    tb = (quantile(sb, 0.95) - quantile(sb, 0.05)) * 0.02
    same = total = 0
    for i in range(1, len(a)):
        if None in (a[i - 1], a[i], b[i - 1], b[i]):
            continue
        da, db = a[i] - a[i - 1], b[i] - b[i - 1]
        ka = 0 if abs(da) <= ta else (1 if da > 0 else -1)
        kb = 0 if abs(db) <= tb else (1 if db > 0 else -1)
        if ka == 0 and kb == 0:
            continue
        total += 1
        same += ka == kb
    ma, mb = statistics.fmean(av), statistics.fmean(bv)
    denom = abs(ma) + abs(mb)
    return dict(n=n, r=r, direction=(same / total if total else None), direction_n=total,
                gap=(2 * abs(ma - mb) / denom if denom else 0.0), mean_ai=ma, mean_perfdog=mb)


def build(session: Path, xlsx: Path, bin_s: float, align: str, start_label: str, end_label: str):
    summary = json.loads((session / "summary.json").read_text(encoding="utf-8"))
    period_s = summary["period_ms_configured"] / 1000
    labels = {item["name"]: item for item in summary["labels"]}
    segment = next(s for s in summary["segments"] if s["label_name"] == start_label)
    gpu_start, gpu_end = segment["start_time_s"], segment["end_time_s"]
    fps_start, fps_end = labels[start_label]["time_s"], labels[end_label]["time_s"]
    real, estimated = fps_end - fps_start, gpu_end - gpu_start
    scale = real / estimated if align == "calibrated" else 1.0

    headers, samples = read_perfdog(xlsx)
    pd_times = [number(r["B"]) / 1000 for r in samples]
    gpu_columns = {h.split(":", 2)[-1]: col for col, h in headers.items() if h.startswith("GPU Counter:")}
    fps_column = next((col for col, h in headers.items() if h == "FPS"), None)

    series = {}
    for index, name in enumerate(summary["headers"]):
        if not name or name not in gpu_columns:
            continue
        ai = [((i * period_s - gpu_start) * scale, number(row[index])) for i, row in enumerate(summary["rows"])
              if gpu_start <= i * period_s < gpu_end]
        pd = [(t, number(r.get(gpu_columns[name]))) for t, r in zip(pd_times, samples)]
        series[name] = (ai, pd)
    if fps_column:
        ai = [(number(r["Elapsed (s)"]) - fps_start, number(r["FPS"])) for r in summary["fps_samples"]
              if fps_start <= number(r["Elapsed (s)"]) < fps_end]
        pd = [(t, number(r.get(fps_column))) for t, r in zip(pd_times, samples)]
        series["FPS"] = (ai, pd)

    span = math.floor(real)  # 与离线对比页一致：区间取整数秒，末尾不足 1 秒的尾巴不计
    results = {}
    for name, (ai, pd) in series.items():
        a = bin_means(ai, 0, span, bin_s)
        b = bin_means(pd, 0, span, bin_s)
        results[name] = dict(a=a, b=b, **compare_series(a, b))
    meta = dict(device=summary.get("device", {}),
                bin_s=bin_s, align=align,
                real_duration_s=real, estimated_duration_s=estimated, scale=scale,
                ai_period_ms=summary["period_ms_configured"], perfdog_period_ms=1000)
    return results, meta


def write_csv(results, path: Path):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "pearson_r", "direction_agreement", "direction_n", "symmetric_mean_gap",
                         "paired_bins", "mean_aiprofile", "mean_perfdog"])
        for name, s in results.items():
            writer.writerow([name] + [("" if s[k] is None else s[k]) for k in
                                      ("r", "direction", "direction_n", "gap", "n", "mean_ai", "mean_perfdog")])


def plot(results, meta, path: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    names = [n for n in PLOT_METRICS if n in results]
    cols = 4
    rows_n = math.ceil(len(names) / cols)
    fig, axes = plt.subplots(rows_n, cols, figsize=(cols * 4.2, rows_n * 3.3), squeeze=False)
    teal, orange = "#117c80", "#d5812e"
    for ax in axes.flat:
        ax.set_visible(False)
    for ax, name in zip(axes.flat, names):
        ax.set_visible(True)
        title, divisor, unit = PLOT_METRICS[name]
        res = results[name]
        x = [(i + 0.5) * meta["bin_s"] for i in range(len(res["a"]))]
        for values, color, label in ((res["b"], orange, "PerfDog"), (res["a"], teal, "AiProfile")):
            ys = [None if v is None else v / divisor for v in values]
            ax.plot(x, [float("nan") if v is None else v for v in ys], color=color, lw=1.3, label=label)
        r = "—" if res["r"] is None else f"{res['r']:.3f}"
        d = "—" if res["direction"] is None else f"{res['direction'] * 100:.0f}%"
        ax.set_title(f"{title}  ({unit})", fontsize=10, loc="left", fontweight="bold", pad=22)
        ax.text(0, 1.03, f"r = {r}   涨跌同向 {d}", transform=ax.transAxes, fontsize=8.5, color="#44606b", va="bottom")
        ax.set_xlabel("相对起点时间 (s)", fontsize=8)
        ax.tick_params(labelsize=8)
        ax.grid(alpha=0.25)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, frameon=False, fontsize=10)
    fig.suptitle(f"AiProfile vs PerfDog · {meta['bin_s']:g} 秒均值 · 单设备单次实测", fontsize=12, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0.05, 1, 0.94), h_pad=2.6)
    fig.savefig(path, dpi=140)
    plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description="AiProfile 与 PerfDog 导出表对照分析")
    parser.add_argument("session", type=Path, help="AiProfile 会话目录（含 summary.json）")
    parser.add_argument("perfdog", type=Path, help="PerfDog 导出的 .xlsx，或同表头的精简 .csv")
    parser.add_argument("--out-dir", type=Path, default=Path("."), help="输出目录")
    parser.add_argument("--bin", type=float, default=5.0, help="聚合窗口秒数，默认 5")
    parser.add_argument("--align", choices=("calibrated", "shift"), default="calibrated",
                        help="calibrated=按实际打标时长校正；shift=只平移起点")
    parser.add_argument("--start-label", default=None, help="起点标签，默认第一个标签")
    parser.add_argument("--end-label", default=None, help="终点标签，默认最后一个标签")
    parser.add_argument("--plot", action="store_true", help="输出对照图（需要 matplotlib）")
    args = parser.parse_args(argv)

    summary = json.loads((args.session / "summary.json").read_text(encoding="utf-8"))
    names = [item["name"] for item in summary["labels"]]
    if len(names) < 2:
        parser.error("会话至少需要两个标签（起点与终点）")
    results, meta = build(args.session, args.perfdog, args.bin, args.align,
                          args.start_label or names[0], args.end_label or names[-1])
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(results, args.out_dir / f"perfdog_comparison_{args.align}.csv")
    rs = sorted(s["r"] for s in results.values() if s["r"] is not None)
    print(f"指标 {len(results)} 项，中位 r = {statistics.median(rs):.3f}，r≥0.90 共 {sum(r >= 0.9 for r in rs)} 项")
    if args.plot:
        plot(results, meta, args.out_dir / "perfdog_comparison.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
