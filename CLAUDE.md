# Claude Code root instructions — ConsentLens

Read `README.md` and **all applicable** `docs/*.md` before changing source. You are an implementation agent, not the product authority. Check your tool/permissions state; **never claim to have researched, tested, used an API, or connected real glasses unless you actually did**.

## First response before edits

1. Summarize the product in 5 lines, list the key hard constraints.
2. Show a small research + environment preflight plan from `docs/02_RESEARCH_AND_VALIDATION.md`.
3. Ask the consolidated **blocking questions** in `docs/01_DECISIONS.md` if unresolved; offer defaults for nonblocking questions.
4. Identify other active git branches/processes; propose nonoverlapping change areas.
5. State the smallest real end-to-end milestone.

## Implementation requirements

- Keep one canonical `FramePacket -> VisionEngine.step -> FrameResult -> protected recorder` path. Separate microphone/LLM services must enqueue validated requests, never mutate state concurrently.
- Video processing on local device; only speech transcripts and minimal context sent to LLM by default. Do not send raw bystander face imagery/embeddings to Gemini/Meta/AWS without owner approval, lawful basis, and explicit test participant consent.
- Gemini or Muse **interprets words**, not identity. Mouth motion provides a candidate, not proof. No confident speaker assignment when ambiguous. A model cannot call an unrestricted `unblur` tool or write database rows directly.
- Defaults: visible when genuinely new and no recorded refusal; **temporarily shield while deciding whether a new detection is a protected return**. Do not equate visibility default with consent.
- Privacy writes are monotonic denial in core build; subject-verified reversal is a separate optional future feature; never wearer-only override.
- Fail protected output closed for known protected/uncertain identities. Never leak raw pixels via preview, encoder fallback, thumbnail, error page, log, or debug endpoint.
- Session-local biometric feature gallery, consenting volunteers only, no identity database shared across sessions.
- Cloud Meta glasses/firmware enforcement and secure evidence escrow are future architecture **only**.
- All claims in README/demo tied to actual passing tests, measured FPS/latency, and known limits.

## Working practice

Small commits and frequent runnable checkpoints. Run tests before declaring done. If another coding agent is in same repo, respect code ownership, do not overwrite uncommitted work, coordinate shared contracts before edits, log integration details in `HANDOFF.md`. Record verified versions/licenses/API endpoints in `docs/RESEARCH_RESULTS.md`. If blocked, report precise blocker + fallback; make best progress on local MVP.

## Team split (from the earlier kit — confirm in `DECISIONS_LOG.md` if it changes)

- **Sarvar owns all code** (decided 2026-10-24 19:20; no teammate code incoming). The earlier Abbos split is void.
- Shared: `shared/contracts.py`, `backend/app/runtime.py`, `requirements*.txt`, `.env.example`, API routes. Coordinate before editing these.

## Project skills (`.claude/skills/`)

`/build-slice` (one tested vertical slice), `/privacy-audit` (red-team leaks), `/muse-integration` (real Meta Muse calls + fallback), `/demo-ready` (judge rehearsal). Where a skill mentions `TEAM_PLAN.md`, read `README.md` + `docs/` instead; `history/` is context only.
