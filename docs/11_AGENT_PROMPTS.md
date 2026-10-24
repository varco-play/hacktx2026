# 11 — Copy-paste prompts for Claude Code / Codex

## One-agent kickoff (paste after opening repo root)

> You are building ConsentLens for HackTX 2026. Read README.md, CLAUDE.md or AGENTS.md, and all relevant docs/ files. Do NOT start coding immediately. First verify official current OpenCV/MediaPipe, Meta Muse Voice and Gemini structured-output documentation plus installed versions and camera/mic permissions; record findings in docs/RESEARCH_RESULTS.md. List the blocking owner questions in docs/01_DECISIONS.md once, with safe defaults. Then implement the smallest real end-to-end slice webcam -> local face detection -> privacy policy -> protected preview and **actual saved video** using shared/contracts. Keep one registry and one camera owner. Report actual passing tests/limitations and never simulate Meta connectivity without labeling it.

## Parallel Agent A: vision / identity / active speaker

> Read the project docs and current HANDOFF.md. Own only the agreed vision-engine slice; confirm file boundaries with the other agent before edits. Implement local YuNet/SFace face detection/re-ID, tracks and session gallery, MediaPipe lip movement time series, a deliberately conservative active-speaker candidate scorer, and blur pixels through FrameResult. Accept typed PrivacyRequest events; do NOT call Gemini, read cloud provider keys, own a second camera, or write a second permission registry. Add tests for ID swaps, re-entry leak frames, offscreen speaker ambiguity and renderer failure. Publish exact branch/commit, interfaces, commands, measured results and known failures in HANDOFF.md.

## Parallel Agent B: capture, speech, recording, UI

> Read all docs and HANDOFF.md. Agree the shared contract with other agent before coding. Own an agreed distinct slice (camera worker, FastAPI, STT/LLM adapters, protected video recorder, React UI); never create independent face IDs/permission state. Verify Meta Voice WS handshake/audio format and Gemini structured JSON from live official docs, run one real API smoke test without exposing secrets. Use timestamped SpeechTurn and ConsentInterpretation; queue verified requests to the vision policy engine, no direct DB edits. Save protected pixels rather than overlays. Show clear live vs fallback API status. Add integration tests and HANDOFF.md with branch/commit and exact run commands.

## Integration-agent prompt

> Read latest main, both feature-branch HANDOFF.md records, shared contracts, and decisions log. Do not redesign architecture. Merge with short review. Reconcile types/enum names, timestamps, camera ownership, recorder input, and voice event queue. Run a real laptop camera two-person rehearsal and verify actual encoded protected file. Fix high-severity misattribution/privacy leaks before any UI polish. List passing and failing tests, measured results, and what remains aspirational. No force pushes without owner approval.

## Adversarial reviewer prompt

> Act as a skeptical Meta staff engineer and privacy reviewer. Inspect source code and evaluation output, not just pitch claims. Try to break ConsentLens using early objection, offscreen speaker, lip motion mismatch, ID swap, return-after-exit, occlusion, cloud timeout, encoder failure and raw output fallback. Report each issue severity, repro steps, owner-visible privacy harm, minimal fix and regression test. Do not modify files unless asked. Explicitly identify false statements about native Meta glasses, secure evidence storage or legal compliance.

## Submission editor prompt

> Compare Devpost README and demo script to working code, actual provider logs and measured trials. Remove every claim not supported by a real execution. Separate implemented, experimental and proposed features. Emphasize unique gesture/voice-to-identity association and session-persistent selective face redaction, while disclosing prior unblurred frames and no stock-glasses enforcement. Produce concise judge demo and source attribution, and recheck submission time.
