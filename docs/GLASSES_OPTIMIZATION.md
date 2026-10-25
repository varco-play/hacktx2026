# Keeping the glasses light

**Principle:** the glasses capture and stream; everything heavy runs on the phone (target) or the Mac (hackathon stand-in). Moving compute off the glasses does **not** make streaming free — camera, encoder and radio still cost power — so we also minimise how much we stream.

## What is implemented

| Technique | Where | Status |
| --- | --- | --- |
| Glasses stream at the SDK sample's known-valid profile (`.low`, 24 fps, HEVC); no higher rates requested | `ios/.../GlassesSession.swift` | written, not compiled |
| Phone forwards ≤12 fps, **one frame in flight**, skipped frames never decoded | `ios/.../FrameUplink.swift`, `GlassesSession.onFrame` | written, not compiled; wire format tested in Python |
| Latest-frame handoff: stale frames dropped (counted), never queued | `backend/app/capture.py` `CaptureWorker`, `CompanionStreamSource` | implemented + tested |
| Quality profiles ECO / BALANCED / QUALITY (processing fps, landmark cadence, preview JPEG quality) | `backend/app/profiles.py` | implemented + benchmarked |
| Thermal governor: macOS `thermalState` serious/critical → ECO; restore after 60 s cool | `ThermalGovernor` | implemented + unit-tested (no real throttle event observed yet) |
| Cheap work every frame, expensive work only when needed: no face features for visible people; SFace only while a protected person is missing; hands and pose on alternate frames | `vision/engine.py`, `vision/landmarks.py` | implemented + tested |
| Landmark watchdog (120 ms budget, auto-restart) so a stall can't freeze capture | `Signals` | implemented + tested |
| Glasses battery/thermal | — | **unavailable** in DAT 1.0.1 sample APIs; phone metrics reported instead, labeled |

## Measured (MacBook Air M4, 640×480, two real faces, `scripts/benchmark.py`, 8 s per profile, 2026-10-25)

| profile | target fps | achieved fps | engine p50 ms | engine p95 ms | CPU % (1 core = 100) | RSS MB |
| --- | --- | --- | --- | --- | --- | --- |
| ECO | 10 | 9.5 | 27.9 | 43.8 | 44.3 | 467 |
| BALANCED | 15 | 14.0 | 27.4 | 31.5 | 61.0 | 474 |
| QUALITY | 30 | 27.5 | 25.7 | 26.6 | 105.3 | 448 |

Host thermal state stayed `nominal` before and after. Per-frame cost is ~26–28 ms regardless of profile, so **frame rate is the main heat lever**: ECO uses ~2.4× less CPU than QUALITY. Live server run (BALANCED, test clip): 14.2 fps in/out, 0 stale drops, capture→preview p50 22–24 ms.

These numbers describe the Mac only. They are **not** evidence of phone or glasses performance.

## Not done / next

- Measure on a real phone (ONNX Runtime Mobile / Core ML) and with real glasses streaming.
- Pause streaming when no faces are present for N seconds (largest possible saving; needs SDK stream stop/start cost measured first).
- Detector every Nth frame with tracker-only frames in between (today YuNet runs every processed frame; it is the cheapest model, ~5 ms).
