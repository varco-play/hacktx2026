# ConsentLens — paste-ready Claude prompts

## 1. Start a Claude Code session (best first prompt)

Read `CLAUDE.md`, `TEAM_PLAN.md` if present, the repository tree, and `shared/contracts.py` before writing code. We are building the ConsentLens HackTX Meta-track demo, not a production product. I own `vision/` and frontend implementation; my teammate owns backend, recording, scaffold, and Meta integration. Inspect the actual current code and give me: (1) what is already real, (2) broken/missing links in the **single** camera -> vision -> privacy -> protected preview -> dual recording path, (3) the smallest high-value thing I can implement now **within my ownership**, (4) exact files and acceptance test. Do not edit files yet. Flag critical privacy failures. Avoid any redesign or second app.

## 2. Build my assigned vision/frontend work

Use `/build-slice`. You are my senior computer-vision pair programmer. Work **only** in my `vision/` and assigned frontend files unless I explicitly approve shared changes. Implement the smallest testable improvement to [DESCRIBE FEATURE]. Preserve face IDs, sticky privacy state, and the one-camera pipeline. Favor deterministic temporal gesture logic and robust fail-safe behavior over impressive-looking but fragile ML. Inspect current code before editing. After changes, execute existing focused tests and give me manual two-person webcam steps to verify. Do not claim re-entry works unless verified.

## 3. Debug a live bug

We observed: [EXACT BEHAVIOR AND REPRO STEPS]. Expected: [EXPECTED]. First locate the underlying code path and state transition. Show a 3-bullet diagnosis with evidence. Make the **minimum diff** to fix it without changing contracts or hiding the symptom. Add a regression test for the failing scenario. Rerun relevant tests and state explicitly what remains unverified on real camera.

## 4. Audit privacy before presenting

Use `/privacy-audit`. Act as a skeptical security/privacy reviewer. Try to find any situation where a person requesting blur can become visible again in the protected preview or protected recording, especially after hands drop, re-entry, occlusion, track-ID swaps, dropped detections, or ambiguous voice. Trace code, not intentions. Give severity, exact file locations, smallest fixes, and reproducible tests. Keep the original recording separate and the frontend protected-only.

## 5. Meta integration task for teammate

Use `/muse-integration`. Stay in teammate-owned backend/Meta modules. Test real Meta Muse credentials/endpoints **without exposing secrets**. Build the transcript -> strict privacy intent -> single vision engine command flow. Validate JSON and handle partial transcripts, timeouts, multiple visible people, and invalid target descriptions conservatively. If actual APIs cannot be called, mark integration unavailable and test the pipeline with visibly labeled TEST INPUT; do not simulate success.

## 6. Final judge demo review

Use `/demo-ready`. Do not propose new features. Audit demo startup, two-person gesture privacy, persistent blur, leave/return (if verified), real protected preview, dual playable recordings, and any actual Muse call. Give me the top 3 failure risks and the smallest fixes, exact test commands, a 60-second pitch, and a 2-3-minute live judge walkthrough. Never overclaim glasses-level enforcement or production security.

## 7. If using Claude.ai rather than Claude Code

Paste `CLAUDE.md` content into your Claude Project Instructions and upload the team plan as Project Knowledge. The slash-command skills above are for Claude Code's `.claude/skills/` mechanism; on Claude.ai, paste their contents as task prompts or use supported custom skill uploads if your plan/interface provides them.
