# ConsentLens

**Bystander-controlled privacy for camera glasses.** Say "blur me", close your eyes for 2 seconds, or cover your eyes, and your face is blurred in the live view *and* in the saved video. You stay blurred when you leave and come back. Only you can undo it: hold a ✌ peace sign next to your face or say "unblur me".

Built at HackTX 2026 (Meta track). A Mac webcam / USB phone camera stands in for Meta glasses; see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the path to the Meta Wearables Device Access Toolkit.

## How it works

```text
camera ─► face detection + tracking ─► who is this? (only people who asked for blur are remembered)
   │            │                        ─► lips / eyes / hands / head pose (MediaPipe)
   │            └─► gestures: eyes closed 2 s · hands over eyes 1.5 s · ✌ peace sign 1 s
mic ─► Meta Muse speech-to-text ─► fixed phrases instantly, LLM for the rest
        └─► who spoke? lips moving in sync with the voice ─► consent rules ─► blur in real pixels
                                                                 ─► live preview + H.264 recording
```

- Blur is drawn into the actual frames that are encoded — not a CSS overlay.
- Face features are stored **only** for people who asked to be blurred, only for the session, and deleted when they consent or the session ends.
- If the system can't tell who spoke, it targets nobody and asks the person to repeat.
- Recordings upload to a private Cloudflare R2 bucket (or stay local if R2 isn't configured). Raw footage is off unless explicitly enabled and is never linked to the browser.

## Run it (Apple Silicon Mac)

```bash
python3 -m pip install --user uv && export PATH="$HOME/Library/Python/3.9/bin:$PATH"
uv python install 3.11 && uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.lock.txt
scripts/fetch_models.sh          # YuNet, SFace, MediaPipe face/hand/pose (checksummed)
cp .env.example .env             # add META_MODEL_API_KEY, optional Gemini + R2 keys
scripts/run.sh                   # http://127.0.0.1:8000
```

Run it from Terminal.app so macOS asks for Camera and Microphone access. Then **Start session → Start voice → Start recording**.

- Tests: `.venv/bin/python -m pytest`
- Replay a file instead of the camera (shown as TEST INPUT): `TEST_VIDEO=clip.mp4 scripts/run.sh`
- Dev mode (auto-reload, manual test controls, local raw copy): `scripts/run.sh --dev`
- Phone companion app on the network (only the token-protected ingest is reachable): `scripts/run.sh --lan`
- Benchmark profiles: `nice -n 19 .venv/bin/python scripts/benchmark.py clip.mp4`
- Scripted API calls need the header `X-ConsentLens: 1` on every POST.

## Stack

Python 3.11 · OpenCV (YuNet, SFace) · MediaPipe (face, hand, pose landmarkers) · PyAV/libx264 · FastAPI · Meta Muse Voice Transcribe + Muse Spark · Google Gemini (optional) · Cloudflare R2.

## Docs

| | |
| --- | --- |
| [Architecture & critique](docs/ARCHITECTURE.md) | pipeline, interfaces, Meta glasses path, known weaknesses |
| [Meta SDK integration](docs/META_SDK_INTEGRATION.md) | Modes A/B/C, DAT 1.0.1 API, companion app, what is and isn't tested |
| [Glasses optimization](docs/GLASSES_OPTIMIZATION.md) | profiles, thermal governor, measured CPU/FPS |
| [Phone camera setup](docs/PHONE_CAMERA_SETUP.md) | USB/Continuity phone as camera, permissions, audio |
| [Privacy & consent](docs/PRIVACY_AND_CONSENT.md) | consent states, data handling, guarantees and limits |
| [Demo guide](docs/DEMO_GUIDE.md) | commands, 2-minute script, troubleshooting |
| [Contracts](docs/04_CONTRACTS_AND_POLICY.md) · [LLM prompt](docs/12_CONSENT_LLM_PROMPT.md) | shared types, state machine, intent schema |
| [Results](evaluation/results.md) | measurements and acceptance tests |

## Limits (honest)

Blur starts from the moment someone asks — earlier frames are not retroactively blurred yet. Face blur doesn't hide clothes, voice or context. "Who spoke" is an audio-visual heuristic and fails safe when unsure. This prototype can't change recordings made by the glasses' own camera app.
