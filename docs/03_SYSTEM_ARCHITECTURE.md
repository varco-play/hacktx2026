# 03 — System architecture, components, and runtime design

## Non-negotiable design principle

A **single trusted local policy engine**, not an LLM, owns persistent person state and determines pixels written to `protected` media. The AI interpretation and visual-speaker evidence are inputs. No per-frame AWS or Gemini call. One process + one camera owner is enough. Normal path operates even during cloud API outage, though speech features may be unavailable.

## Physical deployment / API boundary

**HackTX implementation:** built-in Mac webcam + laptop microphone -> local Python service -> browser viewer. This is a simulation of a possible Meta-built wearer camera pipeline. DO NOT claim native Ray-Ban Meta video mutation. Actual DAT glasses streams require future iOS/Android mobile adapter; hardware/firmware enforcement requires Meta first-party work.

## Data flow

```text
Camera (one OpenCV capture owner) -------------- Mic (one audio owner)
  | monotonically numbered/timestamped frames     | timestamped PCM audio
  v                                               v
CaptureAdapter                                   SpeechTranscriber
  |                                               |  Muse Voice / fallback
  v                                               v
VisionEngine (single worker)                    TranscriptTurn (event ID, interval)
  |- YuNet face boxes                              |
  |- association / stable tracks                   v
  |- SFace gallery for SESSION-only re-ID       ConsentInterpreter (Gemini JSON / rules)
  |- FaceLandmarker mouth timelines                |
  |- gesture optional                              v
  |- active speaker candidate scorer <-------- VoiceRequestCandidate
  |- deterministic PrivacyPolicy <-------------- validated queued request
  |- shield pending re-ID / ambiguity
  `- blurred pixels in independent buffer
  |
  v
FrameResult(frame_id, timestamp, protected_bgr, event snapshot)
  |- protected encoder (never raw fallback)
  |- restricted diagnostic source encoder (dev/consented demo only)
  |- MJPEG preview (protected ONLY)
  `- JSON event stream (no embeddings or raw crops)

Browser React/Vite + TS <- FastAPI REST/WebSocket/event stream
```

**Clarification:** Text classification and active speaker attribution are conceptually *parallel* signals for the same utterance. Don't gate utterance alignment on how long the Gemini request takes. Use audio **capture timestamps**, not response arrival time.

## Baseline local pipeline

- Capture at 640x480 15 FPS target (not measured). Initial single inference worker, bounded 1–3 frame latest queue; timestamps monotonic.
- YuNet face detection + simple Hungarian or greedy IoU/center-distance motion association. Distinguish transient `track_id` from persistent `person_id`. Use one-to-one assignment.
- SFace `alignCrop` + `feature` for clear face samples. Keep small gallery of embeddings per `person_id`, compare after a gap; require threshold, margin over runner-up and multiple confirming frames. Dataset tutorial threshold **never** a universal guarantee. Freeze gallery during mouth/face occlusion and ID uncertainty.
- Face Landmarker for 1–3 visible face crops at measured intervals; track mouth openness metric per face (e.g., landmark lip separation normalized by interocular distance, optionally `jawOpen` blendshape). Handle crop coordinates transforms.
- Local visual active-speaker **heuristic**, not certified speaker ID: compare lip motion temporal variance/derivative within speech interval vs quiet baseline; if one face is clearly ahead by calibrated margin and speech detected, nominate it. Reject if >1 candidates, face side-on, offscreen voice, occlusion, overlap, short utterance, uncertain sync, or low margin. Use Muse diarization speaker label only to link **audio turns**, not faces. Optional TalkNet after feasibility benchmark.
- Transcribe asynchronously via Muse realtime STT; optional fallback; parse utterance start/end, partial/final IDs. Queue only final/confirmed unique turns, reject old-session responses.
- Gemini structured classifier emits `DENY`, `ALLOW`, `NO_REQUEST`, or `UNCLEAR` and `SELF` vs reference. Deterministic phrase rules can intercept explicit denials. LLM output is untrusted until Pydantic validation. Do NOT pass tools for direct write access.
- Policy engine evaluates `VoiceRequestCandidate + active speaker candidate + time sync + visibility/identity confidence`. Only reliable SELF speaker binding can target one `person_id`. For denial with uncertain speaker: emit `REQUEST_UNRESOLVED`, temporarily shield output or pause viewer feed; preserve already denied identities. Allowing/unblur is disabled by default.
- Protected renderer uses **actual image pixels**, blur/pixelation with generous face/head padding. On detector miss, propagate head estimate if credible. If known protected head is lost/uncertainty high, shield affected region or full frame. Fail closed (shield/slate) upon vision exception, never show raw to viewer/recorder.
- Source diagnostic path allowed only for volunteer demo, local files, not user-accessible endpoint by default. Video-only initial. Disk errors stop stream; don't falsely claim paired outputs.

## Long-running video correctness

Run capture on monotonic clock. Model callbacks/results must carry frame ID and source timestamp. Never apply an old detection to the latest unrelated frame. Alignment of transcript intervals to mouth observations must account for clock offsets and network delay; test with a clapper/known speaking sequence. Keep a rolling ~2–4 s local *features* window for mouth data; do not save extra raw video unless explicitly authorized.

## Two deceptively hard privacy gaps

1. **Early exposed frames:** because owner requested visible-by-default, footage preceding refusal remains exposed unless recording is delayed or pre-export backfilled. Core can honestly call itself “prospective redaction” only. Optional delay ring-buffer/retroactive editing has its own complexity; never claim whole-session post-objection anonymity without implementing/testing it.
2. **Re-entry:** first several frames of return may be recognizable before embedding match completes. Temporarily shield incoming candidates while there is a protected identity in the session and identity comparison is incomplete. If this makes default unblurred slower, accept it as documented exception to prevent leakage. No perfect guarantee with missed face detections.

## Why not cloud-first AWS

Rekognition `IndexFaces`/`SearchFacesByImage` can provide collection IDs and comparisons but adds network overhead, cost, handling/transmission of nonconsenting faces, and semantic confusion (`FaceId` ≠ voice speaker). Use local SFace gallery for live. Optional AWS comparison can be performed on consented images after MVP with explicit opt-in. A hosted database isn't required for a session prototype; SQLite only for nonbiometric event metadata, otherwise in-memory.

## Runtime / transport

Python 3.11 (ARM64) local venv; OpenCV, NumPy, MediaPipe, PyAV or ffmpeg; FastAPI + Uvicorn; React/Vite/TypeScript UI. WebSocket for consent events/metrics and MJPEG for protected frames. API keys server-side only. If MJPEG bandwidth or responsiveness poor, test alternative streaming **after baseline**, not before.

## Source tree

```text
backend/
  app/main.py app/runtime.py app/capture.py app/audio.py
  app/vision/{detector.py,landmarks.py,tracker.py,reid.py,speaker.py,renderer.py}
  app/consent/{policy.py,registry.py,events.py,interpreter.py}
  app/providers/{meta_voice.py,gemini_intent.py,local_rules.py}
  app/media/{recorders.py,artifacts.py}
  app/api/{routes.py,socket.py,models.py}
frontend/src/{App.tsx,api.ts,components/*}
shared/{contracts.py,schemas.json}
tests/{unit,integration,fixtures}
evaluation/{trials.csv,results.md}
recordings/   # ignored by git
models/       # binaries ignored by git; MANIFEST tracked
```

Do not multiply microservices, duplicate registries or alternate camera workers. Choose one clear implementation path and prove it.
