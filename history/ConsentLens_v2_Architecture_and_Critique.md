# ConsentLens v2 — Architecture, Objections, and Revised Build Specification

**Date:** 24 October 2026  
**Purpose:** A candid replacement proposal for the *technical architecture* of ConsentLens, using the user's latest voice-first design.  
**Status:** Engineering plan, not implemented or benchmarked.  
**Scope:** Two-person, 24-hour HackTX prototype; eventual Meta glasses integration is a proposal, **not** a supported firmware modification.

## 0. Executive decision

**Preserve the product behavior:** normally visible video; a person explicitly objects (speech, with deliberate face-cover gesture available as an alternative); the correct person is blurred; refusal persists when they leave and re-enter; the subject can later authorize a change; the camera owner should not override a subject's refusal by themselves.

**Reject the proposed naive pipeline:** `every frame → AWS DetectFaces/IndexFaces → unique person ID → Gemini hears “no” → blur face`. It fails on latency/cost, confuses face detection with persistent identity, and—most seriously—**has no reliable link between the voice and the face**. An LLM cannot establish who spoke from transcript text alone.

**Recommended hackathon implementation:** **local Python/OpenCV vision + local session-only face gallery + FastAPI + React/Vite + an asynchronously connected speech-to-text/LLM provider.** Only call an LLM when a meaningful utterance ends; do not put cloud calls in the per-frame blur path. Keep AWS as an optional *controlled experiment*, not the default live dependency.

**Most important engineering proof:** two people visible; Person A requests blur by speaking; the request is correctly associated with A (with explicit limited attribution conditions); A remains blurred after turning away and returning; B stays unblurred; exported protected video actually contains blurred pixels, not a CSS overlay.

---

## 1. Product semantics: what words mean

| Term | Meaning |
|---|---|
| `UNSPECIFIED` | The person has not made an explicit request. **In this prototype, the default output policy is visible; this is *not* evidence of legal or ethical consent.** |
| `DENIED` | A refusal attributed to that person has been accepted. Their face must remain hidden from the owner-visible output. |
| `GRANTED_AFTER_DENIAL` | A previously protected person has knowingly and verifiably reversed the decision. Not enabled by arbitrary speech in the MVP. |
| `PENDING` | The system has detected a refusal but cannot confidently identify its speaker or the face to protect. |
| `track_id` | Short-lived identity assigned to a box across adjacent frames. Not a durable face identity. |
| `person_id` | Session-local persistent ID associated with a face gallery. A provider-specific AWS `FaceId` is **not** itself proof of a unique real-world person. |

**Do not call this “everyone consents by default.”** Say “visible unless they object.” The distinction matters: the product cannot manufacture consent by setting a database boolean to `true`.

### Revised policy

1. A new, resolved person is shown unblurred until a valid refusal. This reflects the requested product direction, but has the privacy trade-off of exposure *before* objection.
2. Once `DENIED`, never expose that person in the protected recording merely because tracking fails, they lower their hand, or the network goes down.
3. The owner cannot unilaterally override `DENIED`.
4. A positive phrase such as “I'm fine with filming now” triggers `REVERSAL_REQUESTED`, **not immediate unblur**, unless the speaker is linked to the same protected subject and a second verification mechanism is present. Omit reversal from MVP if verification is not feasible.
5. Unattributed refusals become `PENDING`: record the request, temporarily shield relevant output, and request clarification rather than guessing whose face to blur.
6. A subject who says “don't record me” may be objecting to capture itself, not merely to appearance in the exported video. A blur feature is not a universal substitute for stopping recording where appropriate.
7. A protected copy created live **cannot erase frames before the objection** unless you add a pre-commit buffer or later redaction stage. Never claim the entire recording is consent-safe without addressing this.

---

## 2. Strongest objections to the new AWS + Gemini proposal

### Objection A — Recognition is not detection
AWS Rekognition can return face boxes and index face vectors into a collection, but a box/frame identifier is not a person's persistent identity. The application still needs: local association across adjacent frames, a persistent gallery, threshold calibration, duplicate prevention, and explicit handling of lookalikes and missed matches.

**Improvement:** Use a `track_id` for motion, and a separately matched session `person_id` for re-entry. Re-identify only when tracking is lost/restarted. Never index every video frame.

### Objection B — Who said “blur me”?
Audio-to-text → Gemini returns “refusal” but cannot determine whether A, B, or an off-screen observer spoke. AWS face IDs do not bridge audio to video. Audio diarization labels (`speaker_0`, `speaker_1`) do not correspond to face IDs.

