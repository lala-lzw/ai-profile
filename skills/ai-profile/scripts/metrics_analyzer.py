"""Index original CLI rows and markers without normalizing counter values."""

import bisect
import csv
from pathlib import Path
from typing import Any, Optional

from cli_data import cells_at, read_cli_csv


class MetricsAnalyzer:
    def __init__(self, fps_baseline=60.0):
        # Kept as a call-site compatibility argument. No per-frame conversion is performed.
        pass

    def parse_sdp_csv(self, csv_path: Path, labels: Optional[list[dict[str, Any]]] = None,
                      period_ms: int = 200) -> dict[str, Any]:
        csv_path = Path(csv_path)
        dataset = read_cli_csv(csv_path)
        count = len(dataset["rows"])
        if period_ms <= 0:
            raise ValueError("采样间隔必须大于零")
        ordered = sorted(labels or [], key=lambda marker: marker.get("time_s", 0))
        boundaries = []
        for marker in ordered:
            if marker.get("source_line") is not None:
                index = bisect.bisect_left(dataset["sourceLines"], int(marker["source_line"]))
                basis = "latest_observed_cli_line"
            else:
                index = int(max(0, marker.get("time_s", 0)) * 1000 / period_ms)
                basis = "estimated_from_configured_period"
            boundaries.append((min(count, index), marker.get("name", "Marker"), basis))
        intervals = []
        if count:
            if not boundaries:
                intervals.append((0, count, "全程", "source_rows"))
            elif boundaries[0][0] > 0:
                intervals.append((0, boundaries[0][0], "初始阶段", boundaries[0][2]))
            for index, (start, name, basis) in enumerate(boundaries):
                end = boundaries[index+1][0] if index+1 < len(boundaries) else count
                if start < end:
                    intervals.append((start, end, name, basis))
        segments = []
        row_labels = [""] * count
        for start, end, name, basis in intervals:
            row_labels[start:end] = [name] * (end-start)
            segments.append({"label_name": name, "row_count": end-start,
                             "source_start_line": dataset["sourceLines"][start],
                             "source_end_line": dataset["sourceLines"][end-1],
                             "start_index": start, "end_index": end,
                             "boundary_basis": basis,
                             "start_time_s": start * period_ms / 1000,
                             "end_time_s": end * period_ms / 1000,
                             "duration_s": (end-start) * period_ms / 1000,
                             "last_source_line": dataset["sourceLines"][end-1],
                             "last_sample": cells_at(dataset, end-1)})
        labeled = None
        if count:
            labeled = csv_path.with_name(f"{csv_path.stem}_labeled.csv")
            with labeled.open("w", newline="", encoding="utf-8-sig") as stream:
                writer = csv.writer(stream)
                writer.writerow(["AiProfile Source Line", "PerfDog Label", *dataset["headers"]])
                for index, row in enumerate(dataset["rows"]):
                    writer.writerow([dataset["sourceLines"][index], row_labels[index], *row])
        return {"raw_csv": str(csv_path.resolve()), "raw_data": dataset,
                "row_count": count, "period_ms": period_ms,
                "last_source_line": dataset["sourceLines"][-1] if count else None,
                "last_sample": cells_at(dataset, count-1),
                "segments": segments, "labels": labels or [],
                "labeled_csv": str(labeled.resolve()) if labeled else None}
