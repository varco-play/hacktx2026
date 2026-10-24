# 02 — Mandatory preflight / official-document research

**STOP:** The agent must not assume that library/model/API semantics in its training data are current. Do this research *before writing integration code*. Prefer documentation already linked below; open official API schema pages; fetch versions + deprecations; test a minimal API request. Record date, version, sample response, endpoint, limitation, and URL in `docs/RESEARCH_RESULTS.md`. If browsing unavailable, mark unverified and implement behind a driver interface; do not invent response fields.

## Preflight table

| Item | Verify | Pass / fallback |
| --- | --- | --- |
| Hardware | macOS versions, `uname -m`, available memory, camera/mic permissions, Python 3.11, Node LTS, ffmpeg | Mac M3/M4 native arm64; fallback to one machine; no ROCm/CUDA required |
| OpenCV | installed `cv2` exposes `FaceDetectorYN`, `FaceRecognizerSF`; fetch YuNet + SFace ONNX and check file size/licensing | Use local tested model; avoid competing `opencv-python` and `opencv-contrib-python` wheels |
| MediaPipe | Face Landmarker **Python** multi-face and VIDEO/LIVE_STREAM tasks, model asset access, blendshape output and timestamps | If integration too slow, use geometric lip height from simple landmark pipeline |
| Meta STT | Key access; Voice realtime **WebSocket handshake** authentication; required audio encoding, timestamps, events, endpointing vs diarization | local fixed-phrase test input (labeled) or independently named STT fallback |
| Gemini | available model and structured JSON API syntax via official SDK; billed quota, key accessibility | deterministic phrase classifier with no false attribution |
| Meta Model API | optional Muse Spark intent model for sponsor; exact ID as listed and key entitlement | if unavailable, use Gemini, disclose unavailable Muse |
| TalkNet | pretrained checkpoint availability, dependencies, macOS/MPS feasibility, runtime, license | **experiment only**, do not block MVP on it |
| PyAV/FFmpeg | arm64 wheel, encoder codec, PTS/time base, paired writer flush, audio not saved by default | write validated MP4/MKV/WebM format available on host |
| Biometric rules | whether face embeddings may be processed/stored, participant consent, local retention | 2 consenting volunteers, local/ephemeral session, no cloud face collection |
| Meta glasses | public DAT is app-level iOS/Android; exact wearable hardware access and output restrictions | webcam adapter, no native firmware claims |
| HackTX rules | actual submission deadline, track and API requirements, demo constraints on Devpost/Discord | use slides until confirmed; update when found |

## Official references verified October 24, 2026 (recheck before implementation)

- OpenCV DNN face detection/recognition YuNet/SFace tutorial: https://docs.opencv.org/4.11.0/d0/dd4/tutorial_dnn_face.html — `FaceDetectorYN` + `FaceRecognizerSF` & model downloads; dataset thresholds are **not** calibrated to this demo.
- MediaPipe Face Landmarker Python: https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/python — landmarks, blendshapes, VIDEO/LIVE_STREAM.
- Meta Model API overview: https://dev.meta.ai/docs/overview — `muse-spark-1.3` currently documented, with `MODEL_API_KEY`; subject to account entitlement.
- Meta Muse Voice Transcribe: https://dev.meta.ai/docs/speech-to-text — model `muse-voice-transcribe-1.0`, realtime `wss://api.meta.ai/v1/asr/realtime` and file `POST /v1/asr/transcribe`; **realtime handshake frame** needs auth, not just HTTP Authorization header. Includes speaker diarization/audio turn labels **not** visual identity.
- Meta structured output: https://dev.meta.ai/docs/structured-output — JSON schema, exact API surface matters.
- Google Gemini structured output: https://ai.google.dev/gemini-api/docs/structured-output — query model list https://ai.google.dev/gemini-api/docs/models; use supported JSON schema form for selected SDK/version, do not paste obsolete API snippets.
- AWS Rekognition collections: https://docs.aws.amazon.com/rekognition/latest/dg/collections-search-faces.html — `IndexFaces`, `SearchFacesByImage`, optional only. No live frame-by-frame dependence.
- Meta Wearables DAT: https://developers.meta.com/wearables/device-access-toolkit/ and https://developers.meta.com/wearables/faq/ — native iOS/Android adapter only if hardware available; **no evidence public API enforces against all native recordings**.
- TalkNet ASD: https://github.com/TaoRuijie/TalkNet-ASD — examine compatibility/license/checkpoints before considering. Mouth movement proxy and TalkNet must be clearly distinguished.
- PyAV timing: https://pyav.org/docs/stable/api/time.html — PTS/time bases for encoding.
- MLH / HackTX: https://hacktx26.devpost.com/ and https://hacktx.com/; verify live schedule and constraints.

## Inspect prior work (not a new authority)

If present in working context, read `ConsentLens-Team-Plan.md` (gesture-first) and `ConsentLens_v2_Architecture_and_Critique.md` (voice-first); use them for requirements history only. Owner's latest voice-first brief wins over earlier conflicting plans.

## Research output template

Create `docs/RESEARCH_RESULTS.md` with:

| Topic | Verified YYYY-MM-DD | Official source | Exact API/version | Smoke-test outcome | Uncertainty |
| --- | --- | --- | --- | --- | --- |

Record actual package versions (`pip freeze`, `node --version`), model hashes/URLs/licenses, selected media codecs, camera backend and proven executable command. **Never record tokens or raw personal data.**
