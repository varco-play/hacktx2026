# Codex / coding-agent instructions — ConsentLens

Root-level contract for Codex and any agent adhering to AGENTS.md. Read `README.md`, `docs/00_PRODUCT_AND_BOUNDARIES.md`, `docs/01_DECISIONS.md`, `docs/03_SYSTEM_ARCHITECTURE.md`, `docs/04_CONTRACTS_AND_POLICY.md`, `docs/06_TESTS_AND_BENCHMARKS.md`, and the latest `HANDOFF.md` and `DECISIONS_LOG.md` if present.

**Before any implementation:** verify toolchain and current official docs listed in `docs/02_RESEARCH_AND_VALIDATION.md`, record results, and ask only unresolved blocking questions once. Use defaults for nonblocking items. Do not invent SDK methods or model IDs. Do not send credentials into chat, code, logs, or public repos.

**Architecture immutables:** one camera owner, one vision worker, one canonical person registry/permission state; timestamped audio/video observations; local hot loop; LLM returns structured intent only; source-of-truth policy engine commits events; blur is in actual saved pixels; raw source isn't a protected-output fallback. Do not call APIs for each frame.

**Collaboration:** check `git status`, current branch and teammate status. Work in an agreed file slice/feature branch. No force pushes or mass refactors; never overwrite another developer's uncommitted files. Propose contract edits first. Commit working increments and write a concise `HANDOFF.md` with changes, test commands/results, known failures, next integration actions. Keep shared env and lockfiles synchronized; no hidden alternative demos.

**Trust and evidence:** don't misstate automated speaker identification from mere transcript or random mouth movement. Never claim native Meta glass pipeline modification, Meta vault, production biometric compliance, zero leaks, exact frame rate or perfect recognition without proof. Name experimental fallbacks. Use volunteer consent and delete biometric demo artifacts on cleanup.

**Expected deliverable after each slice:** code paths changed, interface impact, evidence of tested end-to-end flow, meaningful failing tests, next runnable command. Prioritize a working local demo over optional cloud services.