**Improvement:** The demo supports a bounded attribution policy:
- For an explicit refusal, use a **verified target interaction** (e.g., actor points at self/holds a recognizable gesture), or controlled single visible speaker with the limitation clearly labeled; offscreen speech can still invalidate the latter assumption.
- For 2+ visible people, try an experimental active-speaker signal (lip motion synchronized to utterance) only if tested; otherwise do not automatically assign identity.
- If uncertain, shield while resolving, not a random face.
- Associate utterances to the video frames **at the utterance time**, not when the network response arrives.

### Objection C — LLM as camera controller
“Give Gemini some rules/skills and let it change database permissions” invites hallucinated actions, secondhand statements (“she said yes”), prompt injection from people speaking near the camera, and dangerous mistaken unblurring. An agent framework is unnecessary.

**Improvement:** LLM is an **intent parser**, not the policy engine. It outputs a small validated enum/JSON object. Deterministic code verifies speech timing, speaker attribution, old state, and permitted transition. Gemini cannot write AWS permissions or call “unblur” directly.

### Objection D — Every-frame AWS is expensive and slow
Rekognition Image charges by analyzed image and API; AWS's listed first-tier illustrative rate is approximately **$0.001 per image** for relevant groups. At 15 FPS, one call per frame is 900 billable image analyses/minute, approximately **$0.90/min or $54/hour**, before other calls/storage—illustrative, not a quote. Network round trips also make deterministic redaction harder. Using two or more APIs per frame increases consumption.

**Improvement:** Detect and track locally. Match face embeddings locally; optionally make AWS face-search calls only on confirmed session enrolment and rare re-entry events if there's a compelling reason and the participants opted into cloud biometric processing.

### Objection E — AWS face collection becomes a biometric surveillance store
Saving every bystander's face vector in AWS, including those who expressly object, increases risk, complexity and legal obligations. AWS “collections” store facial vectors, not an ordinary relational table; you would still need an app data store mapping provider face IDs to policies. Texas CUBI may require notice and prior consent for covered commercial biometric capture.

**Improvement:** Do not enroll every face in AWS. Use short-lived local features only for opted-in demo subjects. Delete at session end. For future commercial deployment, obtain specific legal/privacy review; do not claim de-identification because the vector lacks a person's name.

### Objection F — Automatic unblur on “it's okay” is unsafe
A third party can say “it's okay to film her.” An LLM could misunderstand quotations, negatives, irony, or who the statement applies to.

**Improvement:** A privacy refusal is one-way for the MVP. If reversals are included, require the *protected subject* to complete an explicit confirm step tied to their persistent identity, and never allow recorder-only reversal.

### Objection G — Default-visible exposes pre-refusal footage
If Person A spends 8 seconds on camera before speaking, those 8 seconds remain visible even if all subsequent frames are blurred. “Original + protected live encoders, no post-processing” is inconsistent with a guarantee that A doesn't appear in the resulting clip.

**Improvement:** Either (1) explicitly scope the MVP to **protection from activation onward**, or (2) add a delayed-buffer/redaction window, or (3) do an export-time privacy pass. Do not silently claim retroactive removal.

### Objection H — The Meta glasses story is unproven
Public Wearables Device Access Toolkit 1.0 supports camera/mic access for iOS/Android apps, but that is not verified privileged interception of every ordinary glasses recording. Browser dashboard ≠ embedded Meta recording feature.

**Improvement:** Prototype with a Mac webcam, label it accurately, and show a separate future integration diagram. Claim “candidate feature for Meta's trusted media pipeline,” not “installed on Meta glasses.”

### Objection I — Face blur isn't anonymity
Faces may be missed, incorrectly associated, or identifiable by voice/clothes/tattoos/context. Blur alone does not protect people who don't wish to be recorded at all.

**Improvement:** Use strong padded blur, a shield-on-loss policy after denial, clear limits, and local-only demo clips. Don't market “guaranteed privacy.”

### Objection J — Two concurrent cloud AI vendors add risk without value
Meta Muse streaming ASR + Gemini classification + AWS face search can be integrated, but creates more credentials, data flows, outages, pricing and uncertain latency. Using all three won't impress judges as much as a fast coherent product.

**Improvement:** Implement one `SpeechProvider` and one `IntentProvider` interface; choose a verified primary provider and one fallback. Reuse Meta technology where available for Meta sponsor relevance; use Gemini if it performs better or is the credential you actually have.

