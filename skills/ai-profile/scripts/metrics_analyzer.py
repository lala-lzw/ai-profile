#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AiProfile Skill - 硬件计数器统计与物理指标对账分析器 (MetricsAnalyzer)
解析 raw CSV、支持按 PerfDog 标签切分时间轴、计算分段与全景 UBWC 压缩率、
按帧率折算物理单帧指标，并输出打标后的增强 CSV。
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

    def _calc_metrics_from_series(self, series: dict[str, list[float]], row_count: int) -> dict[str, Any]:
        """从数据序列中计算统计指标与整帧换算"""
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
        temp_c = stats.get("Temperature", {}).get("mean", 0.0)

        diagnosis = []
        if total_bw_mb > 1500.0:
            diagnosis.append("总线带宽逼近或超过 1.5 GB/s（发热/功耗高压预警）")
        if tex_read_mb > (total_read_mb * 0.65) and total_read_mb > 500.0:
            diagnosis.append(f"纹理读取占总读取的 {round(tex_read_mb/total_read_mb*100, 1)}%（材质贴图采样为核心带宽瓶颈）")
        if ubwc_pct > 65.0:
            diagnosis.append(f"UBWC 硬件压缩率达到 {ubwc_pct}%（硬件总线压缩利用充分）")
        if temp_c > 48.0:
            diagnosis.append(f"SoC 温度均值高达 {temp_c}°C，已触及温控降频敏感区")

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
            "temperature_c": temp_c,
            "diagnosis": diagnosis,
            "frame_metrics": frame_metrics,
            "raw_stats": stats
        }

    def parse_sdp_csv(
        self,
        csv_path: Path,
        labels: Optional[list[dict[str, Any]]] = None,
        period_ms: int = 200
    ) -> dict[str, Any]:
        """
        解析 sdpcli 导出的 CSV 文件并提取核心统计指标
        - labels: 可选的 PerfDog 模式时间轴标签列表，形如 [{'name': '团战', 'time_s': 12.4}, ...]
        """
        if not csv_path.exists():
            raise FileNotFoundError(f"找不到 CSV 文件: {csv_path}")

        raw_rows: list[dict[str, Any]] = []
        all_series: dict[str, list[float]] = {}
        headers: list[str] = []

        with open(csv_path, "r", encoding="utf-8-sig", errors="ignore") as f:
            reader = csv.DictReader(f)
            headers = [c.strip() for c in reader.fieldnames if c]
            for h in headers:
                all_series[h] = []

            for row in reader:
                parsed_row: dict[str, Any] = {}
                for h in headers:
                    val_s = row.get(h) or row.get(" " + h)
                    val = None
                    if val_s and val_s.strip() != "N/A":
                        try:
                            val = float(val_s.strip())
                            all_series[h].append(val)
                        except ValueError:
                            pass
                    parsed_row[h] = val
                raw_rows.append(parsed_row)

        overall = self._calc_metrics_from_series(all_series, len(raw_rows))

        # 处理 PerfDog 模式的标签分段画像
        segments: list[dict[str, Any]] = []
        labeled_csv_path: Optional[Path] = None

        if labels and raw_rows:
            # 排序标签
            sorted_labels = sorted(labels, key=lambda x: x.get("time_s", 0.0))
            
            # 为每个样本行打上 Label
            # 样本的时刻 (秒) = 行号 * (period_ms / 1000.0)
            sec_per_row = period_ms / 1000.0
            
            # 构建分段区间: [(label_name, start_idx, end_idx)]
            intervals: list[tuple[str, int, int, float, float]] = []
            
            first_label_time = sorted_labels[0].get("time_s", 0.0)
            first_idx = min(len(raw_rows), max(0, int(first_label_time / sec_per_row)))
            
            if first_idx > 0:
                intervals.append(("初始阶段", 0, first_idx, 0.0, first_label_time))
            
            for i, lb in enumerate(sorted_labels):
                name = lb.get("name", f"Tag_{i+1}")
                st_time = lb.get("time_s", 0.0)
                st_idx = min(len(raw_rows), max(0, int(st_time / sec_per_row)))
                
                if i + 1 < len(sorted_labels):
                    end_time = sorted_labels[i+1].get("time_s", 0.0)
                    end_idx = min(len(raw_rows), max(st_idx, int(end_time / sec_per_row)))
                else:
                    end_time = len(raw_rows) * sec_per_row
                    end_idx = len(raw_rows)
                    
                intervals.append((name, st_idx, end_idx, st_time, end_time))

            # 写入带 Label 列的增强 CSV
            labeled_csv_path = csv_path.parent / f"{csv_path.stem}_labeled.csv"
            with open(labeled_csv_path, "w", newline="", encoding="utf-8-sig") as out_f:
                writer = csv.writer(out_f)
                writer.writerow(["Time (s)", "PerfDog Label", *headers])
                
                for idx, r in enumerate(raw_rows):
                    cur_time = round(idx * sec_per_row, 3)
                    # 查找对应 label
                    cur_label = ""
                    for (lbl_name, s_idx, e_idx, _, _) in intervals:
                        if s_idx <= idx < e_idx:
                            cur_label = lbl_name
                            break
                    if not cur_label and intervals:
                        cur_label = intervals[-1][0]
                    
                    row_vals = [cur_time, cur_label]
                    for h in headers:
                        row_vals.append(r.get(h, ""))
                    writer.writerow(row_vals)

            # 计算各分段画像指标
            for (lbl_name, s_idx, e_idx, s_time, e_time) in intervals:
                seg_rows = raw_rows[s_idx:e_idx]
                if not seg_rows:
                    continue
                seg_series: dict[str, list[float]] = {h: [] for h in headers}
                for r in seg_rows:
                    for h in headers:
                        val = r.get(h)
                        if val is not None:
                            seg_series[h].append(val)
                seg_summary = self._calc_metrics_from_series(seg_series, len(seg_rows))
                seg_summary["label_name"] = lbl_name
                seg_summary["start_time_s"] = round(s_time, 1)
                seg_summary["end_time_s"] = round(e_time, 1)
                seg_summary["duration_s"] = round(e_time - s_time, 1)
                segments.append(seg_summary)

        overall["segments"] = segments
        overall["labels"] = labels or []
        overall["labeled_csv"] = str(labeled_csv_path) if labeled_csv_path else None
        return overall
