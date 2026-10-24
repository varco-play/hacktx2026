# ConsentLens — HackTX Team Implementation Plan

**Version:** 1.0 · 24 October 2026  
**Team:** Abbos + teammate  
**Target:** integrated demonstration in 4–5 hours; remaining time, up to the submission deadline, for reliability and presentation  
**Status:** implementation specification, not a claim that the prototype or integrations have already been built or benchmarked

## 1. The shared definition of the project

ConsentLens is a prototype of a **built-in privacy feature for wearable cameras**. A bystander covers their eyes to request that their face be blurred. The system recognizes the gesture, associates it with that person, and maintains live protection after their hands come down. If they leave and return during the session, the system attempts to restore the same identity and privacy state.

The recorder is potentially uncooperative. We are demonstrating a mechanism Meta could embed into its recording pipeline; we are not proposing that an abusive recorder voluntarily install a special recording app.

**One-line pitch:** “Cover your eyes. Keep your face out of the shared moment.”

**Track connection:** Meta asks for AI-powered social products that bring people closer together. Our hypothesis is that giving bystanders an understandable way to express boundaries can make camera-mediated social interaction more comfortable. Our prototype demonstrates the mechanism; it does not prove a measured increase in social trust.

### What the demo actually runs

A live laptop camera feeds a local Python privacy engine. A browser dashboard shows the protected output, tracking state, privacy events, and recording controls. This interface is an engineering demonstration of an embedded feature. It is not the proposed consumer product.

The default camera is the Mac webcam. The iPhone 12 Pro Max is optional as another camera source only after the main pipeline works. Actual Meta glasses are unavailable. Neither Swift nor a mock glasses application is on the initial critical path.

### What requires Meta integration later

Mandatory protection across the glasses' normal recording paths requires Meta to integrate the mechanism into a trusted camera/media pipeline. The public Device Access Toolkit provides application camera sessions; we have not verified a public API that forces our processing onto every native recording or prevents bypass. We must not claim that enforcement is implemented on stock Meta glasses. [Meta toolkit](https://developers.meta.com/wearables/device-access-toolkit/), [official camera sample](https://github.com/facebook/meta-wearables-dat-ios/blob/main/samples/CameraAccess/README.md).

## 2. Locked requirements and scope

| Requirement | Agreed behavior |
|---|---|
| Live processing | Detect, decide, blur, preview, and encode while capture is running. |
| Initial state | Visible people start unblurred. Absence of objection is not labeled consent. |
| Main trigger | One hand covering both eyes, or two hands jointly covering the eyes, deliberately held. |
| Persistence | Once activated, protection remains for that session; lowering hands does not undo it. |
| Multiple people | Blur the requester while leaving clearly unrelated people visible. Initial target: two people. |
| Return to frame | Match returning faces to the session gallery and restore protection where identification is sufficiently reliable. This is a priority feature. |
| Voice | Accessibility route into the same protection mechanism, using Meta's live transcription. |
| Two recordings | Preserve an untouched-input video and a protected video, both written during capture. |
| Recording completion | Stop flushes encoders and closes containers. No second blur pass, offline rendering, or editing step. |
| Session memory | Temporary anonymous person IDs and appearance features; no account enrollment or permanent identity database. |
| Evidence access | Out of scope. Two-copy storage is demonstrated without an authority-request workflow. |

### Submission priorities

**Core demonstration:** real camera, automatic gesture activation, persistent live face blur, original/protected recordings, honest status display.

**Priority differentiator:** leaving and returning with restored person ID and privacy state. Start this early, before visual polish; do not leave it until the final hour.

**Track integration:** real Muse Voice Transcribe request and response, plus Muse Spark interpreting natural-language privacy objections, if API access is available. Access must be checked in the first 20 minutes, not near submission.

**Optional after these work:** voice-to-face association with multiple visible people, iPhone camera, SAM experimentation, Muse connector, generated tutorial art.

This is a target scope, not a promise of general-purpose accuracy in five hours. If a feature is incomplete, label its boundary honestly rather than substituting a hidden manual trigger.

## 3. Hardware decision and AMD GPU findings

Available machines are a MacBook Air M3 and MacBook Air M4. Start on CPU using small pretrained models, measure performance, and choose the more reliable machine for the final demo. Keep both plugged in and test a continuous five-minute session for heat-related slowdown.

**Do not train a model from scratch.** Training is not the initial task. Abbos owns inference, tracking, gesture rules, calibration, and evaluation. Coding agents can accelerate implementation, but cannot replace measurement of occlusion, identity swaps, and timing.

### AMD program: useful, but not a dependency

AMD's AI Developer Program offers a cloud-credit route after verification. Its member resources currently describe $100 of Developer Cloud credits; the separate general Developer Cloud complimentary-access route has different conditions and may require a payment card. An education email alone is not a documented guarantee of immediate access. No approval deadline suitable for this hackathon was verified. [Member benefits](https://developer.amd.com/resources/), [claiming credits](https://www.amd.com/en/developer/resources/technical-articles/2026/how-to-claim-amd-cloud-credits.html), [cloud access conditions](https://www.amd.com/en/developer/resources/cloud-access.html).

If credits and a usable instance are already accessible, use them for an isolated experiment after the local baseline. Otherwise spend at most 10 minutes checking, then proceed locally. Do not enter a paid commitment as part of this plan.

A cloud GPU is not automatically faster for the end-to-end demo: upload, network delay, and runtime compatibility still matter. We have not verified our proposed model stack on AMD/ROCm. Do not assume CUDA-specific instructions work there.

## 4. Concrete stack

