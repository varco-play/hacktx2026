# 08 — Claude + Codex + teammate collaboration rules

**Goal:** two developers/agents can produce mergable code, not two separate apps. Don't prescribe who must do what; choose nonoverlapping slices based on availability. Contracts in `docs/04_CONTRACTS_AND_POLICY.md` are mandatory for all.

## Single repository and operating rules

1. Create one shared GitHub **private** repo. Both people clone the same `main`, share the handoff docs under source control, and never exchange zip files as the merging strategy.
2. Every agent starts with `git status`, current branch, `git log -3`, `README.md`, `AGENTS.md`/`CLAUDE.md`, `HANDOFF.md`, `DECISIONS_LOG.md`, and common contracts. Note concurrent processes/tools.
3. Main should be runnable. Work in named branches, e.g. `feat/vision`, `feat/speech-intent`, `feat/recording-ui`. Merge one coherent vertical slice at a time through review/PR or coordinated local merge; no force push.
4. **Agree shared contracts first**: FramePacket, FrameResult, SpeechTurn, PrivacyRequest, person state, event envelopes, route names. One side cannot add an incompatible `person_id` format without updating both consumers and tests.
5. Separate responsibility by **file paths/feature vertical slices** rather than two parallel architectures. If simultaneously editing `shared/contracts.py`, `backend/app/runtime.py`, dependency lock, `.env.example`, or API surface, stop and coordinate ownership. Don't overwrite uncommitted work.
6. Keep model weights, videos, embeddings, logs, screenshots with faces, `.env`, `.venv`, node_modules out of normal commits. Commit only code, manifests, anonymized fake fixtures and documentation.
7. Build mock adapters to integrate early, but mocks must be clearly identified and disabled in final judges' run. No fake API outputs shown as real.
8. Integration checkpoint every 30–60 min: a real FramePacket travels through engine and backend to UI **and saved protected artifact**. Shared imports/test commands run after every merge.
9. If blocked, write `HANDOFF.md`: branch, files touched, current behavior, commands run and output, contract changes, blockers, known defects, priority next step. Also note key availability WITHOUT keys.
10. Any agent can propose a change, but unrequested product changes require owner approval or documented fallback. Do not re-interpret default-visible and consent rules silently.

## Merge gates

Before accepting branch:

- Pass type check and relevant unit/integration tests.
- No secrets or raw volunteer face data in diff; no new unrestricted original-media route.
- Common contract compatibility verified in both Python and TypeScript.
- Record altered models/dependencies in lock/manifests; no hidden additional cloud bill.
- Demo end-to-end path still works: webcam -> protected pixels -> preview -> protected video.
- Changes to time/identity policy reviewed for privacy regression.

## Handoff template (`HANDOFF.md`)

```md
# Handoff — branch feat/... — YYYY-MM-DD HH:mm CDT
## What changed
## Files touched
## Exact commands/tests and actual outcomes
## Contract/API shape changes (none or precise diff)
## Known bugs / misleading UI indicators
## Provider access checked (yes/no; no token values)
## Merge and integration instructions
## Next smallest runnable task
```

## Agent-to-agent instructions

Do not tell the other agent only “my part is done.” Send exact branch/commit hash, import path, function/API contract, 2-line usage snippet, test command, and runtime expectations. Do not create a second camera capture loop, parallel identity registry or new private protocol without coordination.

## If only one teammate is coding

The same rules still hold. Build one slice to completion; use checklist docs to keep focus. Avoid speculative abstraction until enough working code exists to justify it.
