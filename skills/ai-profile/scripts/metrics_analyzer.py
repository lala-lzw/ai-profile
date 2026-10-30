#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AiProfile Skill - 硬件计数器统计与物理指标对账分析器 (MetricsAnalyzer)
解析 raw CSV、计算 UBWC 硬件无损压缩率、按帧率折算物理单帧指标，并给出瓶颈诊断。
"""

import csv
import math
from pathlib import Path
from typing import Any, Optional

def _pct(values: list[float], p: float) -> float:
    if not values: return 0.0
    sorted_v = sorted(values)
    k = (len(sorted_v) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_v[int(k)]
    d0 = sorted_v[int(f)] * (c - k)
    d1 = sorted_v[int(c)] * (k - f)
    return d0 + d1

class MetricsAnalyzer:
    def __init__(self, fps_baseline: float = 60.0):
        self.fps_baseline = fps_baseline

    def parse_sdp_csv(self, csv_path: Path) -> dict[str, Any]:
        """解析 sdpcli 导出的 CSV 文件并提取核心统计指标"""
        if not csv_path.exists():
            raise FileNotFoundError(f"找不到 CSV 文件: {csv_path}")

        series: dict[str, list[float]] = {}
        row_count = 0

        with open(csv_path, "r", encoding="utf-8-sig", errors="ignore") as f:
            reader = csv.DictReader(f)
            headers = [c.strip() for c in reader.fieldnames if c]
            for h in headers:
                series[h] = []

            for row in reader:
                row_count += 1
                for h in headers:
                    val_s = row.get(h) or row.get(" " + h)
                    if val_s and val_s.strip() != "N/A":
                        try:
                            val = float(val_s.strip())
                            series[h].append(val)
                        except ValueError:
                            pass

        stats: dict[str, dict[str, float]] = {}
        for h, vals in series.items():
            if vals:
                mean_v = sum(vals) / len(vals)
                median_v = _pct(vals, 50.0)
                p95_v = _pct(vals, 95.0)
                min_v = min(vals)
                max_v = max(vals)
                stats[h] = {
                    "count": len(vals),
                    "mean": round(mean_v, 2),
                    "median": round(median_v, 2),
                    "p95": round(p95_v, 2),
                    "min": round(min_v, 2),
                    "max": round(max_v, 2)
                }

        # 计算 UBWC 硬件无损压缩率
        comp_series = series.get("Global Image Compressed Data Read BW (Bytes/sec)", [])
        uncomp_series = series.get("Global Image Uncompressed Data Read BW (Bytes/sec)", [])
        ubwc_pct = 0.0
        if comp_series and uncomp_series:
            tot_comp = sum(comp_series)
            tot_uncomp = sum(uncomp_series)
            if (tot_comp + tot_uncomp) > 0:
                ubwc_pct = round(tot_comp / (tot_comp + tot_uncomp) * 100.0, 2)

        # 换算单帧整帧值 (除以 FPS)
        fps = self.fps_baseline
        frame_metrics: dict[str, Any] = {}
        for h, st in stats.items():
            m_sec = st["mean"]
            if "Bytes/sec" in h or "Bytes/Second" in h:
                bytes_per_frame = m_sec / fps
                frame_metrics[h] = {
                    "sec_val": m_sec,
                    "sec_mb": round(m_sec / (1024 * 1024), 2),
                    "frame_bytes": round(bytes_per_frame, 0),
                    "frame_mb": round(bytes_per_frame / (1024 * 1024), 2)
                }
            elif "/sec" in h or "/ Second" in h or "/ second" in h:
                count_per_frame = m_sec / fps
                frame_metrics[h] = {
                    "sec_val": m_sec,
                    "sec_m": round(m_sec / 1e6, 2),
                    "frame_count": round(count_per_frame, 0),
                    "frame_m": round(count_per_frame / 1e6, 2)
                }
            else:
                frame_metrics[h] = {
                    "mean": st["mean"],
                    "p95": st["p95"]
                }

        total_read_mb = frame_metrics.get("Read Total (Bytes/sec)", {}).get("sec_mb", 0.0)
        total_write_mb = frame_metrics.get("Write Total (Bytes/sec)", {}).get("sec_mb", 0.0)
        total_bw_mb = round(total_read_mb + total_write_mb, 2)
        total_bw_frame_mb = round(total_bw_mb / fps, 2)

        tex_read_mb = frame_metrics.get("Texture Memory Read BW (Bytes/Second)", {}).get("sec_mb", 0.0)
        gpu_util = stats.get("GPU % Utilization", {}).get("mean", 0.0)
        gpu_clk = stats.get("Clocks / Second", {}).get("mean", 0.0) / 1e6
        frag_shaded_m = frame_metrics.get("Fragments Shaded / Second", {}).get("frame_m", 0.0)

        diagnosis = []
        if total_bw_mb > 1500.0:
            diagnosis.append("总线带宽逼近或超过 1.5 GB/s（发热/功耗高压预警）")
        if tex_read_mb > (total_read_mb * 0.65) and total_read_mb > 500.0:
            diagnosis.append(f"纹理读取占总读取的 {round(tex_read_mb/total_read_mb*100, 1)}%（材质贴图采样为核心带宽瓶颈）")
        if ubwc_pct > 65.0:
            diagnosis.append(f"UBWC 硬件压缩率达到 {ubwc_pct}%（硬件总线压缩利用充分）")

        return {
            "row_count": row_count,
            "fps_baseline": fps,
            "total_bw_sec_mb": total_bw_mb,
            "total_bw_frame_mb": total_bw_frame_mb,
            "read_bw_sec_mb": total_read_mb,
            "write_bw_sec_mb": total_write_mb,
            "tex_read_sec_mb": tex_read_mb,
            "gpu_util_pct": gpu_util,
            "gpu_clk_mhz": round(gpu_clk, 2),
            "fragments_frame_m": frag_shaded_m,
            "ubwc_compressed_pct": ubwc_pct,
            "diagnosis": diagnosis,
            "frame_metrics": frame_metrics,
            "raw_stats": stats
        }

