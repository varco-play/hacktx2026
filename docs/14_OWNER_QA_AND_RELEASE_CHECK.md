# 14 — Owner Q&A and demo release gate

## Concise owner questions (ask as **one** message, not dozens)

The agent should check `docs/01_DECISIONS.md` and only ask for information that cannot be obtained from the repo/environment:

1. Are actual supported Meta glasses available, or do we use the planned Mac webcam?
2. Are at least two informed consenting adult volunteers available for an on-camera demo?
3. Are credentials for Meta Model API (Muse Voice) and Gemini available as local environment variables? Never ask to paste their values into chat.
4. For the MVP, is *future-frames-only after refusal* acceptable, or does protected export need prior-face backfill? If uncertain, ship clearly labeled future-frames-only, not a falsely complete privacy claim.
5. Confirm voice-first remains first priority, with eye-cover gesture as stretch goal.

Never block local face detection on an unanswered question. Record assumptions in `DECISIONS_LOG.md` and flag any user approval required to demonstrate a claim.

## Release gates before judges

- [ ] README shows exactly how to start the real local camera demo.
- [ ] Running pipeline actually encodes blurred pixels in protected output, not just a CSS layer.
- [ ] Two distinct people are correctly tracked in at least one fresh, unrehearsed trial.
- [ ] STT/LLM integrations have actual logs of **successful nonsecret** requests or are labeled `UNAVAILABLE/FALLBACK`.
- [ ] Speaker attribution measures are reported honestly, particularly offscreen/overlapping voices.
- [ ] Protected person leaving and returning has recorded success/failure trials; no hidden frame leaks claimed away.
- [ ] Renderer failures never pass raw image through to protected preview/recording.
- [ ] Original diagnostics aren't exposed via ordinary app endpoints or public remote access.
- [ ] Model binary licenses, sources, package versions, and hash references captured.
- [ ] Permissions for volunteer biometric processing/recording documented; raw artifacts deleted per agreed retention.
- [ ] Screenshot/demo clearly labels Mac webcam as glasses stand-in.
- [ ] Scoreboards and slides don't imply Meta purchased, endorsed, or integrated the feature.
- [ ] What is future-only is separated visibly from running functionality.
- [ ] Devpost submission received before official deadline; ensure safe final git commit.

## Emergency cut order if deadline is close

**Never cut** core protected-pixel encoding, source-of-truth privacy state, honest labels, or fail-shield behavior. Cut in order: UI polish → gesture enhancement → AWS experiment → TalkNet → extra Meta tools → live phone/glasses adapter. If speaker attribution isn't robust, show an explicit limited valid case instead of faking automatic face choice.