| Layer | Selected baseline | Owner |
|---|---|---|
| Vision runtime | Python 3.11, native Apple Silicon environment | Abbos |
| Capture/image operations | OpenCV | Abbos; teammate wires lifecycle |
| Face detection | OpenCV YuNet pretrained ONNX model | Abbos |
| Face re-identification | OpenCV SFace pretrained ONNX features | Abbos |
| Body/hand locations | MediaPipe Pose Landmarker Lite and Hand Landmarker | Abbos |
| Association | Motion/overlap matching plus face features; explicit ambiguity handling | Abbos |
| Privacy state | One in-memory registry owned by the vision engine | Abbos |
| Service | FastAPI, one process, one camera/vision worker | Teammate |
| Live preview | MJPEG of processed frames; WebSocket for metadata/events | Teammate backend, Abbos UI |
| Interface | React + Vite + TypeScript; minimal CSS | Abbos |
| Video recording | PyAV/FFmpeg encoders, same source timestamps for both outputs | Teammate |
| Audio capture | Laptop microphone through Python sounddevice | Teammate |
| Transcription | Muse Voice Transcribe realtime WebSocket | Teammate |
| Voice intent | Muse Spark structured classification, off the frame-processing path | Teammate |
| Local artifacts | Session directory with two videos, events, metadata | Teammate |

