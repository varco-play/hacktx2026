# 01 — Owner questions and defaults

The coding agent must **ask the owner once** about blocking items and log answers in `DECISIONS_LOG.md`. Do not halt the project on optional questions. If unavailable, proceed only with the explicit conservative defaults below; never silently treat assumptions as user agreement.

## Blocking decisions (ask before claiming completed behavior)

| Question to owner | Why it matters | If no answer immediately |
| --- | --- | --- |
| Do you have *physical* compatible Meta glasses, or only Mac/iPhone cameras? | Determines SDK vs webcam. | **Mac webcam demo**; describe glasses as future integration. |
| Are two willing volunteers available for local video + biometric test? | Face gallery and speech synchronization require real users. | Use self + consenting teammate; no third-party face datasets without license/consent. |
| Can you provide Meta Model API key/account access and Google Gemini API key **locally**? | May block Muse/Gemini work. | Run local phrase-rules + labeled simulated ASR input; do not claim real integration. |
| Will we release/download a live-processed video that can include a person's face before they object? | Fundamental privacy product requirement. | Clearly label as **future-frames-only** for MVP; do not claim whole-video protection. |
| Is the main demo **speech-first**, with eye-cover as bonus? | Changes high-risk critical path. | **Yes: speech-first** as latest instruction. |

## Important product choices (document, not necessarily block code)

- Reversal/unblur: recommend **DENIED is latched** for MVP. If implemented later, require affirmative consent bound to same person and a trusted verification flow. Never grant on “my friend said yes” or recorder override.
- When unidentified voice says “blur me”: recommended shield/pause owner output and show unresolved, rather than blur random person; bound length/UX policy for production still unsolved.
- Returning face: shield any plausible match while comparison pending. New unambiguous subjects remain visible.
- Original video: for **developer diagnostic only**, optionally on a private local disk; never imply Meta owns a vault. Owner-access only protected video *within the demo UI*, not enforced against laptop OS user.
- Audio in saved output: default **video-only** for MVP; microphone is used for intent only. Do not claim audio anonymity.
- Runtime target: initial 640×480 two faces, aim ~10–15 FPS measured; favor stability to invented benchmark target. All performance numbers must be observed.
- Cloud: local session gallery/SQLite only if necessary; AWS Rekognition as separately approved optional experiment.
- Models: OpenCV YuNet/SFace, MediaPipe Face Landmarker, fast local visual approach; TalkNet optional feasibility gate. Meta Muse for STT, Gemini for semantic parsing as owner suggested. Muse Spark alternate for stronger Meta sponsor alignment.

## Ask these only if time permits

- Which spoken languages should be supported (English default)?
- Must recording preserve audio? (default no)
- Should wearer have manual ability to request consent/unblur? (default no)
- Wants single-camera laptop demo vs separate phone camera? (default laptop)
- Wants a delayed output/backfill to protect the pre-objection segment? (strongly recommend but higher complexity)
- Which event prize tracks will be entered, and is a genuine Meta API integration required? (verify organizer)

## Decision recording format

Use `DECISIONS_LOG.md` entries:
`YYYY-MM-DD HH:mm local | decision | rationale | impacted docs/contracts | owner approval/source`.
No unresolved decision should be misrepresented as user instruction.
