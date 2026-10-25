# Architecture, Meta glasses path, and critique

Written 2026-10-25 after the live two-person tests. Numbers are measured unless marked otherwise.

## 1. The idea in one line

Camera glasses record everyone, but only the wearer chooses. ConsentLens gives the **bystander** a control: say "blur me", close your eyes for 2 s, or cover your eyes, and your face is blurred in the real saved video. You stay blurred when you leave and come back, and only **you** can undo it (peace sign or "unblur me").

## 2. Repository map

```text
shared/contracts.py            one set of types: FramePacket, SpeechTurn, PrivacyRequest, FrameResult, enums
backend/app/
  main.py                      FastAPI: session, recording, voice, protected MJPEG, events WS (CSRF header guard)
  runtime.py                   Session: latest-frame loop -> engine -> preview + recorder; metrics
  capture.py                   CameraSource interface + adapters (USB phone / built-in by device ID,
                               video file, companion-app stream) + CaptureWorker (drop-stale, reconnect)
  profiles.py                  ECO / BALANCED / QUALITY + macOS thermal governor
  config.py                    .env settings; secrets never returned
  voice.py                     mic -> Muse STT -> rules / LLM -> speaker binding -> policy -> engine queue
  vision/
    detector.py                YuNet face boxes + SFace 128-d features (local)
    landmarks.py               MediaPipe face (lips, eye blink) + hand landmarks; peace-sign geometry
    engine.py                  tracks, session identity, gestures, privacy registry writes, pixel decision
    renderer.py                pixelate + blur on a COPY; full-frame slate on error
  consent/
    registry.py                per-session people + privacy state (only engine writes)
    policy.py                  deterministic: interpretation + speaker evidence -> PROTECT / UNPROTECT / UNRESOLVED
    speaker.py                 who spoke: single visible person or lip-motion heuristic, else no target
  providers/
    meta_voice.py              Meta Muse Voice Transcribe realtime WebSocket
    local_rules.py             instant fixed phrases ("blur me", "unblur me", negations, hearsay deferral)
    meta_intent.py             Meta Muse Spark JSON intent (fallback / primary when Gemini unavailable)
    gemini_intent.py           Google Gemini JSON intent (primary when key + model valid)
  media/recorders.py           PyAV H.264 live writer (protected; diagnostic original only if enabled)
frontend/index.html            dashboard: source picker, protected feed, consent states, gesture meters,
                               voice log, timeline, diagnostics (measured or "unavailable")
ios/ConsentLensCompanion/      iOS companion on Meta DAT 1.0.1 (written, not compiled — see META_SDK_INTEGRATION.md)
tests/unit/                    94 tests: policy, rules, engine privacy, gestures, voice timing, recorder, API
scripts/                       run.sh (--dev / --lan), fetch_models.sh, benchmark.py, companion_sim.py,
                               make_test_video.py
backend/app/media/storage.py   Cloudflare R2 upload (protected/ presigned; raw restricted/, off by default)
docs/                          architecture, contracts, privacy, research results; evaluation/results.md = measurements
```

## 3. Tools

| Layer | Tool | Why |
| --- | --- | --- |
| Capture | OpenCV AVFoundation | one owner of the Mac webcam (glasses stand-in) |
| Face detection | OpenCV YuNet (ONNX, 230 KB) | 3–6 ms/frame on M4, landmarks for quality gate |
| Session re-ID | OpenCV SFace (128-d) | 4–8 ms; same person 0.84–1.0 vs others ≤0.3 on our footage |
| Lips / eyes / hands / head | MediaPipe Face (+blendshapes), Hand, Pose-lite landmarkers | face every frame; hands and pose alternate frames; whole engine ~26 ms p50 on M4 |
| Speech to text | Meta Muse Voice Transcribe realtime WS | partial + final turns with timing |
| Intent | local regex rules → Gemini (if key) → Muse Spark | rules 0 ms; Spark 1–2.4 s; strict local validation |
| Recording | PyAV / libx264, ms timestamps | blur is in the saved pixels, VFR-safe at 30 fps |
| API / UI | FastAPI, MJPEG, WebSocket, plain HTML | protected stream only; no original route |
| Tests | pytest, replay of real footage, live Muse latency harness | |

