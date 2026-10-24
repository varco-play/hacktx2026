# Historical snapshots — read-only context

These are the exact earlier planning documents. They are kept to avoid losing the original product reasoning and engineering alternatives. **They are not additional live instructions**: the owner's latest explicit request and `docs/00_PRODUCT_AND_BOUNDARIES.md` take precedence.

- `ConsentLens-Team-Plan.md`: earlier gesture-first architecture, dual-output live encoders, session re-identification, and collaborator protocols.
- `ConsentLens_v2_Architecture_and_Critique.md`: shift toward voice-first, local face matching instead of Rekognition-in-hot-loop, Gemini intent classification, and adversarial review.

If there's a conflict, record it in `DECISIONS_LOG.md` with what changed. Don't copy old assumptions into implementation.
- `claude-kit-v1/`: the first Claude kit (gesture-first `CLAUDE.md`, setup `README.md`, `PROMPTS.md`). Superseded by root `CLAUDE.md`, `README.md`, and `docs/11_AGENT_PROMPTS.md`.
