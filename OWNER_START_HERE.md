# Owner: start here in five minutes

1. Download/extract this whole folder into the **root of one shared private GitHub repository**. Preserve filenames `CLAUDE.md` (Claude Code), `AGENTS.md` (Codex), and `docs/`.
2. Review `docs/01_DECISIONS.md`. Confirm whether you have Meta glasses, whether two consenting volunteers are available, and whether you want to protect **earlier frames before someone refuses**. The default plan uses a laptop webcam, two volunteers, speech-first, and labels earlier exposure as unresolved rather than lying about it.
3. Get a Meta **Model API** key at https://dev.meta.ai/ for Muse Voice (if available), and a Google **Gemini API** key at https://aistudio.google.com/apikey. You don't need AWS keys for the MVP. DO NOT paste credentials into chats.
4. Copy `.env.example` to `.env` and enter credentials locally. `GEMINI_MODEL` must be filled with a **currently accessible model ID** after checking your account/model list. Verify `.env` stays ignored.
5. Open the repo in Claude Code or Codex. Tell it to follow `CLAUDE.md` or `AGENTS.md`, and paste the **One-agent kickoff** from `docs/11_AGENT_PROMPTS.md`. It must research installed API/library versions *before* implementing.
6. For two agents, use a branch per feature slice and the separate prompts in `docs/11_AGENT_PROMPTS.md`. Both must obey `docs/04_CONTRACTS_AND_POLICY.md` and leave `HANDOFF.md` on each slice.
7. Rehearse a real local camera demo and **open the encoded video file** before judging. Don't show a CSS-only blur as if it were actual protected footage.

## Critical truths

- The final product concept is **visible until refusal**, but that is not equivalent to legally valid consent.
- The LLM decides *what the speech means*; it cannot decide *who spoke* without matched visual/audio evidence.
- Face re-identification is local session-only for consenting participants, not an AWS cloud biometric database.
- The video **prior to the objection can contain an unblurred face** until a buffer/backfill feature is implemented.
- This is not a firmware modification of stock Meta glasses. The public SDK does not establish mandatory system-wide bypass-resistant redaction.