## 4. Pipeline (one frame, one sentence)

```text
Camera 30 fps ──► FramePacket (immutable, monotonic t_ms)
                     │
                     ▼  VisionEngine.step  (single thread, ~18–21 ms p50 with landmarks)
   apply queued requests (voice / dev)            ◄──── PrivacyRequest queue ◄──┐
   YuNet faces ─► associate to tracks (IoU/center)                              │
   pending track? SFace on GOOD frames only ─► match known (≥0.40, margin)      │
                                            └► new person (8 good frames <0.22) │
   MediaPipe: lips per person ─► visibility+lip history (60 s)                  │
              eyes closed 2 s / hands over eyes 1.5 s ─► PROTECT (gesture)      │
              peace sign 1 s, hand clearly nearest own face ─► UNPROTECT        │
   decide pixels: protected ─► blur; unknown face while a protected person is   │
                  missing ─► blur until identified; error ─► full slate         │
                     │                                                          │
                     ▼                                                          │
   protected frame ─► H.264 recorder + MJPEG preview (+ optional local original)│
                                                                                │
Mic 24 kHz ─► Muse realtime STT ─► partial: rules DENY? act now (~0.6 s)        │
                                └► final: rules / Gemini / Spark (JSON, validated)
                                   ─► speaker binding (lips in the turn window) │
                                   ─► policy: DENY+SELF+MATCHED=PROTECT,        │
                                      ALLOW+SELF+MATCHED=UNPROTECT, else none ──┘
```

State per person: `VISIBLE_NO_REQUEST` (not consent) → `BLURRED_BY_REQUEST` → `VISIBLE_BY_CONSENT` (only by the same person), session-scoped. Embeddings are deleted at session end.

## 4b. Interfaces and module ownership (for parallel work)

| Module | Interface (stable) | Can be owned separately |
| --- | --- | --- |
| Sources / SDK adapters | `CameraSource` (`initialize/start/read/stop/cleanup/capabilities/status`), ingest wire format | yes — new adapters never touch the engine |
| Vision | `VisionEngine.step(FramePacket) -> FrameResult`, `submit(PrivacyRequest)` | yes |
| Audio + STT | `SpeechTurn`, mic loudness envelope `[(t_ms, rms)]` | yes |
| Speaker matching | `match_speaker(turn, visibility_history, audio_env) -> SpeakerMatch` | yes |
| Consent policy | `resolve_request(...) -> PrivacyRequest`, registry states | yes (small, deterministic) |
| Recording / storage | `PairedRecorder.write(source, protected, t_ms)`, `R2Storage` | yes |
| Frontend | `/api/state`, `/api/events` JSON, `/api/preview/protected` | yes |

All timestamps are the server's monotonic session clock (`Session.now_ms`), stamped when a frame or audio chunk arrives.

## 5. Path to real Meta glasses

What exists publicly (checked 2026-10-25): the **Wearables Device Access Toolkit 1.0** lets an iOS/Android app use the glasses' camera video stream, microphone/audio, and display (display glasses); apps run on the **phone**, paired through the Meta AI app. Nothing documented lets a third-party app intercept or modify the glasses' **native** recordings.

| Stage | What we would build | What it protects | Honest limit |
| --- | --- | --- | --- |
| A. Third-party app (buildable now) | Port the engine to iOS/Android: YuNet/SFace via ONNX Runtime or Core ML, MediaPipe mobile tasks, Muse STT from the phone. Stream from glasses via DAT, write protected clips in our app. | Footage captured **through our app** | Native capture button bypasses it; phone battery/thermal |
| B. Meta AI app import step (first-party) | Run ConsentLens when clips sync from glasses to the phone, **before** gallery/share. Whole clip is available, so a refusal at 0:20 can blur the person from 0:00 (fixes our biggest gap). | All native recordings once imported | Needs Meta; originals still exist on the glasses until import |
| C. On-glasses capture (first-party firmware) | Detector + gesture/keyword spotting on the glasses NPU; protected encode at capture; original encrypted with a key the wearer doesn't hold. | Every frame at source | Compute/battery budget; policy & legal review |
| D. Bystander signal (new idea) | A phone app or wearable broadcasts a short-lived "don't record me" BLE token; glasses that see it shield all unknown faces nearby until the person is identified by gesture/voice. | People who can't speak/gesture in time | Needs ecosystem adoption |

