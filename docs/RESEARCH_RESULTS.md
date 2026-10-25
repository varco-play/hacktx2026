# Research and preflight results

Verified 2026-10-24 ~18:40–19:00 CDT on MacBook Air **Apple M4, 16 GB, macOS 26.0.1, arm64**. No secrets recorded.

| Topic | Verified | Official source | Exact API / version | Smoke-test outcome | Uncertainty |
| --- | --- | --- | --- | --- | --- |
| Python | 2026-10-24 | uv-managed CPython | 3.11.17 arm64 in `.venv` (system only had 3.9.6; no Homebrew) | `.venv/bin/python` works | — |
| OpenCV | 2026-10-24 | docs.opencv.org dnn_face tutorial | `opencv-contrib-python==5.0.0.93` (single wheel; `opencv-python` removed because mediapipe pulls contrib) | `FaceDetectorYN`, `FaceRecognizerSF` present | OpenCV 5 API differences vs 4.x tutorial checked at runtime |
| MediaPipe | 2026-10-24 | developers.google.com/edge/mediapipe | `mediapipe==1.1.1`; `face_landmarker.task` float16 v1, `hand_landmarker.task` float16 v1 | import OK; 2-face test pending | — |
| PyAV | 2026-10-24 | pyav.org | `av==18.1.0` | import OK | **objc warning**: cv2 and av each bundle `libavdevice` (`AVFFrameReceiver` duplicated). Capture uses cv2 only; watch for crashes |
| Meta Muse Voice Transcribe | 2026-10-24 | dev.meta.ai/docs/speech-to-text | `POST https://api.meta.ai/v1/asr/transcribe` multipart (`request` JSON + `audio` WAV mono s16 16/24 kHz), `Authorization: Bearer`; realtime `wss://api.meta.ai/v1/asr/realtime`, auth in first JSON frame `authorization.accessToken`, PCM_24KHZ/PCM_16KHZ binary frames, events `speechStart/transcript/speechEnd/speechComplete`, end with `{"type":"endStream"}` | **200 OK, 1.65 s** for a 2.6 s TTS clip, ENDPOINTING returned `turns[{turnId,startMs,endMs,transcript}]` | Turn-level timestamps only; realtime WS not yet tested |
| Meta Muse Spark intent | 2026-10-24 | dev.meta.ai/docs/structured-output | `POST https://api.meta.ai/v1/chat/completions`, model `muse-spark-1.3`, `response_format.json_schema` strict | **200 OK**, 3.5–9.3 s; "please blur me"→DENY/SELF; "my friend says she's okay"→ALLOW/OTHER; injection→NO_REQUEST/OTHER | Latency too high for sole path → local fixed-phrase rules first |
| Gemini | 2026-10-24 | ai.google.dev | `google-genai==2.33.0` | **FAIL 401** with the provided key; adapter built, falls back to Muse Spark and says so | needs a valid AI Studio key |
| Camera | 2026-10-24 | macOS TCC | `cv2.VideoCapture(0, CAP_AVFOUNDATION)` | works when the server is started from Terminal.app (Terminal holds the permission); 30 fps measured | phone camera not yet connected during dev |
| FFmpeg CLI | 2026-10-24 | — | not installed | PyAV bundles its own libs, so not required | — |
| Node | 2026-10-24 | — | v24.13.0 | — | — |
| Meta Wearables DAT iOS | 2026-10-25 | github.com/facebook/meta-wearables-dat-ios, samples/CameraAccess | Swift Package 1.0.1; MWDATCore / MWDATCamera / MWDATMockDevice; iOS 17.2+ | API surface read from the official sample (see META_SDK_INTEGRATION.md); **not compiled** — no Xcode on this Mac | glasses thermal/battery not in sample APIs |
| Muse Spark latency options | 2026-10-25 | api.meta.ai | `reasoning_effort`: minimal/low/medium/high/xhigh/max; `json_object` | minimal + json_object: 0.9–1.6 s vs strict json_schema 0.9–8.4 s | — |
