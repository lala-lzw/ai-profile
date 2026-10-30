#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AiProfile Skill - 通用截帧相机聚合过滤与对账工具 (CameraFilter)
针对 Unity URP (GLES/Vulkan) 截帧，从原始 CSV 中直接提取各相机根节点并相加 (Main + UI)，
消除整列 SUM 产生的父子重复累加陷阱，产出权威单帧基准。
"""

import csv
from pathlib import Path
from typing import Any, Optional

def parse_num(v: Any) -> float:
    if v is None: return 0.0
    v = str(v).strip()
    if not v or v.upper() == 'N/A': return 0.0
    try:
        return float(v)
    except ValueError:
        return 0.0

class CameraFilter:
    @staticmethod
    def extract_cameras_and_sum(raw_csv_path: Path, output_filtered_csv: Optional[Path] = None) -> dict[str, Any]:
        """从 Snapdragon Profiler 导出的原始 CSV 中提取各相机行并求和"""
        raw_path = Path(raw_csv_path).resolve()
        if not raw_path.exists():
            raise FileNotFoundError(f"找不到截帧 CSV 文件: {raw_path}")

        with open(raw_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
            reader = csv.DictReader(f)
            headers = [c.strip() for c in reader.fieldnames if c]
            
            camera_rows = []
            for line_idx, r in enumerate(reader, start=2):
                cname = ""
                for k in ['Name', ' Name']:
                    if k in r and r[k]:
                        cname = r[k].strip()
                        break
                if 'RenderSingleCamera' in cname:
                    row_data = {'Original_Line': line_idx, 'Camera_Node': cname}
                    for h in headers:
                        if h in ['ID', 'Name', 'Parameters', 'Context', 'Thread']:
                            continue
                        val = r.get(h) or r.get(' ' + h) or r.get(h.strip())
                        row_data[h] = parse_num(val)
                    camera_rows.append(row_data)

        if not camera_rows:
            raise ValueError(f"在 {raw_path} 中未检测到 'RenderSingleCamera' 标记节点！")

        # 按照相机相加 (Main Camera + UICamera)
        tot_row = {'Original_Line': 'SUM', 'Camera_Node': 'TOTAL (Main Camera + UICamera)'}
        first_row = camera_rows[0]
        metric_keys = [k for k in first_row.keys() if k not in ['Original_Line', 'Camera_Node']]

        tot_clocks = sum(c.get('Clocks', 0.0) for c in camera_rows)

        for k in metric_keys:
            if k.startswith('%') or 'Per' in k or 'Average' in k or 'Avg' in k or 'ALU /' in k or 'EFU /' in k or 'Textures /' in k:
                if tot_clocks > 0:
                    weighted_val = sum(c.get(k, 0.0) * c.get('Clocks', 0.0) for c in camera_rows) / tot_clocks
                else:
                    weighted_val = camera_rows[0].get(k, 0.0)
                tot_row[k] = round(weighted_val, 2)
            else:
                tot_val = sum(c.get(k, 0.0) for c in camera_rows)
                tot_row[k] = int(tot_val) if tot_val.is_integer() else round(tot_val, 2)

        if output_filtered_csv:
            output_filtered_csv = Path(output_filtered_csv).resolve()
            output_filtered_csv.parent.mkdir(parents=True, exist_ok=True)
            field_order = ['Original_Line', 'Camera_Node'] + metric_keys
            with open(output_filtered_csv, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=field_order)
                writer.writeheader()
                for cr in camera_rows:
                    writer.writerow(cr)
                writer.writerow(tot_row)

        return {
            'cameras': camera_rows,
            'total': tot_row,
            'filtered_csv': str(output_filtered_csv) if output_filtered_csv else None
        }