---

## 3. Proposed system architecture

```text
               CAMERA (Mac webcam for prototype; glasses adapter later)
                                      |
                               Capture thread
                                      |
                                 Timestamped frame
                                      |
                         LOCAL VISION WORKER (never waits for cloud)
                         |                |                    |
                  YuNet detector     Motion tracker      SFace embeddings
                         |                |                    |
                         +------- persistent session registry ----+
                                        |
                          deterministic CONSENT STATE MACHINE <------ validated command queue
                                        |                                     ^
                                Blur selected face                          |
                                        |                          intent/speaker resolver
                           Protected preview + MP4                           ^
                                        |                                     |
                            React/Vite dashboard              LLM JSON interpretation
                                        |                                     ^
                              original + processed                           |
                            recordings (demo diagnostic)           streaming speech-to-text
                                                                          ^
                                                                          |
                                                               Microphone audio chunks
```

**Invariant:** model inference and identity matching happen on the same time reference as frames. Audio events carry utterance start/end timestamps. The LLM can never mutate consent state by itself. A bounded processing queue and fail-shield logic prevent an old detector result from exposing a denied face.

**Originals:** A parallel raw recording is developer-accessible in this hackathon harness only. It is **not** a secure Meta evidence vault. A secure original under compulsory independent custody is a completely separate trusted-device/product/privacy problem.

---

## 4. Best-performing MVP stack, with reasons

| Concern | Recommended choice | Why | Avoid initially |
|---|---|---|---|
| Video runtime | **Python 3.11 + OpenCV** on Apple Silicon | Fast local processing; model integration; one native capture pipeline | Streaming each frame to Lambda/AWS |
| Face boxes | **YuNet ONNX** via OpenCV FaceDetectorYN | Small pretrained model and five-point face landmarks | Rekognition on every frame |
| Session face re-ID | **SFace ONNX** + cosine similarity + threshold/margin | Local, no ongoing upload and no AWS lock-in | Using bounding box index as person ID |
| Per-frame tracking | IoU/motion matching; optional Kalman | Cheap between detections; preserves temporary tracks | Running full embedding extraction every frame |
| Face blurring | **OpenCV padded ROI** with heavy pixelation/blur | Predictable and fast, demonstrably encoded pixels | CSS overlay |
| Optional gesture | MediaPipe hand/pose landmarks | Independent accessibility input; integrates into same state machine | Training from scratch |
| Streaming STT | **Muse Voice Transcribe** if Meta access verified; alternatively **Gemini Live transcription** | Both support live ASR; Meta is directly relevant to sponsor | Recording full clip then batch transcribing |
| Intent classification | Fast **deterministic phrase rules** plus **Muse Spark** or a **Gemini Flash** text model for ambiguity | LLM only on finalized utterances; schema bounded | LLM called on every frame; autonomous agents |
| Backend | **FastAPI** (one process/worker) | REST/WebSocket preview, events and lifecycle | Multi-service microservices |
| UI | **React + Vite + TypeScript** | Fast, familiar single-screen engineering dashboard | Account system and elaborate marketing site |
| Video write | **PyAV/FFmpeg** | Encodes actual raw and redacted frames, timestamps | Browser-only screenshot download |
| Session state | **In-memory registry + JSONL/SQLite for metadata** | Fast local lookups; simple cleanup | Cloud biometrics for all bystanders |
| Deployment | **Local first**; optional secure cloud demo site later | Reliable live webcam demonstration | Public cloud demo requiring broadband |

**Why not an LLM vision model for boxes?** Deterministic CV models are built for per-frame detection/tracking. A conversational model is slow and unnecessarily costly for that path. **Why not pure AWS?** You gain vendor integration but lose local determinism, privacy simplicity and budget.

### Provider choices — be deliberate

**Route A (Meta sponsor narrative):** Muse Voice Transcribe → fixed-command shortcut or Muse Spark → deterministic policy engine. Muse can return diarization labels, but these are *audio-speaker* labels only, not face identities.

**Route B (Gemini-first):** Gemini Live transcription (`gemini-3.5-transcribe-live`, check access/model) → Gemini Flash text classification for uncertain complete utterances → deterministic policy. The live transcription documentation notes a 10-minute session bound and no live diarization, so handle session restarts and don't claim speaker-to-face matching.

