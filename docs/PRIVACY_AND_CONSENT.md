# Privacy and consent

This is an engineering prototype with volunteers, not legal advice or a compliance claim.

## Consent states (per person, per session)

| State | Meaning | Shown |
| --- | --- | --- |
| UNKNOWN | No request yet. **Not consent.** | visible (default policy) or blurred (`PRIVACY_DEFAULT=protect`) |
| DENIED | Asked to be blurred (voice, eyes closed 2 s, hands over eyes 1.5 s) | blurred |
| GRANTED | The same person consented (✌ peace sign 1 s beside their own face, or their own "unblur me" bound to them) | visible |
| REVOKED | Consented earlier, then asked for blur again | blurred |
| UNCERTAIN | A face not yet identified while someone who asked for blur is missing | blurred until resolved |

Policy is deterministic code (`consent/policy.py`, `vision/engine.py`). Language models only classify a sentence into DENY / ALLOW / NO_REQUEST / UNCLEAR; they cannot change anyone's state.

**Who can unblur whom:** only the person themself. A peace sign counts only if the hand is clearly nearest that person's face (≥1.6× closer than any other face) and not resting on a face. Voice consent counts only when the speaker is matched to that face. Hearsay ("my friend says it's fine"), ambiguous speakers, the wearer, and LLM guesses never unblur anyone.

**Default policy:** visible until someone objects (owner's product choice). `PRIVACY_DEFAULT=protect` switches to strict opt-in: everyone is blurred until they show a peace sign.

## Speaker uncertainty

Speech-to-text never says which face spoke. We link a sentence to a face by correlating each face's lip opening with the microphone's loudness during that sentence (±200 ms), with a per-person noise floor learned from quiet moments. If nobody clearly wins (two people talking, voice from off-camera, lips not visible), **nobody is targeted**: the system briefly shields all faces, logs `REQUEST_UNRESOLVED`, and asks the person to look at the camera and repeat. Scores shown in the UI are uncalibrated evidence, not probabilities.

## Biometric data

- Face features (SFace, 128 numbers) are stored **only for people who asked to be blurred**, in memory, for the session.
- Everyone else is tracked by position only; their features are computed transiently to check "is this a protected person returning?" and discarded.
- Features are deleted when the person consents, and all are deleted at session end (`/api/session/end` reports the count).
- People who never asked leave no record after they leave the frame.

## Recordings

| Output | Default | Storage | Access |
| --- | --- | --- | --- |
| Protected video (blur in the encoded pixels) | on | Cloudflare R2 `protected/` if configured (local temp copy deleted after confirmed upload), else `recordings/` | dashboard link → 5-minute presigned URL |
| Raw / original | **off** | local only with `ENABLE_DIAGNOSTIC_ORIGINAL=true`; in R2 mode only if also `RAW_UPLOAD_R2=true` → `restricted/` | never linked or served by the app |
| Audio | not recorded | — | mic used live for commands only; Muse STT receives audio; only loudness numbers kept in memory for ~60 s |

The R2 bucket must stay private. The laptop owner can still read local files — this is not a tamper-proof vault.

## What we can and cannot guarantee

- **Can:** blur is in the saved pixels from the moment a request is applied; protection survives leaving and returning in the same session; a protected person whose face is lost (turned away) keeps a head-shaped blur via pose tracking; errors produce a slate, never raw frames; consent changes are logged with timestamps.
- **Cannot:** blur frames recorded **before** the request was understood (voice: ~0.5–2.5 s; gestures: their hold time); hide body, clothes or voice; guarantee correct speaker matching; persist protection after the session ends; affect recordings made by the glasses' own camera app.

## Network exposure

The dashboard, preview, state and recordings answer only to `localhost`. With `scripts/run.sh --lan` (for the phone companion app) other devices can reach only `/api/ingest`, which requires `INGEST_TOKEN`. Every state-changing request needs the `X-ConsentLens` header so other websites can't drive the camera.