Glasses-specific details that matter: the privacy LED should change pattern when someone is blurred (feedback to the bystander); glasses open-ear speakers can say "You're blurred" quietly; the glasses' multi-microphone array can give direction-of-arrival, a far stronger "who spoke" signal than lips alone.

## 6. Critique — weaknesses, ranked by privacy harm

1. **Footage before the request stays visible.** We blur only from the moment someone asks. Fix: a 3–5 s delayed write buffer that back-applies blur to the requester's earlier frames; on glasses, stage B processes the whole clip.
2. **Peace sign is the most common photo pose.** A blurred person posing for a selfie can unblur themselves by accident. Fix: hold 2 s **plus** a confirmation (chime + "say yes" or a second gesture), and show a 3-2-1 countdown.
3. **Face-only blur.** Clothes, body, tattoos, voice and context still identify. Fix: MediaPipe person segmentation for optional body blur; mute/pitch-shift the requester's voice in saved audio (we save video only today).
4. ~~**Detector misses = possible exposure.**~~ *Implemented 2026-10-25:* lost faces follow the MediaPipe pose head (guarded so a track can't jump to a visible friend's head). Remaining: Profile views or occlusion longer than 1.2 s drop the face box. Fix: head/body tracking (pose landmarker) so a protected person's region stays shielded even without a frontal face; measure leak frames per trial.
5. **Who-spoke is a heuristic.** *Improved 2026-10-25:* audio-visual sync (lip opening vs mic loudness, ±200 ms lag search) with a per-person self-calibrating noise floor. Remaining: Lip motion fires on laughing/eating; an off-camera speaker plus a talking visible person can mis-bind. Fix: correlate the audio energy envelope with each face's lip opening (cheap, much stronger), then mic-array direction on glasses. Thresholds still need calibration on real speech.
6. ~~**We compute embeddings for everyone**~~ *Implemented 2026-10-25:* features are stored only for people who asked for blur, deleted on consent/departure. Original note:, including people who never asked. Biometric laws (e.g., Texas CUBI, Illinois BIPA) care about this. Fix ("privacy-minimal re-ID"): keep galleries only for people who requested blur; everyone else is track-only, and their features are discarded after the comparison.
7. ~~**The bystander gets no confirmation.**~~ *Implemented 2026-10-25:* chime, spoken line, badge, and preview-only "blurred ✓ / checking…" labels. Original note: They don't know it worked. Fix: audible chime/TTS and an on-screen badge now; LED pattern on glasses.
8. **Cloud audio.** Every word near the wearer goes to the STT provider. Fix: on-device keyword spotting for the fixed phrases (instant, offline); cloud only for complex sentences, with consent.
9. **Wearer can still read the original** when the diagnostic file is enabled. Fix: don't write it in production, or encrypt it with an escrow key the wearer can't use.
10. **Scale and session limits.** Tuned for 2–4 people; a restart forgets refusals by design. Fix: crowd mode (shield all unknowns), clear disclosure of reset behavior.

Fixed during this session (found in real footage or code review): duplicate IDs (4→2), 30 fps recorder crash, false peace sign on fingers touching a face, "don't blur me" misread as "blur me", voice turns blocking each other, stale audio and clock drift after a Muse reconnect, any website being able to start the camera via localhost POST (CSRF), unbounded event log, and an intermittent MediaPipe stall that froze a replay (landmarks now run on a watchdog thread with a 120 ms budget and auto-restart).

## 7. Best next improvements (by value per hour)

1. Bystander feedback chime + badge (small; big UX win for judges).
2. Peace-sign confirmation step (small; closes weakness 2).
3. Audio-visual sync for speaker binding (medium; closes most of 5).
4. Privacy-minimal embeddings (medium; strong pitch point).
5. Delayed-buffer retroactive blur (larger; closes weakness 1 — the best demo moment).
