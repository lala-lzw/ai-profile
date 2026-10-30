"""CLI names and raw values shared by all viewers; grouping never changes a counter."""

from dataclasses import dataclass
from cli_data import numeric


@dataclass(frozen=True)
class Metric:
    column: str
    key: str
    label: str
    unit: str = ""
    divisor: float = 1
    section: str = "gpu"
    chart: str = ""


GROUPS = [('gpu-load', 'gpu', 'GPU General', ('GPU % Utilization', 'GPU % Bus Busy')),
 ('gpu-cycles', 'gpu', 'Clocks / Second', ('Clocks / Second',)),
 ('gpu-shader',
  'shader',
  'Shader',
  ('% Shaders Busy', '% Shader ALU Capacity Utilized', '% Wave Context Occupancy')),
 ('gpu-texture', 'shader', '% Texture Pipes Busy', ('% Texture Pipes Busy',)),
 ('gpu-fragments', 'shader', 'Fragments Shaded / Second', ('Fragments Shaded / Second',)),
 ('gpu-vertex-instructions', 'shader', 'Vertex Instructions / Second', ('Vertex Instructions / Second',)),
 ('gpu-fragment-instructions',
  'shader',
  'Fragment Instructions / Second',
  ('Fragment Instructions / Second',)),
 ('gpu-precision',
  'shader',
  'Fragment ALU / EFU',
  ('Fragment ALU Instructions / Sec (Full)',
   'Fragment ALU Instructions / Sec (Half)',
   'Fragment EFU Instructions / Second')),
 ('gpu-allocation', 'shader', '% Time Shading Fragments', ('% Time Shading Fragments',)),
 ('gpu-stalls',
  'stalls',
  'Stalls',
  ('% Texture Fetch Stall', '% Shaders Stalled', '% Stalled on System Memory')),
 ('gpu-cache',
  'stalls',
  'Cache',
  ('% Instruction Cache Miss', '% Texture L1 Miss', '% Texture L2 Miss', '% Image Read L2 Hit')),
 ('bandwidth', 'bandwidth', 'GPU Memory', ('Read Total (Bytes/sec)', 'Write Total (Bytes/sec)')),
 ('memory-breakdown',
  'bandwidth',
  'Memory Read',
  ('Texture Memory Read BW (Bytes/Second)',
   'Vertex Memory Read (Bytes/Second)',
   'SP Memory Read (Bytes/Second)')),
 ('gpu-image-read',
  'bandwidth',
  'Image Read',
  ('Global Image Compressed Data Read BW (Bytes/sec)', 'Global Image Uncompressed Data Read BW (Bytes/sec)')),
 ('cpu-load',
  'cpu',
  'CPU',
  ('CPU 0 Core Utilization',
   'CPU 1 Core Utilization',
   'CPU 2 Core Utilization',
   'CPU 3 Core Utilization',
   'CPU 4 Core Utilization',
   'CPU 5 Core Utilization',
   'CPU 6 Core Utilization',
   'CPU 7 Core Utilization')),
 ('cpu-clock',
  'cpu',
  'CPU Frequency',
  ('CPU 0 Core Frequency',
   'CPU 1 Core Frequency',
   'CPU 2 Core Frequency',
   'CPU 3 Core Frequency',
   'CPU 4 Core Frequency',
   'CPU 5 Core Frequency',
   'CPU 6 Core Frequency',
   'CPU 7 Core Frequency')),
 ('memory-usage', 'memory', 'Memory', ('Used Memory', 'Available Memory', 'Free Memory', 'Total Memory')),
 ('temperature', 'temperature', 'Temperature', ('Temperature',))]
GROUPS += [
    ("gpu-preemptions","gpu","Preemptions / second",("Preemptions / second",)),
    ("gpu-preemption-delay","gpu","Avg Preemption Delay",("Avg Preemption Delay",)),
]

CHARTS = [(key, section, title, "", None) for key, section, title, columns in GROUPS]
METRICS = [Metric(column, column, column, section=section, chart=key)
           for key, section, title, columns in GROUPS for column in columns]
BY_COLUMN = {metric.column: metric for metric in METRICS}
OVERVIEW = [BY_COLUMN[column] for column in (
    "GPU % Utilization", "% Shaders Busy", "% Shader ALU Capacity Utilized", "% Texture Pipes Busy",
    "Fragments Shaded / Second", "Vertex Instructions / Second", "Fragment Instructions / Second", "% Texture Fetch Stall",
)]


def metric_for(column, index=0):
    return BY_COLUMN.get(column, Metric(column, column, column, section="cpu" if column.startswith("CPU ") else "gpu"))


def finite(value):
    return numeric(value)


def project_counters(values):
    # Numbers are used only for plot coordinates. Visible cells use their original strings.
    return {column: value for column, text in values.items() if (value := numeric(text)) is not None}


def console_gpu_summary(result):
    row = result.get("last_sample", {})
    lines = [f"[sdpcli 原始样本 · CSV 行 {result.get('last_source_line', '—')}]"]
    for metric in OVERVIEW + [BY_COLUMN["Clocks / Second"]]:
        lines.append(f"   {metric.column}: {row.get(metric.column, '未采集')}")
    return "\n".join(lines)


def console_gpu_segment(result):
    row = result.get("last_sample", {})
    return " | ".join(f"{metric.column}: {row.get(metric.column, '未采集')}" for metric in OVERVIEW[:3])
