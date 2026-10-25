# Handoff — branch main — 2026-10-24 20:20 CDT

## What changed
Gate 0 (preflight) + Gate 1 (protected pixels) + Gate 2 (session re-ID, tested on TEST INPUT) + most of Gate 4 (voice path). One process: `CameraSource` → `Session._loop` → `VisionEngine.step` → protected MJPEG + `PairedRecorder`. Voice: mic → Muse realtime STT → `local_rules` → Muse Spark → `match_speaker` → `resolve_request` → `engine.submit()`.

## Files touched
`shared/contracts.py`; `backend/app/{main,runtime,capture,config,voice}.py`; `backend/app/vision/{detector,engine,renderer}.py`; `backend/app/consent/{registry,policy,speaker}.py`; `backend/app/providers/{local_rules,meta_intent,meta_voice}.py`; `backend/app/media/recorders.py`; `frontend/index.html`; `tests/unit/*`; `scripts/*`.

## Exact commands/tests and actual outcomes
- `.venv/bin/python -m pytest` → **68 passed** (policy, rules, LLM-output validation, engine privacy incl. re-entry 0 leak frames, fail-closed, recorder playable, health has no secrets).
- E2E on TEST INPUT via the real server: see `evaluation/results.md` (0/117 leak frames, 14 fps).
- Meta Muse STT (file + realtime WS) and Muse Spark structured output: real 200 responses.

## Contract/API shape changes
New: `shared/contracts.py` per docs/04 (+ `Privacy`, `IdentityStatus`, `OutputState`, `RequestOrigin`, `RequestAction` enums, `ConsentInterpretation.source`). Routes as docs/04 plus `/api/voice/start|stop` and env-gated `/api/dev/protect/{person_id}`.

## Known bugs / limits (do not overclaim)
- Verified on owner's live recordings: hands-over-eyes blur (3/3 correct person), real peace-sign release (1/1), new person entering gets a new ID, 2 IDs for 2 people. **Not yet verified:** eyes-closed 2 s on camera, two-person lip-motion attribution with real speech (thresholds uncalibrated).
- Gemini key rejected (401) → `INTENT_PROVIDER=gemini` falls back to Muse Spark and says so in the UI.
- Lip-motion thresholds (`MIN_ACTIVITY=0.012`, ratio 2.0) are uncalibrated guesses.
- A protected face the detector misses for > 1.2 s (profile, occlusion without hands) is not shielded.
- A returning protected person whose SFace score stays in the ambiguous band stays "identifying…" and shielded; if it falls below 0.22 for 8 good frames they'd be treated as new and visible.
- Future-frames-only: footage before a refusal stays unblurred.
- objc warning: cv2 and PyAV both bundle libavdevice; no crash observed.

## Provider access checked
Meta Model API key: yes, works (STT + Spark). Gemini key: present but invalid. No values recorded.

## Next smallest runnable task
1. Grant Camera/Mic → run the live two-person protocol below; record n/N in `evaluation/trials.csv`.
2. Gate 3: lip-motion speaker scorer in `backend/app/vision/` feeding `match_speaker`.
3. Optional: eye-cover gesture (`hand_landmarker.task` already downloaded).

## Live test protocol (two people)
1. Start session; both face camera; confirm two `person_` IDs, both visible.
2. Only A in frame, A says "please blur me" → A blurred (`PRIVACY_ACTIVATED [VOICE]`).
3. B joins → B visible, A blurred. A leaves 5 s, returns on the other side → shielded throughout, `PERSON_MATCHED protected:true`.
4. Stop recording; open the protected MP4 and confirm blur in the file.
