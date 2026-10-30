"""Presentation-only units. Source names, cells and numeric series stay untouched."""

from cli_data import numeric

PREFIXES = ((1e12,"T"),(1e9,"G"),(1e6,"M"),(1e3,"K"))


def display_spec(column):
    lower = column.lower()
    if "bytes/sec" in lower or "bytes/second" in lower:
        return {"divisor":1e6,"unit":"MB/s","compact":False}
    if column in ("Used Memory","Available Memory","Free Memory","Total Memory"):
        return {"divisor":1e6,"unit":"MB","compact":False}
    if column.startswith("CPU ") and column.endswith("Core Frequency"):
        return {"divisor":1e6,"unit":"MHz","compact":False}
    if column == "Clocks / Second":
        return {"divisor":1e6,"unit":"M cycles/s","compact":False}
    if column == "Vertex Instructions / Second":
        return {"divisor":1e6,"unit":"M inst/s","compact":False}
    if "instructions /" in lower and ("second" in lower or "sec" in lower):
        return {"divisor":1e9,"unit":"G inst/s","compact":False}
    if column in ("Fragments Shaded / Second","Vertices Shaded / Second"):
        return {"divisor":1e6,"unit":"M/s","compact":False}
    if "%" in column or column.startswith("CPU ") and column.endswith("Core Utilization"):
        return {"divisor":1,"unit":"%","compact":False}
    if column == "FPS":
        return {"divisor":1,"unit":"FPS","compact":False}
    if column == "Temperature":
        return {"divisor":1,"unit":"°C","compact":False}
    # In particular, Avg Preemption Delay does not declare a time unit. Scale
    # its numeric magnitude without guessing ns/us/ms or changing its meaning.
    return {"divisor":1,"unit":"/s" if "/ second" in lower or "/ sec" in lower else "",
            "compact":True}


def scaled_spec(column, magnitude=0):
    spec = display_spec(column)
    if spec["compact"]:
        for divisor, prefix in PREFIXES:
            if abs(magnitude) >= divisor:
                return {"divisor":divisor,"unit":prefix+spec["unit"],"compact":False}
    return spec


def format_number(value):
    if value == 0:
        return "0"
    if abs(value) < .01:
        return format(value,".4g")
    return f"{value:.2f}".rstrip("0").rstrip(".")


def format_metric(column, raw, *, readable=True, spec=None):
    if raw is None or raw == "":
        return "—"
    value = numeric(raw)
    if not readable or value is None:
        return str(raw)
    spec = spec or scaled_spec(column, value)
    text = format_number(value/spec["divisor"])
    return text+(" "+spec["unit"] if spec["unit"] else "")
