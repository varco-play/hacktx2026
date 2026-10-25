# Decisions log

`YYYY-MM-DD HH:mm local | decision | rationale | impacted docs/contracts | owner approval/source`

- 2026-10-24 18:40 CDT | `docs/` handoff (voice-first) is the spec; older gesture-first kit moved to `history/claude-kit-v1/` | `docs/02` says latest voice-first brief wins; owner said "use most relevant" of duplicate files | CLAUDE.md, README.md | owner instruction (chat), file choice by Claude
- 2026-10-24 18:40 CDT | Mac webcam demo, no glasses | default from `docs/01`; unconfirmed | 00, 03 | **default — owner to confirm**
- 2026-10-24 18:40 CDT | Two volunteers = Sarvar + Abbos | default | 06 | **default — owner to confirm**
- 2026-10-24 18:40 CDT | Future-frames-only protection after refusal (no backfill) | default; honest label | 00, 09, 10 | **default — owner to confirm**
- 2026-10-24 18:40 CDT | Speech-first; eye-cover gesture as stretch | default from `docs/01` | 05 | **default — owner to confirm**
- 2026-10-24 18:55 CDT | Intent: local fixed-phrase rules first, **Meta Muse Spark (`muse-spark-1.3`) structured output** as LLM; Gemini adapter kept but unavailable | Gemini key returns 401; Muse Spark verified working (3.5–9 s); all-Meta stack fits sponsor track | 03, 07, 12 | Claude recommendation — **owner to confirm**
- 2026-10-24 18:55 CDT | `.env` variable names renamed to `META_MODEL_API_KEY` / `GEMINI_API_KEY` (values untouched) | match `docs/07` | .env.example | Claude, mechanical
- 2026-10-24 18:55 CDT | Saved output is video-only; DENY latched, no unblur path | `docs/01` defaults | 04 | default
- 2026-10-24 19:20 CDT | Repo stays **public** for now | owner choice (docs/08 recommends private; no secrets/biometrics committed — scanned each push) | 08 | owner (chat)
- 2026-10-24 19:20 CDT | **Gemini is the primary intent "brain"**; Muse Spark used only as fallback on Gemini error; `INTENT_PROVIDER=gemini` | owner choice, supersedes 18:55 Muse-primary recommendation. Current Gemini key is invalid → runtime shows `gemini UNAVAILABLE` and uses Muse Spark until a valid AI Studio key + GEMINI_MODEL are set | 07, 12 | owner (chat)
- 2026-10-24 19:20 CDT | **Sarvar owns all code**; no teammate code incoming; full MVP built in this repo | owner (chat) | CLAUDE.md team split | owner (chat)
- 2026-10-24 19:20 CDT | Live camera confirmed working when server started from Terminal (macOS grants Terminal, not Claude) | measured 30 fps, vision p50 10.7 ms | 07 | observed
- 2026-10-24 19:30 CDT | Speaker binding: lip-motion heuristic (MediaPipe inner-lip gap / eye distance) for 2+ people; single visible person still needs lip motion when landmarks exist, else OFFSCREEN | docs/03 Gate 3; thresholds need live calibration | 03, 04 | Claude, per docs
