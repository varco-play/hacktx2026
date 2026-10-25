"""Repeatable local benchmark: replay a clip through the real engine per quality profile.

  .venv/bin/python scripts/benchmark.py clip.mp4 --seconds 10 [--profiles ECO BALANCED QUALITY]

Reports processed FPS, engine latency p50/p95, CPU% and RSS for each profile, plus the
number of faces seen. Frames are fed as fast as the profile allows (no camera), so this
measures processing cost on THIS machine only — it says nothing about phone or glasses
performance. Run with `nice -n 19` to keep the laptop cool.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import av  # noqa: E402
import psutil  # noqa: E402

from backend.app.profiles import PROFILES, mac_thermal_state  # noqa: E402
from backend.app.vision.detector import FaceModels  # noqa: E402
from backend.app.vision.engine import VisionEngine  # noqa: E402
from backend.app.vision.landmarks import Signals  # noqa: E402
from shared.contracts import FramePacket  # noqa: E402


def frames(path):
    while True:
        with av.open(path) as c:
            for fr in c.decode(video=0):
                img = fr.to_ndarray(format="bgr24")
                if img.shape[1] != 640:
                    import cv2
                    img = cv2.resize(img, (640, 480))
                yield img


def run(path, profile, seconds, models):
    prof = PROFILES[profile]
    eng = VisionEngine("bench", models.detect, models.feature, signals=Signals("models"))
    proc = psutil.Process()
    proc.cpu_percent(None)
    lat, faces, t0, n = [], 0, time.monotonic(), 0
    interval = 1.0 / prof["process_fps"]
    a_int, next_a = 1.0 / prof["analyze_hz"], 0.0
    for img in frames(path):
        start = time.monotonic()
        if start - t0 > seconds:
            break
        n += 1
        analyze = start >= next_a - 0.25 * a_int
        if analyze:
            next_a = max(next_a + a_int, start)
        r = eng.step(FramePacket("bench", n, int((start - t0) * 1000), img), analyze=analyze)
        lat.append((time.monotonic() - start) * 1000)
        faces = max(faces, len([t for t in r.tracks if not t["coasting"]]))
        spare = interval - (time.monotonic() - start)
        if spare > 0:
            time.sleep(spare)  # pace like the live loop at the profile's rate
    lat.sort()
    el = time.monotonic() - t0
    return {"profile": profile, "target_fps": f'{prof["process_fps"]} (analysis {prof["analyze_hz"]} Hz)', "fps": round(n / el, 1),
            "engine_ms_p50": round(lat[len(lat) // 2], 1), "engine_ms_p95": round(lat[int(.95 * len(lat))], 1),
            "cpu_percent": round(proc.cpu_percent(None), 1), "rss_mb": round(proc.memory_info().rss / 2**20),
            "max_faces": faces, "frames": n}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("clip")
    ap.add_argument("--seconds", type=float, default=10)
    ap.add_argument("--profiles", nargs="+", default=["ECO", "BALANCED", "QUALITY"])
    a = ap.parse_args()
    models = FaceModels("models")
    print(f"host thermal before: {mac_thermal_state()}")
    print("| profile | target fps | achieved fps | engine p50 ms | engine p95 ms | CPU % | RSS MB | faces |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for p in a.profiles:
        r = run(a.clip, p, a.seconds, models)
        print(f"| {r['profile']} | {r['target_fps']} | {r['fps']} | {r['engine_ms_p50']} | {r['engine_ms_p95']} | "
              f"{r['cpu_percent']} | {r['rss_mb']} | {r['max_faces']} |")
    print(f"host thermal after: {mac_thermal_state()}")
