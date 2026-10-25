"""Shared ConsentLens contracts (spec: docs/04_CONTRACTS_AND_POLICY.md).

Change only with both teammates' agreement. `track_id` is ephemeral motion
identity; `person_id` is stable only within one session.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np

SCHEMA_VERSION = 1


class Intent(str, Enum):
    DENY = "DENY"
    ALLOW = "ALLOW"
    NO_REQUEST = "NO_REQUEST"
    UNCLEAR = "UNCLEAR"


class SpeakerRef(str, Enum):
    SELF = "SELF"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class Privacy(str, Enum):
    VISIBLE_NO_REQUEST = "VISIBLE_NO_REQUEST"  # NOT consent
    BLURRED_BY_REQUEST = "BLURRED_BY_REQUEST"  # latched for the session


class IdentityStatus(str, Enum):
    IDENTITY_PENDING = "IDENTITY_PENDING"
    CONFIRMED_NEW = "CONFIRMED_NEW"
    MATCHED = "MATCHED"
    AMBIGUOUS_MATCH = "AMBIGUOUS_MATCH"


class OutputState(str, Enum):
    NORMAL = "NORMAL"
    REGION_SHIELDED = "REGION_SHIELDED"
    FULL_SHIELD = "FULL_SHIELD"
    ERROR = "ERROR"


class RequestOrigin(str, Enum):
    VOICE = "VOICE"
    GESTURE = "GESTURE"
    MANUAL_TEST = "MANUAL_TEST"  # development only, must be labeled in UI


class RequestAction(str, Enum):
    PROTECT = "PROTECT"
    REQUEST_ALLOW = "REQUEST_ALLOW"  # recorded, never unblurs in MVP
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class FramePacket:
    session_id: str
    frame_id: int
    t_ms: int  # monotonic, session-relative
    bgr: np.ndarray  # uint8 HxWx3, unmirrored, treat as immutable


@dataclass(frozen=True)
class SpeechTurn:
    session_id: str
    turn_id: str
    start_ms: int
    end_ms: int
    text: str
    is_final: bool
    audio_speaker_label: Optional[str] = None  # NOT a visual ID


@dataclass(frozen=True)
class ConsentInterpretation:
    turn_id: str
    intent: Intent
    speaker_ref: SpeakerRef
    needs_clarification: bool
    reason_short: str  # diagnostic only
    source: str = "unknown"  # local_rules / muse_spark / gemini


@dataclass(frozen=True)
class SpeakerMatch:
    turn_id: str
    person_id: Optional[str]
    method: str  # lip_motion_heuristic / single_candidate / none
    evidence_score: float  # heuristic, NOT a probability
    runner_up_margin: float
    status: str  # MATCHED / AMBIGUOUS / OFFSCREEN / UNKNOWN


@dataclass(frozen=True)
class PrivacyRequest:
    session_id: str
    event_id: str
    origin: RequestOrigin
    turn_id: Optional[str]
    target_person_id: Optional[str]
    action: RequestAction
    observed_ms: int
    verified: bool


@dataclass(frozen=True)
class FrameResult:
    session_id: str
    frame_id: int
    t_ms: int
    protected_bgr: np.ndarray
    tracks: list = field(default_factory=list)
    events: list = field(default_factory=list)
    output_state: OutputState = OutputState.NORMAL
    vision_ms: float = 0.0


def event_envelope(session_id: str, event_id: str, type_: str, t_ms: int,
                   person_id: Optional[str] = None, source: Optional[str] = None,
                   details: Optional[dict] = None) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id,
        "event_id": event_id,
        "type": type_,
        "t_ms": t_ms,
        "person_id": person_id,
        "source": source,
        "details": details or {},
    }
