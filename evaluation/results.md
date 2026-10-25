# Measured results (honest, small n)

## 2026-10-24 — TEST INPUT replay (not live camera)

Input: `scripts/make_test_video.py` built from OpenCV sample images (two faces; A leaves at 5 s, returns elsewhere at 8 s). Replayed at 15 fps through the real server, real YuNet + SFace. n = 1 run, 184 recorded frames.

| Metric | Result |
| --- | --- |
| Processed FPS | 14.0 (source paced at 15) |
| Vision time per frame | p50 16.0 ms, p95 28.6 ms (M4) |
| A frames after protection in saved protected file | 117 |
| A frames left unblurred after protection (mean abs diff < 8 vs diagnostic original) | **0 / 117** (incl. re-entry) |
| A re-identified after exit | yes, `PERSON_MATCHED` score 0.927, still protected |
| B region change in protected file | mean diff 0.33 (unaffected) |
| A frames before refusal | 22 visible — expected: future-frames-only |
| Recording playable | yes, 184 frames decoded, H.264 MP4 |

## Voice decision path (real Meta calls, simulated visibility)

| Utterance | Interpreter | Result | Decide time |
| --- | --- | --- | --- |
| "Please blur me" | local_rules | DENY/SELF → PROTECT (single candidate) | 0 ms |
| "I'd rather not be in the clip." | muse-spark-1.3 | DENY/SELF → PROTECT | 3.9 s |
| "My friend says she's okay with filming." | muse-spark-1.3 | NO_REQUEST/OTHER → no-op | 6.8 s |
| Realtime STT (TTS audio streamed) | muse-voice-transcribe-1.0 WS | 2 turns, final ≈1.9 s after speech end | — |

**Not yet measured:** live webcam with real people, lighting/profile faces, two-person speaker attribution, live mic latency.
