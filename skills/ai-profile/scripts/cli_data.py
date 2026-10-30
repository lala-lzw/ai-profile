"""Lossless CSV cells and conservative review flags; never repairs source data."""

import base64
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import io
import math
from pathlib import Path


def numeric(text):
    try:
        value = float(text)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError, OverflowError):
        return None


def cell_findings(column, text):
    try:
        value = Decimal(text)
    except (InvalidOperation, TypeError, ValueError):
        return []
    if not value.is_finite():
        return ["CLI 非有限值；保留原文，曲线留空"]
    findings = []
    if "%" in column and not 0 <= value <= 100:
        findings.append("百分比超出 0～100，需核对 CLI 输出")
    if column == "Avg Preemption Delay" and abs(value) >= Decimal("1e9"):
        findings.append("数量级较大，且 CLI 列名未注明时间单位；待核实")
    if column == "Preemptions / second" and abs(value) >= 10000:
        findings.append("每秒计数达到万级；需核对计数器定义与采样有效性")
    return findings


def read_cli_csv(path, metadata_columns=()):
    path = Path(path)
    source = path.read_bytes()
    reader = csv.reader(io.StringIO(source.decode("utf-8-sig"), newline=""))
    headers = next(reader, [])
    named = [header for header in headers if header]
    if len(named) != len(set(named)):
        raise ValueError(f"CLI CSV 含重复列名，不能安全映射：{path}")
    indices = [i for i, header in enumerate(headers) if header and header not in metadata_columns]
    rows, lines, findings = [], [], []
    while True:
        source_line = reader.line_num + 1
        try:
            row = next(reader)
        except StopIteration:
            break
        rows.append(row)
        lines.append(source_line)
        if len(row) != len(headers):
            findings.append({"line": source_line, "column": "", "value": "",
                             "reason": f"列数不一致：应为 {len(headers)}，实际 {len(row)}"})
        for index in indices:
            text = row[index] if index < len(row) else ""
            for reason in cell_findings(headers[index], text):
                findings.append({"line": source_line, "column": headers[index],
                                 "value": text, "reason": reason})
    return {"headers": headers, "rows": rows, "sourceLines": lines,
            "displayIndices": indices, "findings": findings,
            "sourceName": path.name, "sourceSha256": hashlib.sha256(source).hexdigest(),
            "sourceBase64": base64.b64encode(source).decode("ascii")}


def cells_at(dataset, index):
    if not 0 <= index < len(dataset["rows"]):
        return {}
    row = dataset["rows"][index]
    return {dataset["headers"][i]: row[i] if i < len(row) else ""
            for i in dataset["displayIndices"]}
