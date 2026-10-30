"""FPS from the selected application's SurfaceFlinger actual-present timestamps.

This is an Android display measurement, separate from unmodified sdpcli counters.
"""

import csv
from datetime import datetime, timezone
from pathlib import Path
import re
import shlex
import time

SOURCE = "SurfaceFlinger actualPresentTime"
FPS_FIELDS = ("Elapsed (s)", "FPS", "Source", "Layer", "Status", "Presented frames",
              "First actualPresentTime (ns)", "Last actualPresentTime (ns)")
FRAME_FIELDS = ("Observed UTC", "Layer", "desiredPresentTime (ns)",
                "actualPresentTime (ns)", "frameReadyTime (ns)")
PENDING = 2**63 - 1


def parse_latency(text):
    frames = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 3:
            continue
        try:
            desired, actual, ready = map(int, parts)
        except ValueError:
            continue
        if 0 < actual < PENDING:
            frames[actual] = (desired, actual, ready)
    return [frames[key] for key in sorted(frames)]


def candidate_layers(text, package):
    if not package:
        return []
    pattern = re.compile(re.escape(package) + r"(?=[/\]\s]|$)")
    layers = [line for line in text.splitlines() if pattern.search(line)
              and not any(name in line for name in ("Background for", "ActivityRecord", "Bounds for",
                                                    "InputSink", "Splash Screen", "Snapshot"))]
    return sorted(layers, key=lambda layer: ("SurfaceView" in layer, "BLAST" in layer), reverse=True)


class FpsReader:
    def __init__(self, adb, package, clock=time.monotonic):
        self.adb, self.package, self.clock = adb, package, clock
        self.layer = None
        self.last_present = None
        self.last_discovery = -float("inf")
        self.last_new_frame = None

    def read(self):
        now = self.clock()
        discover = self.layer is None or (self.last_new_frame is not None and
                                          now - self.last_new_frame > 2 and
                                          now - self.last_discovery > 3)
        layers = [self.layer] if self.layer else []
        if discover:
            listing = self.adb.shell("dumpsys SurfaceFlinger --list", timeout=4)
            self.last_discovery = now
            if not listing.ok:
                return self._unavailable("layer_list_unavailable")
            layers = candidate_layers(listing.stdout, self.package)
            if not layers:
                self.layer, self.last_present = None, None
                return self._unavailable("target_layer_unavailable")
        for layer in layers[:3]:
            result = self.adb.shell("dumpsys SurfaceFlinger --latency " + shlex.quote(layer), timeout=4)
            if not result.ok:
                continue
            frames = parse_latency(result.stdout)
            if not frames:
                continue
            if layer != self.layer:
                self.layer, self.last_present = layer, None
            observed = self.clock()
            last = frames[-1][1]
            if self.last_present is None or last < self.last_present:
                self.last_present, self.last_new_frame = last, observed
                return {"fps": None, "source": SOURCE, "layer": layer, "status": "warming_up",
                        "frame_count": 0, "first_present_ns": last, "last_present_ns": last,
                        "frames": []}
            new_frames = [frame for frame in frames if frame[1] > self.last_present]
            if not new_frames:
                return {"fps": 0.0, "source": SOURCE, "layer": layer, "status": "no_new_frames",
                        "frame_count": 0, "first_present_ns": self.last_present,
                        "last_present_ns": self.last_present, "frames": []}
            first, count = self.last_present, len(new_frames)
            status = "ok"
            if frames[0][1] > self.last_present:
                # The 128-entry buffer rolled past our baseline. Use only the
                # intervals actually present in the returned window.
                first, count, status = frames[0][1], len(frames) - 1, "buffer_window"
            delta = last - first
            fps = count * 1e9 / delta if delta > 0 and count > 0 else None
            self.last_present, self.last_new_frame = last, observed
            return {"fps": fps, "source": SOURCE, "layer": layer,
                    "status": status if fps is not None else "warming_up",
                    "frame_count": count, "first_present_ns": first, "last_present_ns": last,
                    "frames": new_frames}
        self.layer, self.last_present = None, None
        return self._unavailable("frame_timestamps_unavailable")

    def _unavailable(self, status):
        return {"fps": None, "source": SOURCE, "layer": self.layer or "", "status": status,
                "frame_count": 0, "first_present_ns": None, "last_present_ns": None, "frames": []}


class FpsRecorder:
    """Persist FPS observations without adding columns to the sdpcli CSV."""

    def __init__(self, output_dir, start_time):
        self.folder, self.start_time = Path(output_dir) / "raw", start_time

    def append(self, sample, elapsed=None):
        self.folder.mkdir(parents=True, exist_ok=True)
        elapsed = max(0, time.time() - self.start_time) if elapsed is None else elapsed
        observation = {"Elapsed (s)": f"{elapsed:.6f}",
                       "FPS": "" if sample["fps"] is None else repr(sample["fps"]),
                       "Source": sample["source"], "Layer": sample["layer"],
                       "Status": sample["status"], "Presented frames": sample["frame_count"],
                       "First actualPresentTime (ns)": sample["first_present_ns"],
                       "Last actualPresentTime (ns)": sample["last_present_ns"]}
        self._append(self.folder / "fps.csv", FPS_FIELDS, [observation])
        stamp = datetime.now(timezone.utc).isoformat()
        frames = [{"Observed UTC": stamp, "Layer": sample["layer"],
                   "desiredPresentTime (ns)": frame[0], "actualPresentTime (ns)": frame[1],
                   "frameReadyTime (ns)": frame[2]} for frame in sample.get("frames", [])]
        if frames:
            self._append(self.folder / "surfaceflinger_frames.csv", FRAME_FIELDS, frames)
        return observation

    @staticmethod
    def _append(path, fields, rows):
        new = not path.exists() or not path.stat().st_size
        with path.open("a", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            if new:
                writer.writeheader()
            writer.writerows(rows)


def load_fps_samples(path):
    path = Path(path)
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))