**Route C (lowest-risk first hour):** Browser/OS/local STT or basic transcript input → deterministic refusal phrase rules, visibly label test inputs. This proves the full interaction before external credentials are in place. Never claim mocked transcripts are real Muse or Gemini output.

**Choose one primary ASR provider after an actual streaming smoke test.** Do not put both Muse and Gemini transcription into the critical path. The providers may evolve; validate available model names in your own account before code freeze.

---

## 5. What AWS could usefully do — without being the whole design

AWS is **not a synonym for faster**. It is a cloud provider with distinct services.

| AWS component | Plausible optional role | Necessity for MVP |
|---|---|---|
| Rekognition `IndexFaces` | Enroll a **consented demo participant** into a collection for experimental cloud re-ID comparison | **No** |
| Rekognition `SearchFacesByImage` | Match a **cropped single face** against that collection on new/re-entering tracks | **No** |
| DynamoDB | Persist `session_id`, app `person_id`, current privacy status, opt-out events | **No**, replace with in-memory + JSONL |
| S3 | Store *protected-only* exported demo clips with retention limits | **No**, local video sufficient |
| KMS/IAM | Protect cloud artifacts and isolate service permissions | Required **if** cloud storage introduced |
| Rekognition Video streams | Streaming integration | **Do not rely on it**; official docs state streaming-video feature availability restrictions for new customers |

If using Rekognition, be aware: `SearchFacesByImage` uses the **largest face** in a supplied image; crop each face intentionally. `IndexFaces` returns an AWS `FaceId` for a vector, but you must own the application mapping and duplicate logic. Use threshold + runner-up margin and uncertain state. Delete face vectors and cloud artifacts after the consented experiment. **Never upload everyone's unblurred face to AWS merely to show sponsor buzzwords.**

### Cloud privacy checklist if you experiment

- Inform every test subject what biometric data and audio are captured, where they go, and when deleted.
- Use opt-in volunteers, no unsuspecting bystanders or crowd-wide facial enrollment.
- Short-lived test collection, least-privilege IAM and private S3 only if needed.
- Backend holds credentials; never put AWS or model API keys in React/browser source.
- Record deletion results. Do not claim AES/KMS or encrypted video custody unless implemented and verified.
- Check applicable privacy law and provider data-processing/opt-out settings before commercial use.

---

## 6. Event and state models (normative contracts)

```typescript
type PersonState = "UNSPECIFIED" | "DENIED" | "GRANTED_AFTER_DENIAL";
type IdentityConfidence = "TRACKED" | "MATCHED" | "UNCERTAIN";

type Person = {
  sessionId: string;
  personId: string;     // stable only in session
  trackId?: string;     // transient motion identity
  state: PersonState;
  identity: IdentityConfidence;
  lastSeenMs: number;
  consentLastChangedMs?: number;
};

type SpeechIntent = {
  intent: "REQUEST_BLUR" | "REQUEST_UNBLUR" | "NO_REQUEST" | "UNCERTAIN";
  target: "SELF" | "OTHER" | "UNKNOWN";
  originalText: string;
  utteranceStartMs: number;
  utteranceEndMs: number;
};

type PolicyDecision = {
  action: "DENY_PERSON" | "REQUEST_VERIFICATION" | "SHIELD_PENDING" | "NONE";
  targetPersonId?: string;
  reason: string;
};
```

Do **not** include raw face embeddings, audio streams, secret credentials, or arbitrary LLM-generated person IDs inside front-end metadata. Maintain a mapping between camera-frame time and utterance time. Validate LLM JSON against a strict schema and ignore nonconforming actions.

### State rules

```text
UNSPECIFIED --(verified refusal)------------------> DENIED
UNSPECIFIED --(no request / uncertain)------------> UNSPECIFIED / PENDING shield
DENIED      --(repeated refusal / identity lost)---> DENIED
DENIED      --(owner says 'unblur')-----------------> DENIED
DENIED      --(unauthenticated 'it's okay')--------> DENIED + REVERSAL_REQUESTED
DENIED      --(subject verified + explicitly opts in)--> GRANTED_AFTER_DENIAL [post-MVP]
```

**Detection status is separate from consent status.** Loss of a bounding box must never erase an opt-out record. Speaker attribution is also separate from both.

---

## 7. Voice path: the critical operational algorithm

