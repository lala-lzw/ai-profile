"""Write source-preserving CLI reports and a separate review log."""

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from cli_data import read_cli_csv
from gpu_metrics import OVERVIEW
from fps_reader import SOURCE as FPS_SOURCE, load_fps_samples


class ReportEngine:
    @staticmethod
    def generate_single_report(tag: str, analyzer_res: dict[str, Any], device_info: dict,
                               memory_info: dict, output_dir: Path,
                               timestamp_utc: Optional[str] = None) -> Path:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = timestamp_utc or datetime.now(timezone.utc).isoformat()
        dataset = analyzer_res.get("raw_data") or read_cli_csv(analyzer_res["raw_csv"])
        fps_path = Path(analyzer_res.get("fps_csv") or output_dir/"raw"/"fps.csv")
        fps_samples = load_fps_samples(fps_path)
        summary = {"schema": "sdpcli-raw-v1", "timestamp_utc": timestamp, "tag": tag,
                   "device": device_info, "memory": memory_info,
                   "source_file": dataset["sourceName"], "source_sha256": dataset["sourceSha256"],
                   "headers": dataset["headers"], "rows": dataset["rows"],
                   "source_lines": dataset["sourceLines"],
                   "period_ms_configured": analyzer_res.get("period_ms"),
                   "last_source_line": analyzer_res.get("last_source_line"),
                   "last_sample": analyzer_res.get("last_sample", {}),
                   "segments": analyzer_res.get("segments", []), "labels": analyzer_res.get("labels", []),
                   "review_flags": dataset["findings"],
                   "fps_source":FPS_SOURCE,"fps_samples":fps_samples}
        (output_dir/"summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

        def escape(value):
            return str(value).replace("|", "\\|").replace("\n", " ")

        sample = analyzer_res.get("last_sample", {})
        lines = [f"# {escape(tag)} — sdpcli 原始数据\n",
                 f"- 来源文件：`{dataset['sourceName']}`",
                 f"- SHA-256：`{dataset['sourceSha256']}`",
                 f"- 原始数据行数：{len(dataset['rows'])}",
                 f"- 当前样本：CSV 文件第 {analyzer_res.get('last_source_line', '—')} 行",
                 "- 指标使用 CLI 原始列名、原始字符串和原始单位。",
                 "- [交互查看原始样本](timeline.html) | [数据核查记录](data_audit.md)\n",
                 "## GPU 原始样本\n", "| CLI 原始列名 | CLI 原始值 |", "| :--- | ---: |"]
        for metric in OVERVIEW:
            lines.append(f"| `{metric.column}` | `{escape(sample.get(metric.column, '未采集'))}` |")
        if fps_samples:
            latest = fps_samples[-1]
            lines.extend(["\n## FPS\n",f"- 来源：{FPS_SOURCE}；目标应用呈现帧时间戳。",
                          f"- 最新值：`{escape(latest.get('FPS') or '未获得有效帧间隔')}`",
                          "- [FPS 采样数据](raw/fps.csv) | [原始帧时间戳](raw/surfaceflinger_frames.csv)",
                          "- FPS 单独保存，不更改 CLI 原始 CSV。"])
        lines.extend(["\n## 当前样本全部 CLI 列\n", "| CLI 原始列名 | CLI 原始值 |", "| :--- | ---: |"])
        for column, value in sample.items():
            lines.append(f"| `{escape(column)}` | `{escape(value)}` |")
        lines.extend(["\n## 阶段与来源行\n", "| 阶段 | 起始 CSV 行 | 结束 CSV 行 | 样本数 | 边界依据 |",
                      "| :--- | ---: | ---: | ---: | :--- |"])
        for segment in analyzer_res.get("segments", []):
            basis = "按配置间隔估算，非 CLI 时间戳" if segment.get("boundary_basis")=="estimated_from_configured_period" else "来源行"
            lines.append(f"| {escape(segment['label_name'])} | {segment['source_start_line']} | {segment['source_end_line']} | {segment['row_count']} | {basis} |")
        (output_dir/"summary.md").write_text("\n".join(lines), encoding="utf-8")
        audit = ["# CLI 数据核查\n",
                 "以下为待核实项；所有数值保留原文，未自动修正或剔除。量级提示不是物理有效性结论。\n",
                 f"来源：`{dataset['sourceName']}`；SHA-256：`{dataset['sourceSha256']}`。\n",
                 "| 原始 CSV 行 | CLI 列名 | 原始值 | 待核实原因 |", "| ---: | :--- | ---: | :--- |"]
        for item in dataset["findings"]:
            audit.append(f"| {item['line']} | `{escape(item['column'])}` | `{escape(item['value'])}` | {escape(item['reason'])} |")
        if not dataset["findings"]:
            audit.append("| — | — | — | 本轮规则未标记数值；不表示已验证硬件计数器正确性。 |")
        (output_dir/"data_audit.md").write_text("\n".join(audit), encoding="utf-8")
        with (output_dir/"data_audit.csv").open("w", newline="", encoding="utf-8-sig") as stream:
            writer=csv.DictWriter(stream, fieldnames=("line","column","value","reason"))
            writer.writeheader(); writer.writerows(dataset["findings"])
        ReportEngine._generate_timeline_html(tag, analyzer_res, output_dir/"timeline.html", device_info, memory_info, timestamp)
        return output_dir/"summary.md"

    @staticmethod
    def _generate_timeline_html(tag, analyzer_res, html_path, device_info=None, memory_info=None, timestamp=None):
        from timeline_report import generate_timeline
        generate_timeline(tag, analyzer_res, html_path, device_info, memory_info, timestamp)
