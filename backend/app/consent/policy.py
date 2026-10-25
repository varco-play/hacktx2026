"""Deterministic authorization: turns interpretation + speaker evidence into a request.

The LLM never calls this with authority; it only supplies `ConsentInterpretation`.
"""
from __future__ import annotations

from typing import Optional

from shared.contracts import (ConsentInterpretation, Intent, PrivacyRequest,
                              RequestAction, RequestOrigin, SpeakerMatch,
                              SpeakerRef, SpeechTurn)


def resolve_request(turn: SpeechTurn, parsed: ConsentInterpretation,
                    match: Optional[SpeakerMatch], session_id: str,
                    event_id: str) -> Optional[PrivacyRequest]:
    """Return None for no-op. UNPROTECT only for the bound speaker's own ALLOW."""
    if not turn.is_final or turn.session_id != session_id:
        return None
    if parsed.turn_id != turn.turn_id:
        return None

    def req(action: RequestAction, target: Optional[str], verified: bool) -> PrivacyRequest:
        return PrivacyRequest(session_id=session_id, event_id=event_id,
                              origin=RequestOrigin.VOICE, turn_id=turn.turn_id,
                              target_person_id=target, action=action,
                              observed_ms=turn.end_ms, verified=verified)

    if parsed.intent == Intent.NO_REQUEST:
        return None
    if parsed.intent == Intent.UNCLEAR:
        # Unclear chatter is NOT a privacy request: no-op. (It used to shield everyone for 3 s,
        # which looked like "blurring out of nowhere" in live tests.) Only a clear refusal whose
        # speaker can't be identified triggers the temporary shield below.
        return None
    bound = (parsed.speaker_ref == SpeakerRef.SELF and match is not None and match.status == "MATCHED"
             and match.person_id is not None and match.turn_id == turn.turn_id)
    if parsed.intent == Intent.ALLOW:
        # Only the speaker's own consent, bound to their face by lip/visibility evidence.
        # Hearsay ("my friend says it's fine") is OTHER -> recorded, no effect.
        if bound:
            return req(RequestAction.UNPROTECT, match.person_id, True)
        return req(RequestAction.REQUEST_ALLOW, None, False)
    # DENY
    if parsed.speaker_ref != SpeakerRef.SELF:
        return req(RequestAction.UNRESOLVED, None, False)
    if match is None or match.status != "MATCHED" or match.person_id is None:
        return req(RequestAction.UNRESOLVED, None, False)
    if match.turn_id != turn.turn_id:
        return req(RequestAction.UNRESOLVED, None, False)
    return req(RequestAction.PROTECT, match.person_id, True)