1. Capture audio with monotonic timestamps. Stream to one speech-to-text provider.
2. Use finalized utterances or a highly constrained fast refusal phrase shortcut; deduplicate partial updates.
3. For clear phrases such as “please blur me,” a fixed rule can generate `REQUEST_BLUR` immediately; use the LLM for varied phrasing and negations (“do not unblur me”, “I don't want to appear”).
4. Parse LLM output to strict JSON with one of four intents. **No model tool access to DynamoDB or state mutation.**
5. Retrieve candidate people visible **during the utterance**; do not associate with faces visible only at response time.
6. Associate speaker to subject only when the evidence is adequate (verified single actor in a controlled demo, or separately implemented audiovisual association). If multiple plausible people, hold a `PENDING` request and shield temporarily rather than guessing.
7. Apply the `DENIED` transition through deterministic policy code. Log timestamp, source and association basis.
8. Rendering checks policy state for the current track + session re-ID registry, then blurs ROI in actual output pixels before encode.
9. If the face leaves, retain its `DENIED` state in session gallery; on return, shield new candidate regions until match is resolved when needed.
10. Requests to **unblur** never execute automatically in the basic demo.

**Why skills/agent orchestration do not help:** There is no complex multi-step autonomous planning problem. A tiny classifier + verifiable rules is simpler, faster, safer, and easier to judge.

### LLM instruction skeleton

> Classify only whether the *speaker is requesting their own face to be hidden or shown*. Ignore third-party claims as consent. Quoted examples, sarcasm, uncertain meanings and hypotheticals must return `UNCERTAIN` or `NO_REQUEST`. Emit only valid JSON from the fixed schema. Do not identify people or assign database IDs. You do not control the camera, storage, or permission state.

Policy remains responsible for what to do with that classification.

---

## 8. Real-time video design

- Capture 640×480 frames initially; aim for sustained 15+ protected FPS on Mac M3/M4, **measure rather than claim**.
- Detect faces every N frames if tracking is stable; choose N empirically (e.g., 3–5) and re-detect when tracker confidence drops. Never assume an old box is valid indefinitely.
- Face gallery stores several unoccluded SFace embeddings per *consented demo subject*; recognize returning subjects with cosine threshold + margin + repeated observations, and one-to-one assignment.
- When a previously protected person might be re-entering, shield temporarily until matching is resolved; do not expose frames while waiting for an AWS lookup or LLM.
- Blur padded head/face regions with strong pixelation; ensure preview and exported recording use the same protected pixels.
- On CV exceptions or uncertainty involving a protected person, shield affected region or full protected frame. Do not fall back to raw output.
- Parallel raw and protected recording is a technical comparison in the demo, not proof of secure trusted storage.
- Record frame timestamps, processing latency, frame drops, blur activation delay, and any protected-face leakage. LLM/network work is asynchronous.

**Unresolvable tension:** “Everyone instantly visible by default” and “never accidentally expose a previously denied subject while identity matching” conflict whenever a person first enters and recognition is pending. Accept brief shielding for uncertain re-entrants or explicitly document the leakage risk. There is no magic AWS face ID that eliminates it.

---

## 9. Milestones and cutting rules

| Gate | Minimum evidence | If missing |
|---|---|---|
| A — Video | One camera feeds local detector and produces two separately encoded streams | Stop cloud work, fix local pipeline |
| B — Independent people | Two faces, stable short-lived tracks, selective blur of one | Fix association before language models |
| C — Real voice | Actual mic utterance yields timestamped transcript and validated `REQUEST_BLUR` | Use the gesture/manual test input clearly labeled; do **not** fake live STT |
| D — Attribution | Correct person receives blur in controlled scenario; offscreen/multiple ambiguity handled visibly | Disable automatic multi-person voice attribution claim |
| E — Persistence | Denied subject remains hidden after moving, leaving and returning | Keep temporary protective shield; document measured failures |
| F — Recording proof | Saved processed file contains redacted pixels while other person remains visible | Fix recorder, don't hide behind dashboard UI |
| G — Sponsor proof | Real Muse request executed, if entered as a Muse integration | Claim Meta tool only if real request/response works |

**Cut order:** external AWS face indexing → fancy dashboard → gesture extras → reversible consent → custom eyewear adapter. Keep selective blur, event log, saved processed video and honest attribution limitations.

### Demo script, ~90 seconds

1. Show 2 subjects, both visible; announce they are consenting volunteers in this controlled demo.
2. A explicitly objects on microphone. Show transcript, parsed intent and *association method* (don't hide manual confirmation if used).
3. A becomes blurred while B stays visible.
4. A leaves and returns; show the stored session identity and the blur state returning, or explicitly show a protected shield while matching.
5. Stop the recording. Open the **saved processed file**, not just the live preview.
6. Mention webcam in place of glasses, native integration not yet implemented, original file held in a developer-only comparison environment.

### Adversarial acceptance tests

- A says “blur me” while B is also visible; speaker-to-person attribution cannot silently pick B.
- A speaks from outside the frame; no visible person is arbitrarily assigned.
- B says “A gave permission” after A denied; A remains blurred.
- A says “don't unblur me”; no positive consent is inferred from the word `unblur`.
- A returns during poor face visibility; any temporary shield and potential leakage are explicitly measured.
- A and B swap positions; protection does not follow a bounding-box index.
- Lose internet during recording; vision + existing refusal states continue to function.
- Restart recording inside same session; A remains denied.
- Check *saved frames*, not just preview; report numerator/denominator of cases, latency and zero/positive exposure counts.

---

## 10. What would actually impress Meta and judges

**Not** “we used AWS + Gemini + Muse + five agents.”

**Yes:** an instantly understandable interaction and a privacy state that persists correctly across occlusion, movement and re-entry; strong engineering discipline; saved output proving real effects; clear test metrics; and intellectually honest failure-handling.

The business problem is trust in social capture. The buyer/beneficiary tension remains: bystanders benefit, while a wearer may see inconvenience. A product pilot would need tests with both groups and a reason manufacturers or event operators would invest in the experience. Similar privacy/anonymization ideas exist already; this demonstration's novelty is the complete *interaction-to-persistent-redaction* workflow, not inventing blurring itself.

**Product positioning:** “A real-time, person-specific refusal layer for shared wearable-camera recordings.” Avoid calling this a legally sufficient consent mechanism or guaranteed anonymity.

---

## 11. Final architecture decision

**Use for HackTX:**

- **Local CV:** OpenCV YuNet + SFace + simple tracker on Mac M3/M4.
- **Local protected encoder:** OpenCV + PyAV/FFmpeg.
- **Voice:** Meta Muse Voice Transcribe + Muse Spark if keys available; **or** Gemini live transcription + Gemini Flash classification if that is the available credential. Use an interface that makes this swappable.
- **Policy:** deterministic Python state machine, no autonomous agent privileges.
- **Session metadata:** in-memory + SQLite/JSONL. No persistent cloud facial enrollment.
- **UI:** React/Vite, FastAPI, WebSockets/MJPEG; localhost demonstration.
- **AWS:** optional small consented Rekognition comparison after core reliability, not the live per-frame path.

**Open questions you must explicitly label in the final pitch:** speaker-to-face association outside the controlled demo; exposure before objection; identity under severe occlusion; subject-verified unblurring; biometric-law compliance; raw-original custody; and actual Meta device-level enforcement.

---

## 12. Verified reference documentation (checked 24 October 2026)

- AWS `IndexFaces`: <https://docs.aws.amazon.com/rekognition/latest/APIReference/API_IndexFaces.html>
- AWS `SearchFacesByImage` (largest face): <https://docs.aws.amazon.com/rekognition/latest/dg/search-face-with-image-procedure.html>
- AWS face collections: <https://docs.aws.amazon.com/rekognition/latest/dg/collections.html>
- AWS image pricing and free tier: <https://aws.amazon.com/rekognition/pricing/>
- AWS streaming Rekognition availability warning: <https://docs.aws.amazon.com/rekognition/latest/dg/streaming-video.html>
- OpenCV YuNet + SFace: <https://docs.opencv.org/4.x/d0/dd4/tutorial_dnn_face.html>
- Meta Wearables SDK capability boundary: <https://developers.meta.com/wearables/faq/>
- Meta Model API/Muse Voice: <https://dev.meta.ai/docs/overview> and <https://dev.meta.ai/docs/speech-to-text>
- Gemini Live transcription: <https://ai.google.dev/gemini-api/docs/live-api/live-transcribe>
- Gemini structured outputs: <https://ai.google.dev/gemini-api/docs/structured-output>
- Texas biometric identifier law overview: <https://www.oag.state.tx.us/consumer-protection/file-consumer-complaint/consumer-privacy-rights/biometric-identifier-act>

*Documentation describes supported services; account access, live performance and product-law applicability require independent verification. This plan intentionally contains no invented benchmark results or claims of actual Meta glasses integration.*
