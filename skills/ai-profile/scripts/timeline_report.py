"""Embed original CLI strings and original CSV bytes in an offline viewer."""

from dataclasses import asdict
import bisect
import json
from pathlib import Path

from cli_data import read_cli_csv
from gpu_metrics import CHARTS, OVERVIEW, metric_for
from fps_reader import load_fps_samples
from display_units import display_spec


def prepare_stages(segments, labels, source_lines, period_ms=200):
    """Keep source-row intervals and wall-clock marker intervals separate."""
    if not source_lines:
        return []
    markers = sorted(labels or [], key=lambda marker: marker.get("time_s", 0))
    marker_lines = []
    for marker in markers:
        line = marker.get("source_line")
        if line is None:
            index = min(len(source_lines)-1, int(max(0, marker.get("time_s", 0))*1000/period_ms))
            line = source_lines[index]
        marker_lines.append(int(line))
    stages = []
    for index, segment in enumerate(segments or [{"label_name":"全程", "source_start_line":source_lines[0],
                                                  "source_end_line":source_lines[-1], "boundary_basis":"source_rows"}]):
        start = segment.get("source_start_line", source_lines[0])
        end = segment.get("source_end_line", source_lines[-1])
        marker_index = bisect.bisect_right(marker_lines, start)-1
        marker = markers[marker_index] if marker_index >= 0 else None
        next_marker = markers[marker_index+1] if marker_index+1 < len(markers) else None
        stages.append({"id":f"stage-{index}", "label_name":segment.get("label_name", ""),
                       "source_start_line":start, "source_end_line":end,
                       "row_count":bisect.bisect_right(source_lines, end)-bisect.bisect_left(source_lines, start),
                       "boundary_basis":segment.get("boundary_basis", "estimated_from_configured_period"),
                       "is_marked":marker is not None,
                       "time_start_s":marker.get("time_s", 0) if marker else 0,
                       "time_end_s":next_marker.get("time_s") if next_marker else None})
    return stages


def generate_timeline(tag, result, output, device=None, memory=None, timestamp=None):
    dataset = result.get("raw_data")
    if dataset is None:
        source = result.get("raw_csv") or result.get("labeled_csv")
        if source and Path(source).is_file():
            metadata = () if result.get("raw_csv") else ("Time (s)","PerfDog Label","AiProfile Source Line")
            dataset = read_cli_csv(source, metadata)
        else:
            dataset = {"headers":[],"rows":[],"sourceLines":[],"displayIndices":[],
                       "findings":[],"sourceName":"","sourceSha256":"","sourceBase64":""}
    raw_columns = {dataset["headers"][i]: [row[i] if i < len(row) else "" for row in dataset["rows"]]
                   for i in dataset["displayIndices"]}
    specs = [metric_for(column, i) for i, column in enumerate(raw_columns)]
    charts = []
    for chart_id, section, title, unit, limit in CHARTS:
        items = [{"key": spec.key, "label": spec.column, "column": spec.column}
                 for spec in specs if spec.chart == chart_id]
        if items:
            charts.append({"id":chart_id,"section":section,"title":title,
                           "unit":"CLI raw","limit":None,"items":items})
    overview = [{"key":metric.column,"label":metric.column,"column":metric.column,"unit":""}
                for metric in OVERVIEW if metric.column in raw_columns]
    segments = prepare_stages(result.get("segments", []), result.get("labels", []),
                              dataset["sourceLines"], result.get("period_ms", 200))
    fps_path = result.get("fps_csv")
    if not fps_path and result.get("raw_csv"):
        fps_path = Path(result["raw_csv"]).with_name("fps.csv")
    fps_samples = load_fps_samples(fps_path) if fps_path else []
    period_ms = result.get("period_ms") or 200
    data = {"tag":tag,"timestamp":timestamp,"device":device or {},"memory":memory or {},
            "sampleCount":len(dataset["rows"]),"sourceLines":dataset["sourceLines"],
            "sampleTimes":[round(index*period_ms/1000, 9) for index in range(len(dataset["rows"]))],
            "periodMs":period_ms,"timeBasis":"configured_sampling_interval",
            "rawColumns":raw_columns,"charts":charts,"overview":overview,"segments":segments,
            "labels":result.get("labels",[]),"metricSpecs":[asdict(spec) for spec in specs],
            "findings":dataset["findings"],"sourceName":dataset["sourceName"],
            "sourceSha256":dataset["sourceSha256"],"sourceBase64":dataset["sourceBase64"],
            "fpsSamples":fps_samples,
            "displayUnits":{column:display_spec(column) for column in raw_columns}}
    script = json.dumps(data,ensure_ascii=False,allow_nan=False).replace("<","\\u003c").replace("\u2028","\\u2028").replace("\u2029","\\u2029")
    template = Path(__file__).with_name("timeline_template.html").read_text(encoding="utf-8")
    output = Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(template.replace("/*__REPORT_DATA__*/",f"const report = {script};"),encoding="utf-8")
