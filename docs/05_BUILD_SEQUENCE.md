# 05 — Vertical-slice build plan and stop/go gates

Time is short. The goal is an **honest executable** demo, not a doc-perfect but nonfunctional system. “T+” below refers to start of work, not clock time; align final stage to HackTX deadline. Do research first and keep a 45+ minute submission/rehearsal buffer.

## Gate 0: preflight (20–40 min cap)

- Verify Python/OpenCV/MediaPipe/native ARM dependencies, camera/mic permissions and FFmpeg. Check Meta key with simple transcript or file request; Gemini key with one schema classification. Don't burn whole day on denied access.
- Write `docs/RESEARCH_RESULTS.md`; create versioned env/lockfiles; no credentials committed.
- Ask owner blocking questions once; log defaults and real answers. Create `shared/contracts.py` and type-compatible frontend definitions.
- Pass: one test frame through detector and backend without multiple camera owners.

## Gate 1: processed pixels (target first 60–90 mins after preflight)

- Capture webcam at low resolution; return bounded latency. Detect two faces, stable separate tracks, strong padded blur manually selected **test state**.
- Prove `FramePacket -> FrameResult -> protected MJPEG` and start/stop **actual protected video** with no image-identity leaks via overlay-only approach.
- Pass: saved protected artifact actually differs from raw source at expected face pixels.

## Gate 2: identity registry and re-entry (core innovation)

- Build only SFace-on-clear-frames gallery and match test subjects on re-entry. New track pending -> shield -> matched protected or confirmed new. Do not create long-lived cloud DB.
- Pass: subject A denied via development-injected event, leaves 3–5s, returns on other side, remains blurred before confirmation/output. Subject B unaffected. At least 5 local repeats; record failures.
- If unstable, report it as unsupported and protect output conservatively. Do NOT secretly manual-assign a restored ID.

## Gate 3: speaker association (core research risk)

- Build Face Landmarker lip openness time series per tracked face; calibrate noise baseline and speech timestamps. Single speech source + two faces; compare relative mouth motion.
- Pass: non-overlapping A speaks/B silent, then reverse, correct candidate on repeated trials; `UNKNOWN` when both speaking/offscreen/occluded.
- If heuristic poor, use deterministic single-visible-speaker assumption **labeled** or a visible manual confirmation for ambiguous cases. Consider TalkNet only if a pretrained model runs reliably in a <30 min feasibility spike.

## Gate 4: live STT + structured LLM

- Muse real-time microphone audio -> final turns with timing; Gemini structured classify; schema validation; policy queue. `DENY + SELF + MATCHED` protects correct ID. No LLM side effects.
- Pass: “please blur me” by participant A with B visible -> A blurred in saved video; “she said you can film” does not unblur; offscreen “blur me” unresolved. External key outage leaves camera/gesture path working and visibly marks voice unavailable.
- If Meta unavailable, never claim Meta integration; provide runnable labeled alternate.

## Gate 5: extra UX, camera gesture, performance

- Optional deliberate eye-cover gesture + person association. Improve preview/timeline, saved video verification, optional Meta Muse Spark comparison. Introduce real audio only after privacy decision for it is explicitly defined. Avoid AWS hot-loop, SAM, hardware SDK, custom model training.
- Measure p50/p95 frame latency and STT-to-apply delay, steady FPS, wrong-ID rate, false protection, frames leaked for denied IDs. Save `evaluation/results.md`.

## Gate 6: feature freeze / judge rehearsal / submit

- Reproduce one full live demo without manual hidden clicks, plus a visibly disclosed fallback video. Test two volunteers, two protected/unprotected outputs, docs on machine. Finish Devpost by current confirmed deadline. Provide exact limitations and any unverified features.

## Prioritization if time collapses

1. Actual face-specific processed recorder and stable IDs.
2. Local matching when one speaker/candidate; honest fallback.
3. Real speech API integration and controlled semantic classification.
4. Re-entry proof without unblurred leak in controlled trials.
5. UI polish and optional gesture.

Do not spend the hackathon training SOTA active speaker models, building serverless AWS architecture, or porting to native glasses while the core demo is broken. Test performance on available M3/M4 device, don't assume GPU accelerator.

## Go / no-go decisions

- If the identity tracker swaps people repeatedly, lock the demo to one or two stationary volunteers and name the limit. Do not claim arbitrary crowds.
- If speaker matcher cannot decide, NEVER randomly blur/unblur. Show `UNRESOLVED`, shield/pause viewer output, and have a conservative manual *development* fallback visible.
- If video cannot be recorded with protected pixels, stop feature additions: a visual overlay is not the product.
- If voice API inaccessible, test alternative but change pitch to local intent/gesture demo with documented unfulfilled sponsor integration.
