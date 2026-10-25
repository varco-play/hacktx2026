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
    """Return None for no-op. Never returns an unblur action."""
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
        return req(RequestAction.UNRESOLVED, None, False)
    if parsed.intent == Intent.ALLOW:
        # Recorded only. MVP has no verified reauthorization flow.
        return req(RequestAction.REQUEST_ALLOW, None, False)
    # DENY
    if parsed.speaker_ref != SpeakerRef.SELF:
        return req(RequestAction.UNRESOLVED, None, False)
    if match is None or match.status != "MATCHED" or match.person_id is None:
        return req(RequestAction.UNRESOLVED, None, False)
    if match.turn_id != turn.turn_id:
        return req(RequestAction.UNRESOLVED, None, False)
    return req(RequestAction.PROTECT, match.person_id, True)
