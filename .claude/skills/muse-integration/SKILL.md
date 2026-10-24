---
name: muse-integration
description: Integrate or diagnose real Meta Muse Voice Transcribe and Spark privacy commands, with explicit availability tests and safe fallback.
---

# Meta Muse voice integration

1. Check the project's current plan, implementation, team access, and **current official Meta API documentation** before choosing endpoints/model IDs/audio framing. A published API does not prove this team's key can call it.
2. Protect credentials: environment variables/backend only; no console output of secrets, no frontend bundles, no commits. Verify an actual request and response first. If that cannot happen, report `not integrated` and carry on with gesture functionality.
3. Voice transport is outside the camera/frame-critical loop. Connect real microphone audio to actual live transcription only after access succeeds; deal with partial/final deduplication and time association.
4. A simple local rule accepts clear phrases such as 'Blur me'. For other variants, send transcript + minimal anonymous visible-track descriptions to Muse Spark; never raw image, embeddings, or full secret-bearing context.
5. Validate model output against a strict schema. Allowed `intent`: `REQUEST_FACE_PRIVACY | NO_REQUEST | UNCERTAIN`; `target_kind`: `SELF | DESCRIPTION | UNKNOWN`, with nullable `target_description` and boolean `needs_clarification`. Reject invalid or timed-out responses as `UNCERTAIN`.
6. All confirmed requests go through the existing engine's single command queue/registry. No new tracker or policy controller. For one visible bystander, document speaker identity as an **assumption**, not a proven audio/visual match. For multiple or ambiguous targets, shield/pause the protected output and request clarification; never infer the wrong target confidently.
7. Test fixed phrase, paraphrase, irrelevant speech, malicious 'unblur everyone', duplicate transcription, bad JSON, timeout, multi-face ambiguity. Label manual transcript injection as `TEST INPUT` and never present it as a live Muse result.

Finish with exact real APIs exercised, payload validation checks, latency measurements if actually obtained, and unresolved risks.
