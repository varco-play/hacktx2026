# ConsentLens — HackTX 2026

> **Status (2026-10-24 19:00 CDT):** working MVP draft. Webcam → local face detection → session re-ID → latched privacy → **blurred pixels in saved video**, protected-only live preview, Meta Muse voice path. See `HANDOFF.md` for what is verified vs not.

## Run it (Apple Silicon Mac)

```bash
python3 -m pip install --user uv && export PATH="$HOME/Library/Python/3.9/bin:$PATH"
uv python install 3.11 && uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.lock.txt
scripts/fetch_models.sh                 # YuNet, SFace, MediaPipe; checksums verified
cp .env.example .env                    # then add META_MODEL_API_KEY locally
.venv/bin/python -m uvicorn backend.app.main:app --port 8000
```

Open http://127.0.0.1:8000 → **Start session** → **Start voice** → **Start recording**. macOS must allow Camera + Microphone for the app running Python.

- Tests: `.venv/bin/python -m pytest`
- Replay a file instead of the camera (shown as **TEST INPUT**): `TEST_VIDEO=path.mp4 .venv/bin/python -m uvicorn backend.app.main:app`
- Dev-only manual protect button: `ENABLE_DEV_CONTROLS=true` (labeled `MANUAL_TEST`; keep off for judges)
- Developer diagnostic original file (saved locally, never served): `ENABLE_DIAGNOSTIC_ORIGINAL=true`

---

## Handoff spec

**Status:** build specification and researched implementation guidance, **not an implemented project**. **Event:** HackTX 2026, Oct 24–25, Austin. Final submission listed in ceremony: Sun Oct 25, 11:30 AM local; recheck official Devpost/Discord. **Target team:** two developers with Claude Code/Codex. **Device:** MacBook Air M3/M4; no assumed Meta glasses.

## Begin here — do not start coding blindly

1. Read this file, `CLAUDE.md` or `AGENTS.md` (as appropriate), and every file under `docs/` referenced below.
2. **Before code:** run the research/preflight in `docs/02_RESEARCH_AND_VALIDATION.md`; verify current official API shapes, local camera/mic permissions, hardware, models, licenses, account access, and event rule changes. Write findings in `docs/RESEARCH_RESULTS.md` (create it).
3. Ask the owner the **blocking questions** in `docs/01_DECISIONS.md` *once*, consolidated. If owner is unavailable, use the marked conservative defaults and proceed; do not repeatedly interrupt.
4. Request credentials by secure local `.env` configuration, **not in chat or git**. Read `docs/07_APIS_AND_ENV.md`.
5. Agree `docs/04_CONTRACTS_AND_POLICY.md` before parallel implementation. Treat one worker, one camera, one source of identity/privacy truth as invariants.
6. Build in vertical slices and prove recording of actual blurred pixels. Use `docs/05_BUILD_SEQUENCE.md` and `docs/06_TESTS_AND_BENCHMARKS.md`.
7. If another developer/agent is active, use `docs/08_COLLABORATION.md` and coordinate branch + changed-file boundaries.
8. Pitch **what works**, not promises; see `docs/10_DEMO_AND_SUBMISSION.md`.

## File map

| File | Purpose |
| --- | --- |
| `CLAUDE.md` | Claude Code root instructions |
| `AGENTS.md` | Codex root instructions |
| `docs/00_PRODUCT_AND_BOUNDARIES.md` | Product behavior, rationale, scope, anti-goals |
| `docs/01_DECISIONS.md` | Owner questions, defaults, unresolved policy decisions |
| `docs/02_RESEARCH_AND_VALIDATION.md` | Mandatory documentation and environment checks |
| `docs/03_SYSTEM_ARCHITECTURE.md` | Components, runtime, model choices, timing, fail-safe path |
| `docs/04_CONTRACTS_AND_POLICY.md` | Common interfaces, state machine, JSON examples, API boundary |
| `docs/05_BUILD_SEQUENCE.md` | Ordered deliverables, dependencies, exits, risk budgets |
| `docs/06_TESTS_AND_BENCHMARKS.md` | Tests, evaluation matrix, measured success criteria |
| `docs/07_APIS_AND_ENV.md` | What keys to create and how to configure services |
| `docs/08_COLLABORATION.md` | Git/merge coordination and transparent agent handoffs |
| `docs/09_PRIVACY_SECURITY.md` | Biometrics, retention, failure policy, raw video restrictions |
| `docs/10_DEMO_AND_SUBMISSION.md` | Demo, judge questions, prize-track evidence |
| `docs/11_AGENT_PROMPTS.md` | Copy-paste kickoff / handoff prompts |
| `docs/12_CONSENT_LLM_PROMPT.md` | Output schema and adversarial utterances |
| `docs/13_REQUIREMENTS_TRACEABILITY.md` | Crosswalk preserving all earlier features, contradictions, and deferred decisions |
| `docs/14_OWNER_QA_AND_RELEASE_CHECK.md` | Owner question bundle and demo-release gate |
| `history/` | Read-only copies of both earlier full plans, so original context is preserved |
| `.env.example` | Configuration names and safe defaults, **no secrets** |
| `.gitignore` | Secrets, recordings, models, local biometric data ignored |

## Source of truth and precedence

Latest explicit owner decision > these docs > verified official current docs > assumptions. If a new decision changes the product, update `docs/01_DECISIONS.md` and `DECISIONS_LOG.md`, then any affected contract and tests. Avoid coding two interpretations silently. Previous `ConsentLens-Team-Plan.md` and `ConsentLens_v2_Architecture_and_Critique.md` are historical context only, **not** competing specifications.

## Definition of an honest minimum demo

One actual webcam feed; two visible volunteers; two distinct stable IDs during a scene; a spoken refusal is transcribed, interpreted, attributed when evidence is sufficient; the **correct** face is blurred in the actual saved protected recording; permission stays denied while they move; a returning face is shielded while re-identification is unresolved; ability to show limitations and a refusal timeline. Deliberate eye-cover gesture is desirable independent input if it doesn't jeopardize the voice-first demonstration. Meta glasses / system-wide bypass prevention / cloud evidence vault **are not claimed**.

## No mandatory AWS

Use local face detection and local session gallery in the hot loop. AWS Rekognition is optional comparison after passing the demo. `FaceId` in an AWS collection is not proof of who spoke and not equivalent to a global legal identity.