OpenCV documents pretrained face detection and recognition models and alignment/feature comparison. These are candidate components, not a claim that our return-to-frame pipeline is already reliable. [OpenCV face tutorial](https://docs.opencv.org/4.x/d0/dd4/tutorial_dnn_face.html).

MediaPipe provides Python hand and pose landmark tasks with video/live-stream modes. Set multiple poses explicitly; the pose default is one. Hand/body landmarks are locations, not persistent identities. [Hands](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/python), [Pose](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker/python).

### Installation decisions

- Use a project virtual environment and lock working dependency versions after the first smoke test on both Macs.
- Avoid installing competing OpenCV packages into the same environment. Resolve MediaPipe's OpenCV dependency, then confirm `FaceDetectorYN` and `FaceRecognizerSF` are available.
- Download models once from the official model repositories; record filenames, sources, licenses, and checksums. Confirm downloaded files are model binaries, not Git LFS pointer text.
- Use pretrained models and parameter calibration first. Do not add PyTorch, CUDA, a training framework, or a large segmentation model unless a measured gap justifies it.
- Do not spend the initial build learning Swift, porting models to iOS, or making a custom C++ extension. These do not improve the first live demonstration enough to justify their integration cost.

## 5. One architecture, one machine, one source of state

```text
Mac camera
   │
   ▼
Capture adapter → FramePacket(frame_id, monotonic timestamp, BGR image)
   │
   ▼
Single vision worker
   ├─ face detection + body/hand observations
   ├─ tracking + session identity gallery
   ├─ gesture detection
   ├─ apply queued privacy commands
   ├─ persistent protection registry
   └─ blur / ambiguity shield
   │
   ▼
FrameResult(raw image, protected image, tracks, events, timing)
   ├─ original encoder → original.mp4
   ├─ protected encoder → protected.mp4
   ├─ protected MJPEG preview → React dashboard
   └─ metadata WebSocket → tracks, events, metrics

Laptop microphone → Muse Voice Transcribe → fast command / Muse Spark
   → resolved privacy request → command queue → SAME vision worker
```

### Invariants both teammates must preserve

1. Exactly one component opens the camera. The browser does not open a second webcam feed.
2. Exactly one engine owns persistent person IDs and privacy states. The frontend and backend do not invent parallel person registries.
3. The protected file encodes the same protected pixels used by the preview, before optional debug annotations. A CSS overlay is not protection.
4. Raw frames are immutable input. Rendering creates a separate image; otherwise the original can accidentally become blurred too.
5. Network calls never block the vision worker. Voice requests enter a queue and take effect on a subsequent frame.
6. A session's protection state is monotonic: `UNBLURRED → BLURRED`. There is no gesture toggle or recorder-facing “unblur person” control.
7. A second recording in the same session retains protection. “Stop recording” is not “forget everybody.”
8. A new session clears the gallery; that is a labeled test-harness action, not a claimed bypass-resistant product behavior.
9. Both developers integrate on the same machine before the demo. Laptop-to-laptop streaming is not part of the baseline.

## 6. Vision pipeline and gesture activation

### 6.1 Frame and coordinate handling

Start at 640×480 with a goal of 15 processed frames per second for two people. Raise resolution only after meeting the acceptance tests. These are engineering targets, not measured performance claims.

Run the engine on unmirrored frames. All model outputs are converted into one pixel coordinate system before association. Mirroring is a display-only option. Normalize boxes to `[x, y, width, height]` in `[0,1]` only at the API boundary. Do not mix corner coordinates with width/height boxes.

### 6.2 Detect before the face becomes covered

When a clear face appears, associate it with a body track and obtain several good face features over time. This establishes a session ID before the eye-cover gesture hides the eyes.

Use head position, shoulders, wrists, and recent movement to maintain the association during the gesture. If eye landmarks disappear, use the recent reliable eye region transformed with the tracked head, rather than immediately deleting the person. Do not trust a new face feature extracted from a heavily covered face.

If a person enters already covering their eyes, protect the candidate head region while identification is pending. Establish the face identity after the hands come down without revealing their face in the protected output. Do not pretend this edge case is solved until demonstrated.

### 6.3 Gesture definition

Accepted patterns:

- One open hand spans both estimated eye regions.
- Two hands jointly cover the left and right eye regions of the same person.

Starting parameters to tune:

| Parameter | Initial value | Purpose |
|---|---|---|
| Deliberate hold | 0.8 seconds | Reject brief contact |
| Short landmark dropout allowance | 0.15 seconds | Avoid resetting for one missed observation |
| Maximum stale head anchor | 0.25 seconds | Avoid applying a gesture to a person who moved elsewhere |
| Candidate progress | elapsed valid time / hold time | Visible confirmation of the interaction |

Use real elapsed time, not a fixed count of frames. Require both eye regions to be covered, hand scale plausibly comparable to the face, and low enough relative movement for a deliberate cover. Estimate a palm area from landmarks rather than testing whether a single fingertip is close to an eye.

Associate each hand with a person's wrist/body geometry where possible. Proximity to a face alone can assign a neighbor's hand to the wrong person. If association is ambiguous, do not commit a confident identity-specific request.

### 6.4 Eye rubbing and hair adjustment

The intended distinction is bilateral eye coverage plus a deliberate hold, not simply “a hand near the face.”

- One-eye rubbing normally fails the two-eye coverage condition.
- Hair adjustment normally lies above the eye region.
- Nose scratching normally lies below/between the regions.
- A quick face touch normally fails the duration condition.

Someone rubbing both eyes for long enough can look identical to the chosen gesture. This ambiguity cannot be eliminated by a promise or a threshold. Test it; if it remains common, tighten the documented gesture to a steady cover or a specific palm orientation, and agree on that change together. Do not silently implement a different interaction.

### 6.5 State machine

Keep privacy preference separate from gesture progress and track visibility:

```text
Gesture: IDLE → COVER_CANDIDATE → CONFIRMED → IDLE
Privacy: UNBLURRED → BLURRED (latched until session reset)
Visibility: VISIBLE ↔ OCCLUDED ↔ OUT_OF_FRAME
Identity: KNOWN / PENDING / AMBIGUOUS
```

The gesture returns to idle after release; the privacy preference stays blurred. A temporary ambiguity shield is separate from the person's stored preference, so conservative handling does not accidentally grant another person a permanent blur state.

### 6.6 Rendering

Blur the full face/head region with padding rather than only the eyes. For an initial implementation, use an enlarged head box and strong blur/pixelation. Inspect the saved output at full size; a small decorative blur is insufficient.

When a protected person's face detector fails but their body/head track remains reliable, use the estimated head region. If the head cannot be located reliably, shield the possible regions or the full protected output until tracking recovers. Do not keep reusing a stale box while their face moves outside it.

The feature conceals faces; it does not guarantee anonymity from voices, clothes, tattoos, or context. We do not promise voice anonymization.

## 7. Leaving and returning: priority implementation

Use **face-based session re-identification**, not color matching alone. We do not need a person's name or enrollment account.

For each stable person ID, retain a small gallery of normalized face feature vectors from clear, unoccluded observations. Associate new detections using spatial continuity first, supported by appearance consistency. When a new face cannot be explained by a current track, compare its features with the existing session gallery before issuing a new persistent ID.

### Matching requirements

1. Start with 3–5 clear feature samples per person where available; cap the gallery size.
2. Align the face as expected by the face recognizer before extracting a feature.
3. Select a match only if its similarity passes a calibrated threshold **and** has a useful margin over the next candidate.
4. Require repeat agreement across several observations for identity confirmation; do not flicker between IDs on every frame.
5. Respect one-to-one assignment: two visible faces cannot simultaneously become the same person ID.
6. Keep gallery records for the whole active session, even when a person's short-lived motion track expires.
7. Update a gallery only from high-quality observations with reliable identity. No updates during coverage, uncertain association, or a crossing that might swap people.
8. Fetch the stored blur preference before rendering the newly matched face.

The example similarity thresholds in a model tutorial are starting references, not validated thresholds for this camera and demo. Calibrate with both teammates, different distances, and a few turning/returning examples. Save the selected thresholds and their observed errors in the evaluation log.

### Protection while matching

A reappearing face can be briefly shielded while the system resolves whether it belongs to an opted-out person. This is a temporary uncertainty treatment, not default permanent blurring of everybody. Start unblurred for resolved new people; preserve the saved preference for resolved returning people.

If there is a plausible protected candidate but no reliable match, keep the candidate shielded or pause the protected output. Show `Identity uncertain`. Do not silently assign a new unblurred ID simply because recognition failed. The prototype cannot guarantee it will detect every failed match; measure re-entry leakage explicitly.

### Planned demonstration conditions

Two people, adequate front lighting, clear initial face views, a stationary camera, short exits, and returning faces visible enough to compare. Test returning on the opposite side, changed order, and crossing. Do not claim robust recognition across sessions, large crowds, identical-looking people, severe motion blur, or major appearance changes.

### Re-entry success means

The same session ID is restored, the stored preference is restored, unrelated people remain visible, and no identifiable returning-face frame escapes into the protected recording during matching. Record successful restores separately from conservative full-frame shields.

## 8. Meta integrations with real responsibilities

The track screenshot encourages Meta tools; it does not state that every listed service must be used. Our aim is substantive integration, not a collection of unrelated API calls.

| Tool | Planned use | Submission status we can claim |
|---|---|---|
| Muse Voice Transcribe | Live accessibility phrase transcription | Integrated only after a real microphone-to-API-to-privacy event succeeds |
| Muse Spark | Classify natural-language objections and extract an explicit target description | Integrated only after a real API response drives a validated privacy request |
| Wearables Toolkit | Future camera adapter / integration design | Proposed or simulated until actual SDK execution is demonstrated |
| SAM | Optional tracking/segmentation experiment | Experimental unless it runs in the actual live path |
| Muse Image | Optional instructional asset showing the gesture | Supporting asset generation, not privacy-engine intelligence |
| Muse connector | Optional read-only access to live session summaries | Integration only if the connector is actually registered and exercised |
| Facebook Graph API | No initial dependency | Not used unless a concrete authorized sharing flow is built |

### 8.1 Live transcription

Use the laptop microphone, with a single application audio owner. Send live chunks to Muse Voice Transcribe using its realtime endpoint. Use the documented audio format and handshake; an endpoint existing in the documentation does not guarantee the team's key has access.

Meta documents turn detection, partial transcripts, and optional speaker labels. It recommends `ENDPOINTING` rather than diarization for low-latency commands. Audio labels such as A/B do not identify faces. Do not fabricate a confidence field: the documentation says transcription confidence scores are not available. [Muse Voice documentation](https://dev.meta.ai/docs/speech-to-text).

Map server audio offsets to the local session clock. A request must be associated with people visible during the utterance, not whichever person happens to be visible several seconds later. Deduplicate partial/final transcripts using the utterance/turn ID.

### 8.2 Voice intent without blocking gesture protection

Support direct phrases such as “Blur me,” “Don't record my face,” and “Please hide my face.” A small deterministic route recognizes the fixed “Blur me” command. Muse Spark handles variations and explicit descriptions such as “Please blur the person in the red shirt.”

Spark's allowed output is a validated structure:

```json
{
  "intent": "REQUEST_FACE_PRIVACY",
  "target_kind": "SELF",
  "target_description": null,
  "needs_clarification": false
}
```

Allowed intents: `REQUEST_FACE_PRIVACY`, `NO_REQUEST`, `UNCERTAIN`. Allowed target kinds: `SELF`, `DESCRIPTION`, `UNKNOWN`. A self-reported model score is not a calibrated reliability guarantee.

The model receives transcript text and the minimum necessary track descriptions, not raw video or face embeddings. The baseline has no color-description resolver; until one exists, descriptive targets request clarification. The model cannot unblur, reset the session, retrieve the original, or issue arbitrary application actions. Invalid output or a timeout becomes `UNCERTAIN`.

Muse Spark is available through Meta Model API according to Meta's current documentation. Verify the actual model ID and account access during setup rather than hard-coding an untested assumption. [Meta Model API](https://dev.meta.ai/docs/overview).

### 8.3 Speaker association: deliberately small scope

For the first working accessibility demonstration, support one visible bystander during an explicit spoken privacy request. Resolve that request to the single tracked bystander, with the stated assumption that the request is coming from them. This assumption is not proof of speaker identity, and the interface must not claim otherwise.

If multiple people are visible or the speaker might be outside the frame, protect/pause the output and ask for clarification. This gives a working voice route without training an active-speaker model.

If time remains, add mouth-motion evidence over the utterance interval. Treat it as an experimental heuristic: mouth motion can come from chewing, silent speech, or a different conversation. Do not market it as reliable voice-face matching. A proper audiovisual speaker model is later work unless integrated and tested within the remaining time.

The voice path does not require people to use their hands to confirm. An unresolved request can leave the protected stream shielded; raw recording continues because preserving an original is an explicit project requirement.

### 8.4 API-access contingency

In the first 20 minutes, teammate must test an actual transcription request and an actual Spark request with the hackathon credentials or a self-service key. Do not send the key to the frontend, commit it, or include it in debug screenshots.

If access fails, continue building gestures locally and mark the Meta path unavailable. A manual transcript injector is acceptable for integration development only, labeled `TEST INPUT`; it is not evidence of Muse integration. Ask sponsor mentors for the event-specific access route while independent work continues. Never substitute another provider and label it Muse.

### 8.5 Why SAM is not on the initial critical path

Meta SAM is relevant to segmentation and tracking, but it does not supply the full eye-cover interaction, identity registry, or recording policy. The hosted API's streaming responses for a submitted clip should not be confused with support for an endless low-latency camera input. Public real-time benchmarks also depend on specific hardware. [SAM API](https://dev.meta.ai/docs/sam/overview), [Meta performance discussion](https://ai.meta.com/blog/segment-anything-model-3/).

Only add it if the baseline is stable and a short benchmark demonstrates a concrete improvement. An optional model experiment must feed the same `VisionObservation`/`FrameResult` interfaces, not create a second demo.

## 9. Recording, latency, and failure behavior

### 9.1 Two copies, continuously written

For each accepted source frame, preserve an untouched input image and produce a protected image. Use matching timestamps. Encode both while capture runs. “Original” means the unblurred camera input received by the prototype, not bit-identical access to a future glasses sensor master.

Stop finalizes the existing streams; it does not reprocess the video. The files should be playable within a few seconds of stopping, subject to normal container closure. PyAV exposes frame timestamps and time bases; use them rather than assuming inference always runs at a constant frame rate. [PyAV timing](https://pyav.org/docs/stable/api/time.html).

The first delivery is **two video-only files**. Microphone audio is used live for voice commands; embedding audio into both files is an optional later enhancement. No one should independently add a post-recording audio mux step and thereby violate the agreed live pipeline.

### 9.2 Processing schedule

Use a dedicated capture/vision worker outside FastAPI's async request loop. A bounded latest-frame queue prevents an ever-growing delay. Start with synchronous model inference within that worker; synchronous processing of each newly arriving frame is still a live pipeline. It is simpler to align results than multiple asynchronous callbacks.

If optimizing with asynchronous inference later, attach frame IDs/timestamps to every result. Never use a result from an unrelated old frame to decide which current person to blur.

For overload, the worker can skip source frames before admission. The first version writes both outputs from the same admitted frame sequence, preserving timestamps. Report drops; do not claim a full-frame-rate original. If a full-rate raw recorder is added later, its timing relationship must be tested explicitly.

A small bounded delay during capture is permitted. No prerecorded substitution, offline pass, or unbounded buffering is permitted in a live claim.

### 9.3 Conservative output rules

| Situation | Protected output | Original output |
|---|---|---|
| Known unblurred person, no request | Normal | Normal |
| Confirmed gesture | Blur their face/head | Normal |
| Protected person lowers hands | Continue blur | Normal |
| Protected person turns; head remains located | Expand protection to estimated head | Normal |
| Plausible returning protected identity pending | Temporary candidate/head shield | Normal |
| Multiple plausible matches / lost location | Shield relevant regions or full frame | Normal |
| Unresolved voice objection | Shield full frame and show clarification state | Normal |
| Vision exception or stale protection result | Slate/full-frame shield; never raw fallback | Continue only if capture/encoder is healthy |
| Encoder error or disk full | Stop recording and report failure | Stop paired recording; do not claim both files succeeded |

Raw originals remain accessible to developers in this test harness. That is not a deployed evidence-security system. Label original playback as `Developer diagnostic — unprotected original`. Default dashboard preview and default download select the protected video.

### 9.4 Target measurements

Measure separately:

- **Capture-to-protected-preview age:** target p95 below 300 ms at 640×480, two people.
- **Gesture hold:** initial 800 ms design requirement, not inference delay.
- **Activation after hold completion:** target p95 below 300 ms.
- **Processed throughput:** initial goal at least 15 FPS; report sustained actual value.
- **Voice response:** show observed time from utterance completion to protection; no invented target achievement.
- **Protection leaks:** count identifiable protected-face frames after activation and during re-entry; target zero in the rehearsed scenario.

An MJPEG preview FPS figure alone is not latency. Log timestamps at capture, decision, render, and preview receipt where available. If the browser cannot reliably measure display time, report the instrumented boundary instead of calling it end-to-end latency.

## 10. Shared interfaces — agree before independent implementation

### Internal types

```python
# shared/contracts.py — names and meanings are locked jointly

FramePacket:
    frame_id: int
    timestamp_ms: int             # monotonic, session-relative
    bgr: ndarray                 # uint8 H×W×3, unmirrored

PrivacyRequest:
    request_id: str
    session_id: str
    source: "gesture" | "voice" | "test"
    person_id: str | None
    requested_at_ms: int
    action: "PROTECT_PERSON" | "SHIELD_UNRESOLVED"

FrameResult:
    frame_id: int
    timestamp_ms: int
    protected_bgr: ndarray       # independent image; input not mutated
    tracks: list[TrackView]
    events: list[PrivacyEvent]
    output_state: "NORMAL" | "SHIELDED" | "ERROR"
    inference_ms: float

VisionEngine:
    step(packet: FramePacket, requests: list[PrivacyRequest]) -> FrameResult
    reset(session_id: str) -> None
    close() -> None
```

Backend retains the packet's raw frame for the original recorder; the engine returns the protected frame. `step` runs on one worker and is the only place that mutates the identity/privacy registry. Requests from other threads are queued, not applied concurrently. Old-session voice results are rejected after reset.

### Public track snapshot

```json
{
  "person_id": "p_002",
  "privacy": "BLURRED",
  "visibility": "VISIBLE",
  "identity_status": "KNOWN",
  "face_box": [0.42, 0.18, 0.14, 0.22],
  "gesture_progress": 0.0,
  "protection_source": "gesture",
  "last_seen_ms": 9320
}
```

Do not expose embeddings or raw face crops in metadata. Stable `person_id` is separate from temporary motion `track_id`; never use a detector's array index as a persistent ID. Public snapshots can include recently absent protected people with `visibility: OUT_OF_FRAME` so judges see persistence.

### Event example

```json
{
  "schema_version": 1,
  "event_id": "e_015",
  "session_id": "s_demo_01",
  "type": "PERSON_REIDENTIFIED",
  "timestamp_ms": 14320,
  "person_id": "p_002",
  "source": "vision",
  "details": {"restored_privacy": "BLURRED"}
}
```

Event types: `PERSON_SEEN`, `GESTURE_STARTED`, `GESTURE_CANCELLED`, `PROTECTION_ACTIVATED`, `PERSON_LEFT`, `PERSON_REIDENTIFIED`, `IDENTITY_UNCERTAIN`, `VOICE_REQUEST`, `OUTPUT_SHIELDED`, `OUTPUT_RESUMED`, `RECORDING_STARTED`, `RECORDING_STOPPED`, `ERROR`.

### API contract

| Route | Behavior |
|---|---|
| `GET /api/health` | Engine, model, camera, microphone, encoder, Meta connection status |
| `GET /api/state` | Latest immutable session/track snapshot and metrics |
| `POST /api/session/start` | Create a new session only when idle; initialize registry and camera lifecycle |
| `POST /api/recording/start` | Begin paired writers inside active session; duplicate start is rejected |
| `POST /api/recording/stop` | Finalize paired writers; return artifact status, not an offline job ID |
| `POST /api/session/end` | Stop capture, finalize writers, clear in-memory gallery |
| `GET /api/preview/protected` | Processed MJPEG stream; reconnecting must not reopen the camera |
| `WS /api/events` | Snapshots, privacy events, metrics; include schema version/session ID |
| `GET /api/recordings/{recording_id}/protected` | Protected file after finalization |
| `GET /api/recordings/{recording_id}/original` | Developer-only diagnostic route, visibly labeled in local demo |

Do not add public routes that accept arbitrary file paths. Artifact IDs map to files inside the session directory. Add any development-only injection endpoint behind an explicit test flag; it must be absent or clearly disabled in the judging run.

Run locally. Use a Vite proxy to FastAPI during development; serve the built frontend from FastAPI for the rehearsed demo if convenient. No login, accounts, cloud database, or public hosting is needed.

## 11. Repository structure and ownership

```text
consentlens/
├── README.md                         # setup, one demo command, current known limits
├── TEAM_PLAN.md                      # this specification, shared source of truth
├── DECISIONS.md                      # short jointly agreed deviations
├── .env.example                      # variable names only; never credentials
├── .gitignore
├── requirements.lock                 # working Python environment
├── models/
│   └── MANIFEST.md                   # model URLs, versions, checksums, licenses
├── shared/
│   └── contracts.py                  # teammate scaffolds; both approve changes
├── vision/                           # Abbos owns
│   ├── engine.py                     # public engine interface
│   ├── detectors.py                  # YuNet and MediaPipe wrappers
│   ├── association.py                # face/body/hand and frame-to-frame matching
│   ├── identity.py                   # SFace gallery and return matching
│   ├── gestures.py                   # temporal eye-cover rules
│   ├── registry.py                   # sole person/privacy state owner
│   └── rendering.py                  # blur and temporary uncertainty shields
├── backend/                          # teammate owns
│   ├── main.py                       # FastAPI setup and lifecycle
│   ├── runtime.py                    # one worker, queues, immutable snapshots
│   ├── capture.py                    # default OpenCV camera adapter
│   ├── recording.py                  # paired live encoders
│   ├── sessions.py                   # session lifecycle and artifact index
│   ├── api.py                        # REST, preview, events
│   ├── audio.py                      # microphone, clock mapping
│   └── meta/
│       ├── transcribe.py             # real Muse realtime client
│       ├── intent.py                 # Spark and fixed-command adapter
│       └── requests.py               # resolve/queue validated requests
├── frontend/                         # Abbos owns; teammate creates shell
│   └── src/
│       ├── App.tsx
│       ├── api.ts                    # shared service client and typed messages
│       └── components/
│           ├── ProtectedPreview.tsx
│           ├── PersonRegistry.tsx
│           ├── PrivacyTimeline.tsx
│           ├── RecordingPanel.tsx
│           └── IntegrationStatus.tsx
├── tests/
│   ├── test_privacy_state.py
│   ├── test_reidentification.py
│   ├── test_recording_pair.py
│   └── MANUAL_ACCEPTANCE.md
├── evaluation/
│   ├── trials.csv
│   └── results.md
└── recordings/                       # ignored; session outputs below
    └── s_<id>/
        ├── r_<id>_original.mp4
        ├── r_<id>_protected.mp4
        ├── events.jsonl
        └── metadata.json
```

Keep modules small enough to own independently; do not invent a separate service for each file. A single coherent process is sufficient. `recordings/` is the proposed application's runtime directory, not a request to create recordings now.

### Ownership boundaries

**Abbos:** vision, gesture behavior, tracking/re-identification, privacy registry, blur rendering, UI, camera-scene trials, final narrative.

**Teammate:** repository scaffold, dependency setup coordination, service lifecycle, capture adapter wiring, dual recordings, live preview/event transport, microphone/Meta clients, artifact handling, integration smoke tests.

**Jointly owned decisions:** contracts, model changes affecting outputs, gesture definition, uncertainty behavior, recording format, session lifetime, and submission scope.

Do not have both coding agents edit `shared/contracts.py`, `backend/runtime.py`, or the dependency lock simultaneously. The named owner makes the edit; the other consumes the change after a short checkpoint.

## 12. Five-hour execution schedule

Use T+ relative to starting implementation. The 10-hour deadline is a reserve, not a reason to postpone integration. Both teammates should see the same working system within the first hour.

| Time | Abbos | Teammate | Required joint checkpoint |
|---|---|---|---|
| 0:00–0:20 | Agree contracts, gesture, two-person scene; start model smoke test | Scaffold repo, environment, engine stub; test real Muse API access | Both can import shared contracts; keys/access status known |
| 0:20–1:00 | Faces + pose/hands → stable visible tracks; render one selected test blur | Camera worker, service, preview, recording start/stop; consume stub then real engine | Webcam pixels pass through real engine to dashboard and two files |
| 1:00–2:00 | Automatic eye-cover activation + persistence; start gallery/re-entry immediately | Finish paired encoder timing, event log, error handling; live transcription client | Hands lower, blur stays; protected file contains actual modified pixels |
| 2:00–3:00 | Prioritize leave/return tests; resolve ID swaps; build basic registry/timeline UI | Spark intent, single-visible-person voice scope, command queue, Meta status UI payloads | Same protected ID returns; real voice request reaches same registry |
| 3:00–4:00 | Negative gesture trials; boundary padding; crossings; frontend polish | Test stop/playback, duration, reconnects, API failures, disk errors; metrics | Full live demonstration on one machine without manual privacy intervention |
| 4:00–5:00 | Rehearse narrative, judge demo, visual clarity; review final recordings | Fix only blocking defects; document setup, actual metrics and Meta evidence | Feature freeze, runnable handoff, backup recording, submission material |

### First-hour integration rule

It is acceptable to test a manually selected blur in the first hour to validate data flow. It must be labeled a development test. It is not the completed gesture feature. Replace the stub and test trigger as soon as automatic activation is available.

By T+1:00, the same source frame must flow through both owners' work. If that has not happened, stop independent feature work and fix integration together.

### Remaining time up to deadline

Use extra time in this order:

1. Fix actual protected-face leakage and wrong-ID behavior.
2. Improve leaving/returning and crossing robustness.
3. Improve false gesture activation and multi-person voice handling.
4. Increase sustained performance or improve camera quality.
5. Add a genuine, low-cost extra Meta integration only if earlier items are stable.

Do not start Swift, a new model family, or cloud deployment in the last hour. Freeze feature changes at least 45 minutes before submission so both teammates can rehearse and complete materials.

## 13. Integration rules that prevent two separate projects

1. One repository and one shared plan. Do not create an alternate “better architecture” repo during the event.
2. One executable end-to-end path, one frame contract, one person ID namespace, one privacy registry.
3. Every 30–45 minutes, run together from camera input to protected output. Do not substitute a screenshot of a standalone module.
4. Backend work is not complete when an endpoint exists; it is complete when the vision engine and frontend use it.
5. Vision work is not complete when an OpenCV debug window works; it is complete when its protected pixels reach the preview and recorder.
6. Frontend mock data must match the shared schema and be visibly labeled. Disable it in the judging path.
7. A contract change gets a brief note in `DECISIONS.md`, and both consumers are updated before further features.
8. Merge small working changes. Keep model downloads, large binaries, videos, and credentials outside normal source commits as appropriate.
9. If either teammate is blocked for more than 15 minutes, surface the blocker and integrate an existing component instead of silently starting a workaround project.
10. All extra features enter the existing pipeline. No separate image-upload privacy app, chatbot demo, or offline video editor.

## 14. UI specification

Use one main screen, with live protected video as the visual focus.

### Main elements

- Heading: **ConsentLens**.
- Subtitle: **Live bystander privacy — prototype for camera integration**.
- Primary live view: protected frames.
- Instruction: **Cover both eyes and hold briefly to hide your face. Or say “Blur me.”**
- Person cards: stable ID, visible/absent, unblurred/blurred, identity pending where relevant.
- Gesture progress near the tracked person, so detection is visibly automatic.
- Event timeline: request detected, protection activated, person left, identity restored.
- Recording controls: begin/end paired recording; clearly separate session end/reset.
- Indicators: sustained processed FPS, processing age, recording status, dropped frames, Meta connectivity.
- After recording: protected playback/download; separate labeled developer original comparison.

Do not expose an “unblur Person 02” button. Development inspection can reveal originals, but ordinary demo controls should not imply the deployed recorder gets to override the request.

An unresolved request shows **Privacy request detected — identity uncertain; protected output paused**. It should not silently clear because the speaker stops talking. Resume normal protected output only after resolving the request while retaining all prior protection states. A manual development recovery/reset, if needed, must be labeled as such rather than presented as automatic resolution.

Original and protected side-by-side views are valuable in the final artifact comparison, but keep the live original hidden by default. Make it obvious that the comparison is a developer diagnostic.

## 15. Acceptance tests and measurement sheet

### Required live trials

| Test | Procedure | Pass condition |
|---|---|---|
| Normal scene | Two people, no request | Both visible and unblurred |
| Two-hand gesture | One actor covers both eyes and holds | Only that actor becomes protected |
| One-hand gesture | One hand spans both eyes and holds | Same result if the configured variant is enabled |
| Release | Protected actor lowers hands and talks/moves | Protection remains latched |
| Neighbor | Other actor stays beside requester | No privacy-state transfer to neighbor |
| Eye rub | Rub one eye briefly | No activation |
| Hair/nose/glasses | Adjust hair, scratch nose, adjust glasses | No activation in recorded trials |
| Partial cover | Touch one side of face | No activation unless full accepted gesture condition holds |
| Turn/occlusion | Protected actor turns or partially hides | Head protected or conservative shield; no raw fallback |
| Leave/return | Exit 3–5 seconds, return on other side | Same ID and preference restored; no unprotected re-entry frames |
| Cross | Two actors exchange positions | No silent swap of privacy state |
| Simultaneous requests | Both actors perform accepted gesture | Both become protected independently |
| Paired recording | Stop and immediately open both videos | Original stays unblurred; protected contains live protection; durations sensible |
| Second recording | Stop/start within same session | Previously protected identity remains protected |
| Voice | Single visible actor says a request | Real Muse transcription leads to protection; assumption labeled |
| Voice ambiguity | Multiple candidates or unclear speaker | Output shielded; no invented face match |
| API outage | Disconnect transcription/model service | Gesture pipeline keeps working; voice unavailable is visible |
| UI reconnect | Refresh dashboard during session | Same session, camera worker, IDs and recordings continue |

For the negative gestures, collect at least 10 trials per gesture category across both teammates if time permits. For intended activation and re-entry, aim for 10 trials each. These are small local trials, not population-level accuracy claims.

### Record results, not just impressions

`trials.csv` columns:

```text
trial_id,test_type,actor,expected_person_id,observed_person_id,
activated,false_activation,reentry_restored,protected_face_leak_frames,
unrelated_person_wrongly_blurred,activation_ms,notes
```

For a re-entry trial, separately note whether the person was correctly recognized or merely hidden by a full-frame shield. Both avoid exposure in that trial, but only one demonstrates identity restoration.

Capture a short consented evaluation clip to inspect frames around activation and return. Replaying a test fixture through the engine is permitted for debugging; the judging live demonstration still uses a live camera. No test clip is a hidden substitute for live inference.

### Small automated checks worth writing

- Privacy latch survives track disappearance and reattachment.
- An old-session voice request cannot protect a newly reused ID in a new session.
- Two simultaneous detections cannot map to the same persistent identity.
- An uncertain candidate does not overwrite a known identity gallery.
- The original input array is unchanged after rendering.
- A vision failure cannot send the raw frame to the protected writer.
- Paired recorders finalize playable files with consistent timestamps and the intended differing pixels.

These tests protect meaningful integration and privacy behavior. Do not spend the event writing tests that merely repeat trivial getter/setter code.

## 16. Known risks and bounded fallback choices

| Risk | First response | What we do not claim |
|---|---|---|
| Hands hide face landmarks | Preserve body/head association and recent eye region | That face detection will always work under coverage |
| Hand landmarks disappear against face | Use wrist/body evidence and inspect actual scene; tune deliberately | That a generic hand detector understands consent |
| Eye rubbing resembles gesture | Bilateral steady hold; document residual ambiguity | Perfect intent inference |
| Return matching uncertain | Temporary shielding and explicit unresolved status | Guaranteed recognition in arbitrary environments |
| Local performance low | Lower input resolution, expensive-model frequency, and candidate count; remeasure | A fabricated FPS or zero latency |
| Mac dependency issue | Fix one supported environment first, then reproduce lock on second Mac | That identical-looking package installs are identical runtimes |
| Muse access missing | Seek sponsor credentials; keep core running; label unavailable path | A mocked integration as real |
| Cloud approval slow | Continue locally | That education accounts guarantee instant GPUs |
| Encoding setup slow | First make one timed paired recording work before UI polish | That a preview proves the files work |
| No glasses | Webcam stands in for camera source | A completed physical Meta integration |

If return matching is not dependable by T+3:00, keep improving it before optional integrations or UI flourishes. Use the remaining deadline reserve. If it is still incomplete at submission, demonstrate only supported conditions and state the limit; do not fake a restored ID.

## 17. Judges' demonstration and narrative

### Two-minute demonstration

1. **Problem, 15 seconds:** Wearable cameras can capture social moments while leaving bystanders little control over their faces appearing in footage.
2. **Normal capture, 10 seconds:** Show two visible people, no default blur.
3. **Bystander action, 20 seconds:** One actor covers their eyes. The progress indicator completes, their face becomes protected, and the other remains visible.
4. **Persistence, 10 seconds:** Hands come down. The protected actor keeps interacting and moving.
5. **Return, 20 seconds:** The actor leaves and returns on the opposite side. The same anonymous ID and blur state return. Show the event in the timeline.
6. **Accessibility, 20 seconds:** Use the supported single-visible-person voice scenario. Show real Muse transcript/intent and protection activation. Explain broader speaker matching is limited if it has not been built.
7. **Proof, 15 seconds:** Stop recording and play corresponding original/protected output. No editing or new processing job starts.
8. **Integration boundary, 10 seconds:** Webcam is the current input; mandatory deployment would embed the engine in Meta's trusted recording pipeline.

### Suggested pitch

> ConsentLens gives bystanders a way to express a boundary with one gesture: cover your eyes, and your face stays hidden in the protected video. Our prototype processes live camera frames, remembers the request when you leave and return, and uses Meta's voice tools for an accessible spoken alternative. We're demonstrating a camera capability Meta could integrate, so respecting the request does not depend on a recorder choosing a separate privacy app.

Use the voice sentence only if that integration actually works. Replace it with a precise limitation if access fails.

### Answers to likely questions

**“Why does this bring people closer together?”**  
The design allows a shared moment to continue while a person expresses a visibility boundary. It aims to reduce friction between capturing memories and respecting people nearby. We have built the interaction, not a social-outcomes study.

**“Can't the recorder just ignore it?”**  
Our prototype enforces it inside its own pipeline. Preventing bypass across a device requires integration by Meta; that is the deployment proposal, not an already-achieved capability of the public SDK.

**“Why are you keeping an original?”**  
The prototype demonstrates two simultaneous outputs, including potential evidence preservation. Restricting original access is separate future work. In this developer harness originals are inspectable; we are not claiming a secure evidence vault.

**“What is AI doing?”**  
Pretrained vision models locate faces, bodies, and hands; face features support session identity matching; temporal geometry turns observations into the explicit gesture interaction. Muse transcribes voice, and Spark interprets varied requests. Deterministic code stores the privacy decision and renders protection.

**“What did you build rather than download?”**  
The gesture-to-person association, persistent privacy registry, re-entry policy, ambiguity behavior, live rendering/dual-output integration, accessibility flow, interface, and measured demo. We use pretrained perception models rather than claiming to have trained foundation models.

## 18. Copyable teammate handoffs

Both coding agents should receive this entire plan and the actual repository context. Give each the role below. These are handoff instructions for the two human teammates' tools, not a request to start additional agents now.

### Abbos: vision and interface brief

```text
Implement the vision engine and frontend for ConsentLens according to TEAM_PLAN.md.
Own vision/ and frontend/. Do not redesign the backend or open a second camera.
Honor shared/contracts.py; propose contract changes before editing consumers.

First deliver a real FramePacket → FrameResult engine using pretrained detectors.
Then automatic eye-cover activation, persistent blur, session face gallery,
leave/return identity restoration, and conservative uncertainty behavior.
Integrate with backend/runtime.py within the first hour.

Use normal capture until an explicit request. Lowering hands never unblurs.
Never mutate the raw image. Never render a protected identity unblurred merely
because its face detector or temporary track disappears. Do not fake re-entry.

Frontend consumes the backend preview/events; it does not separately capture
or simulate vision. Prioritize two-person live behavior over visual polish.
No offline blur pass, training from scratch, Swift app, or cloud dependency.
Record measured limitations and coordinate every shared-schema change.
```

### Teammate: scaffold, backend, recordings, and Meta brief

```text
Implement the shared scaffold and backend for ConsentLens using TEAM_PLAN.md.
Own backend/, initial dependency setup, artifact handling, and integration tests.
Create shared/contracts.py early and agree it with Abbos before independent work.
Create the frontend shell but leave its feature implementation to Abbos.

One FastAPI process runs one camera/vision worker. Call VisionEngine.step;
the engine owns person IDs and privacy state. Do not build a second registry.
Deliver the real protected MJPEG feed, metadata WebSocket, paired live recordings,
and start/stop/session routes. Finalize files at stop; never run an offline blur job.

Check actual Muse Voice Transcribe and Spark access in the first 20 minutes.
Implement live transcription and validated voice requests through the same
engine command queue. Keep network calls outside the frame worker.
Label single-visible-person speaker assumptions and ambiguous voice behavior.
Keys stay backend-only. Mocked input is development-only and visibly labeled.

Integrate real camera → engine → preview → both videos within the first hour.
Do not build accounts, evidence-access workflows, Graph sharing, or a separate
chatbot. Discuss contract changes immediately instead of creating alternatives.
```

## 19. Final readiness checklist

- [ ] Both teammates can describe the exact same end-to-end project.
- [ ] One machine launches the complete demo using the documented instructions.
- [ ] Live gesture activation works without a hidden click or injected event.
- [ ] Protection persists after hands lower and recording restarts within a session.
- [ ] Leave/return behavior has measured results and honest limits.
- [ ] Protected output remains safe on ambiguous/lost tracking in tested scenarios.
- [ ] Two playable files are ready after normal recording finalization.
- [ ] Protected file contains modified pixels; original stays untouched.
- [ ] At least one intended Meta integration has been exercised, or unavailable access is clearly disclosed.
- [ ] Model/provider usage is attributed accurately; optional tools are not presented as completed work.
- [ ] Actual metrics and failed trials are recorded.
- [ ] The interface identifies the webcam as a stand-in for glasses.
- [ ] No claim of system-wide enforcement, guaranteed anonymity, or secure authority access appears in the submission.
- [ ] A short backup demonstration recording exists, visibly presented as backup if used.
- [ ] Final submission explains the social value, working contribution, and Meta integration path.

## 20. First action when coding starts

Spend 15–20 minutes together locking `shared/contracts.py`, testing model imports, verifying Meta API access, and assigning the files above. Then split work. The first milestone is not two impressive modules; it is one real camera frame passing through the shared engine into the protected preview and both recording paths.
