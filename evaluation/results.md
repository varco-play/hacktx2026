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

## 2026-10-24 ~20:10 — Real two-person footage (owner + friend, diagnostic original replayed as TEST INPUT)

| Check | Before fixes | After fixes |
| --- | --- | --- |
| Person IDs for 2 people (106 s clip) | **4** (dupes from a turned face at 11 s and a top-edge partial face at 73.7 s) | **2** |
| Person IDs for 1 person (131 s clip) | 1 | 1 |
| Hands-over-eyes gesture → blur | n/a | fired for the correct person both times (10.8 s, 39.6 s), verified by viewing frames |
| False peace-sign release | n/a | first detector fired on curled fingers touching a face (64.3 s); stricter geometry + "not on a face" rule → 0 false releases |
| Server replay incl. face+hand landmarks | — | 26–28 fps, vision p50 18–21 ms, p95 23–41 ms; 1195-frame 30 fps recording finalized, no error |
| Protected file after blur | — | blurred person's face pixelated in every checked frame (detector still finds a blurred blob in 95/832 frames; visually confirmed not identifiable) |

## Voice latency (live Meta Muse realtime WS, TTS audio streamed in real time)

| Phrase | Path | Command issued after end of phrase |
| --- | --- | --- |
| "Please blur me" | partial transcript + local rules | ~0.6 s |
| "Unblur me" | final transcript + local rules | ~0.7 s |
| "I would rather not be in this video" | Muse Spark (minimal, json_object) | decide 1.0 s after final (+ ~1–2 s endpointing) |
| Before fixes | serial handling, strict schema | 1.9 s endpointing + 3.5–9 s, later turns blocked |

**Not yet verified live:** peace sign by a real hand (only geometry unit tests + no-false-positive replay), eyes-closed 2 s on live camera, two-person lip-motion attribution with real speech.

## 2026-10-25 ~00:30 — Owner live recordings (27 min + 5 min), replayed

| Event (time) | What the frames show | Engine |
| --- | --- | --- |
| 13.8 s | person covers eyes with hand | PRIVACY_ACTIVATED (hands_over_eyes) ✔ |
| 34.0 s | same person holds a ✌ peace sign beside face | PRIVACY_RELEASED (peace_sign) ✔ |
| 813 s | a different person walks in | PERSON_NEW person_002 ✔ (2 IDs total for 27 min) |
| 2nd recording 16.8 s | front person covers eyes, second person behind | front person blurred only ✔ |
| 2nd recording 193 s | blurred person holds ✌ | PRIVACY_RELEASED ✔ (2 IDs total for 5 min) |

Final replay: 0 landmark timeouts / 0 restarts; offline throughput ~55–67 fps.

Voice (live Muse, final run): "please blur me" ⚡ partial path, issued ~0.5 s after speech end; "unblur me" ~0.8 s; Muse Spark phrases decided 1.3–1.5 s after the final transcript.

Robustness: one replay hung inside MediaPipe (main thread blocked in a lock; not reproducible on the same file alone). Landmarks now run on a watchdog thread (120 ms budget, restart after 2 s); unit test simulates the hang.
