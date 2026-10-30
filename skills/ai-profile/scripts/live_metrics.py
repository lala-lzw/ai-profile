"""Preview complete CLI CSV records, preserving names, cells and source lines."""

import csv
import shlex

from cli_data import cell_findings
from gpu_metrics import project_counters


def parse_counter_tail(text):
    records=list(csv.reader(text.splitlines()))
    if len(records)<2:
        return {}
    header=records[0]
    for row in reversed(records[1:]):
        if len(row)!=len(header) or row==header:
            continue
        return {column:row[index] for index,column in enumerate(header) if column}
    return {}


class LiveMetricsReader:
    def __init__(self, adb):
        self.adb=adb
        self.source_file = None
        self.source_line = 1

    def reset(self):
        self.source_file = None
        self.source_line = 1

    def read(self, session):
        remote=session.get("remote_tmp_dir")
        if not remote:
            return {"counter_ready":False,"cli_metrics":{},"cli_raw":{}}
        directory=shlex.quote(remote)
        # Fetch every complete new record. UI polling can be slower than CLI
        # sampling, so reading only the tail discards brief spikes between polls.
        previous = shlex.quote(self.source_file or "")
        next_line = self.source_line + 1
        command=(f'for file in {directory}/*.csv; do if test -f "$file"; then '
                 'lines=$(wc -l < "$file"); '
                 f'if test "$file" = {previous} && test "$lines" -ge {self.source_line}; '
                 f'then start={next_line}; else start=2; fi; '
                 'end=$((start + 1999)); if test "$end" -gt "$lines"; then end=$lines; fi; '
                 'printf "%s\\n%s\\n" "$file" "$lines"; '
                 'sed -n "1p" "$file"; if test "$end" -ge "$start"; then '
                 'sed -n "${start},${end}p" "$file"; fi; break; fi; done')
        response=self.adb.shell(command,timeout=5)
        if not response.ok:
            raise RuntimeError(response.stderr or "读取 CLI CSV 失败")
        parts=response.stdout.splitlines()
        if len(parts)<4 or not parts[1].strip().isdigit():
            return {"counter_ready":False,"cli_metrics":{},"cli_raw":{}}
        file, complete_lines = parts[0], int(parts[1].strip())
        reset_stream = file != self.source_file or complete_lines < self.source_line
        start = self.source_line + 1 if file == self.source_file and complete_lines >= self.source_line else 2
        records = list(csv.reader(parts[2:]))
        header, rows = records[0], records[1:]
        samples = []
        for index, row in enumerate(rows):
            source_line = start + index
            raw = {column:row[i] if i<len(row) else "" for i,column in enumerate(header) if column}
            numeric = project_counters(raw)
            findings = [{"line":source_line,"column":column,"value":value,"reason":reason}
                        for column,value in raw.items() for reason in cell_findings(column,value)]
            if len(row) != len(header):
                findings.append({"line":source_line,"column":"","value":"",
                                 "reason":f"CLI 列数不一致：{len(row)} / {len(header)}"})
            samples.append({"counter_ready":bool(raw),"cli_metrics":numeric,"cli_raw":raw,
                            "source_line":source_line,"source_file":file,"findings":findings})
        self.source_file = file
        self.source_line = start + len(rows) - 1
        if not samples:
            return {"counter_ready":False,"cli_metrics":{},"cli_raw":{},"samples":[]}
        return {**samples[-1],"samples":samples,"reset_stream":reset_stream}
