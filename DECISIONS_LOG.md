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
