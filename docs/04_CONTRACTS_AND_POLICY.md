# 04 — Shared contracts, authority and state machine

This is the **primary merge contract**; decide before separate code changes. Generated TypeScript types should mirror Pydantic schemas or a tracked JSON schema (choose one and test consistency). One session owns one namespace. `track_id` is ephemeral, `person_id` stable only for this session; never use a `FaceId` returned by a detector array as identity.

## Python data contracts (specification; implement concretely)

```python
@dataclass(frozen=True)
class FramePacket:
    session_id: str
    frame_id: int
    t_ms: int              # monotonic clock, session-relative
    bgr: np.ndarray       # uint8 H x W x 3, unmirrored, treated immutable

@dataclass(frozen=True)
class SpeechTurn:
    session_id: str
    turn_id: str
    start_ms: int
    end_ms: int
    text: str
    is_final: bool
    audio_speaker_label: str | None = None  # NOT a visual ID

class Intent(str, Enum):
    DENY = 'DENY'
    ALLOW = 'ALLOW'
    NO_REQUEST = 'NO_REQUEST'
    UNCLEAR = 'UNCLEAR'

class SpeakerRef(str, Enum):
    SELF = 'SELF'
    OTHER = 'OTHER'
    UNKNOWN = 'UNKNOWN'

@dataclass(frozen=True)
class ConsentInterpretation:
    turn_id: str
    intent: Intent
    speaker_ref: SpeakerRef
    needs_clarification: bool
    reason_short: str          # diagnostic only; not evidence of reliability

@dataclass(frozen=True)
class SpeakerMatch:
    turn_id: str
    person_id: str | None
    method: str              # e.g. lip_motion_heuristic / single_candidate / none
    evidence_score: float   # internally calibrated heuristic; NOT probability
    runner_up_margin: float
    status: str             # MATCHED / AMBIGUOUS / OFFSCREEN / UNKNOWN

@dataclass(frozen=True)
class PrivacyRequest:
    session_id: str
    event_id: str
    origin: str  # VOICE / GESTURE / MANUAL_TEST
    turn_id: str | None
    target_person_id: str | None
    action: str # PROTECT / REQUEST_ALLOW / UNRESOLVED
    observed_ms: int
    verified: bool

@dataclass(frozen=True)
class FrameResult:
    session_id: str
    frame_id: int
    t_ms: int
    protected_bgr: np.ndarray
    tracks: list[dict]
    events: list[dict]
    output_state: str  # NORMAL / REGION_SHIELDED / FULL_SHIELD / ERROR
    vision_ms: float
```

## Canonical subject record

```json
{
  "session_id": "s_demo_1",
  "person_id": "person_002",
  "motion_track_id": "track_57",
  "appearance": "VISIBLE",
  "privacy": "VISIBLE_NO_REQUEST",
  "identity_status": "MATCHED",
  "last_seen_ms": 14526,
  "embedding_gallery_size": 4
}
```

Don't publish embeddings, aligned facial crops, source pixels or subject descriptions as API metadata. `VISIBLE_NO_REQUEST` is **not** `CONSENT_GRANTED`. Persist refusal across stop/start of recording within session; default clear registry only at explicit session teardown, and note that reboot/reset defeats user protection in this prototype.

## State transitions

```text
NEW FACE -> IDENTITY_PENDING
  -> CONFIRMED_NEW => VISIBLE_NO_REQUEST
  -> MATCHED_PROTECTED => BLURRED_BY_REQUEST
  -> AMBIGUOUS_MATCH => TEMP_SHIELD

VISIBLE_NO_REQUEST --verified refusal for SAME person--> BLURRED_BY_REQUEST
BLURRED_BY_REQUEST --leave/reappear same session--> BLURRED_BY_REQUEST
BLURRED_BY_REQUEST --unverified 'allow'--> BLURRED_BY_REQUEST
BLURRED_BY_REQUEST --verified reauthorization (future, approved only)--> VISIBLE_AUTHORIZED

Unknown transcript/unknown speaker -> REQUEST_UNRESOLVED + shield/pause; do NOT assign a random face.
```

**Note:** Initial visible state is requested by owner and not equivalent to legal consent. `ALLOW` intent does not mean verified reauthorization; leave transition disabled for MVP. No wearer override, and no LLM database writes.

## Deterministic authorization function pseudocode

```python
def resolve_request(turn, parsed, matching, registry):
    if not turn.is_final or turn.session_id != registry.session_id:
        return NOOP
    if parsed.intent == 'NO_REQUEST': return NOOP
    if parsed.intent == 'UNCLEAR': return UNRESOLVED
    if parsed.intent == 'ALLOW':
        return REQUEST_SUBJECT_REAUTHORIZATION  # no unblur in MVP
    if parsed.intent == 'DENY':
        if parsed.speaker_ref != 'SELF': return UNRESOLVED
        if matching.status != 'MATCHED' or matching.person_id is None: return UNRESOLVED
        if matching.turn_id != turn.turn_id: return UNRESOLVED
        return PROTECT(matching.person_id)
```

Only the `VisionEngine.step` privacy registry commits PROTECT. Validate unique event IDs and timestamp window; late/duplicate transcript never overrides later events. Ensure protected decision applied to correct **frame** not current unrelated face after API lag.

## Event envelopes / REST

Event example:

```json
{
  "schema_version": 1,
  "session_id": "s_demo_1",
  "event_id": "event_91",
  "type": "PRIVACY_ACTIVATED",
  "t_ms": 16740,
  "person_id": "person_002",
  "source": "VOICE",
  "details": {"turn_id": "turn_03", "speaker_method": "lip_motion_heuristic"}
}
```

HTTP endpoints proposed:

| Endpoint | Contract |
| --- | --- |
| `GET /api/health` | camera/model/encoder/STT/LLM state and actual package versions (no secrets) |
| `POST /api/session/start` | create session only if idle; exactly one camera worker |
| `POST /api/session/end` | finalize recorders, clear session embeddings, report deletion |
| `POST /api/recording/start` | create paired demo outputs; don't reset privacy IDs |
| `POST /api/recording/stop` | finalize outputs; report playable status |
| `GET /api/state` | immutable snapshot of tracked people and metrics |
| `GET /api/preview/protected` | MJPEG **protected only** |
| `WS /api/events` | snapshots and event envelopes, include schema version |
| `GET /api/recordings/{opaque_id}/protected` | protected artifact, after closed |

**No unprotected original GET route** on publicly exposed server or default UI. For controlled developer comparison, make an explicit local developer-only path requiring opt-in env flag; never use raw path values from request IDs. On failures return safe errors, not raw image previews. No test-injection route enabled for judges.

## Timestamps and timing

`FramePacket.t_ms` and `SpeechTurn.start/end_ms` **must be comparable**. Record microphone and video capture monotonic offset at start; separate event arrival time from event capture time. Keep lip feature ring buffer longer than worst observed STT/LLM arrival delay or use bounded speech turn feature extraction. If late event cannot be resolved, show limitation and never blindly apply to current face. All clock conversions tested.

## Renderer policy

For every protected person, apply strong padded face/head pixel blur *in the saved frame*. If detection is missing but head track good, use head estimate; if confidence insufficient, shield relevant region or entire frame. On exception replace with shield/slate and emit event. Never encode source raw as fallback to protected video. Confirm no debug watermark or UI overlay is the sole redaction mechanism.
