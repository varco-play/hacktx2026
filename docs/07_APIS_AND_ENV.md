# 07 — External credentials, installs, and operational setup

**Do not send passwords or API keys in chat, a committed file, screenshots, terminal recordings or issue comments.** Put local secrets only in repo-root `.env`, load server-side, keep `.env` in `.gitignore`. Use separate/restricted keys where possible, low spend caps, review provider privacy settings, rotate any leaked token. Agents should never ask owner to paste secrets into prompts.

## Owner credential checklist — required vs optional

| Provider | Owner creates | Used for | Required? |
| --- | --- | --- | --- |
| Meta Model API, https://dev.meta.ai/ | `META_MODEL_API_KEY`; check billing/access | Muse Voice Transcribe streaming STT; optional Muse Spark | **Required only to claim real Meta integration** |
| Google AI Studio, https://aistudio.google.com/apikey | `GEMINI_API_KEY` | Structured consent intent interpretation | **Required for Gemini interpretation** |
| AWS console, https://console.aws.amazon.com/ | AWS account, IAM credentials or role, allowed Rekognition region | Optional offline comparison of facial embeddings | **No** (skip MVP) |
| GitHub | Shared private repo, access for both teammates | Collaboration and backup | Recommended; no app secret needed |
| No account | OpenCV YuNet/SFace, MediaPipe model assets, FFmpeg | Local fast vision/video | Yes; license/model terms still verify |

A Meta developer app token, Facebook Graph API token, and Meta **Model API** key are not interchangeable. Don't attempt to call Muse with a Facebook Graph token. Note Meta's realtime speech WebSocket credentials are sent in the **handshake frame**, not a normal `Authorization` header. Read official schema and test one request rather than guessing protocol.

## API decision and provider adapters

Recommended voice-first sponsor combination:

- **STT primary:** `MetaVoiceTranscriber`, model `muse-voice-transcribe-1.0`, endpoint `wss://api.meta.ai/v1/asr/realtime`. Use actual documented audio sample format. Alternative file endpoint `POST https://api.meta.ai/v1/asr/transcribe` for smoke test (not a low-latency stream). Turn timestamps and optional audio-speaker labels are **not matched to faces**.
- **Intent primary:** `GeminiIntentInterpreter` with official Google `google-genai` Python SDK. Select an **account-available low latency stable Flash model** from current model list, config in `GEMINI_MODEL`, and response schema validated by Pydantic. Do not hardcode guessed latest model ID in code. LLM only classifies intent; never writes privacy state.
- **Sponsor-aligned alternative:** `MetaMuseIntentInterpreter` with `muse-spark-1.3` (as documented October 24), structured output via Meta Model API if account entitlement available. May substitute for Gemini on consent parsing if access/cost favorable, but do not run two LLMs for every utterance unless demonstrating measurable benefit.
- **No-credentials fallback:** `RuleBasedInterpreter` supporting a handful of explicit commands and labeled as fallback. Optional demo-injected transcript must be clearly labeled **simulated input**, never called “Muse integration.”

## `.env.example` variables

Read file at repository root. `ENABLE_DIAGNOSTIC_ORIGINAL=false` by default; original recording access only on local trusted test machine with consenting volunteers. `ALLOW_REMOTE_FACE_UPLOAD=false`. Use a dedicated real model asset directory not committed to source.

## Setup on Apple Silicon Macs

1. Install native Python 3.11 and Node LTS; `python3 --version`, `node --version`, `uname -m` (expect arm64). Install FFmpeg and ensure `ffmpeg -version`. Verify camera/mic OS permission to terminal or app hosting Python.
2. Create `.venv` with `python3.11 -m venv .venv`, source `source .venv/bin/activate`, and run package install from **agents' tested `requirements.txt` or lockfile**. Do not blindly mix OpenCV wheels. Confirm `python -c 'import cv2; print(cv2.__version__,hasattr(cv2,"FaceDetectorYN"),hasattr(cv2,"FaceRecognizerSF"))'`.
3. Use official OpenCV model download links, record exact model filenames, sizes/checksums and redistribution license in `models/MANIFEST.md`. Confirm bytes are ONNX binaries rather than Git LFS pointer text.
4. Install MediaPipe's correct Python package and task face landmarker bundle per official docs; verify a 2-face sample locally before depending on it. Record NUM_FACES/max face setting; test pixel coord handling and mirroring.
5. Setup Vite/React frontend, FastAPI backend on localhost. Confirm local camera backend and single webcam owner. Never expose dev server to public internet while raw diagnostic routes exist.
6. Copy `.env.example` to `.env`, add secret values **directly in your own environment**, never into chatbot message. Check that `git status` doesn't show `.env`.
7. Run independent Meta/Gemini smoke tests with dummy nonpersonal phrases; check cost/rate limits; then start full demo.

## Key creation instructions

**Meta:** Open https://dev.meta.ai/, create/sign into developer account, find Model API project / API key management, enable/bill as required, confirm Muse Voice and Muse Spark permissions. Consult https://dev.meta.ai/docs/speech-to-text and https://dev.meta.ai/docs/overview. Place generated key in local `.env` as `META_MODEL_API_KEY`. Do not assume access just because sponsor is Meta.

**Google:** Open https://aistudio.google.com/apikey, create an API key for a project with Gemini API enabled. Check current model availability and quotas in https://ai.google.dev/gemini-api/docs/models and https://ai.google.dev/gemini-api/docs/structured-output. Place in `.env` as `GEMINI_API_KEY`, model ID under `GEMINI_MODEL`.

**AWS (optional):** if deliberately testing Rekognition, create an IAM principal or assumed role with *least privilege* restricted to specified collection/region and actions needed; prefer short-lived credentials over static access keys; don't create broad admin keys. Configure region/profile in environment, set cost alerts, and **never index strangers without informed consent**. Skip altogether for live demo.

## Security notes

API calls off video hot loop; retry/backoff and timeouts. No raw audio/face images sent to Gemini by default—only text and safe metadata. For Muse, microphone audio is sent to provider; get volunteers' agreement. Do not store provider transcripts by default beyond ephemeral session metadata. Stop processing/recording on disk or permission errors; don't silently downgrade protected stream to raw.
