---
name: build-slice
description: Implement the smallest testable end-to-end ConsentLens feature without breaking team contracts or privacy invariants.
---

# Build a working slice

Use this skill for any requested feature or integration in ConsentLens.

1. Inspect `TEAM_PLAN.md` if present, `CLAUDE.md`, `shared/contracts.py`, relevant owners' files, and existing tests. Never assume a route, module, or payload exists.
2. Report: **current behavior**, **requested behavior**, **owner**, **inputs/outputs**, **invariants**, **acceptance test**. Highlight any incompatible contract or second-camera risk before changes.
3. Find a minimal vertical implementation in the existing pipeline. Prefer to extend one existing module rather than scaffold an alternative app, state registry, or capture loop.
4. For privacy logic, keep state changes deterministic; never put LLM/network calls into frame-critical work. Maintain original/protected frame separation.
5. Add at least one focused test for behavior, and one negative/failure case where relevant. Run them. Give a manual webcam validation procedure if software tests cannot demonstrate the full feature.
6. Report files changed, test commands/results, actual observed behavior versus unverified expectations, and next step. Do not claim tests you could not execute.

Never implement offline blur/post-processing as a substitute for live protected encoding. Never quietly alter another teammate's directory or shared contracts.
