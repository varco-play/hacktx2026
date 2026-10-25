"""Deterministic fixed-phrase interpreter. Runs before any LLM (no network).

Returns None when the phrase is not one of the explicit fixed commands, so the
caller can ask the LLM. It only ever emits DENY/SELF for explicit first-person
refusals; it never emits ALLOW.
"""
from __future__ import annotations

import re
from typing import Optional

from shared.contracts import ConsentInterpretation, Intent, SpeakerRef, SpeechTurn

_DENY = [
    r"\b(please\s+)?blur\s+(me|my\s+face)\b",
    r"\bdon'?t\s+(record|film|show)\s+(me|my\s+face)\b",
    r"\bdo\s+not\s+(record|film|show)\s+(me|my\s+face)\b",
    r"\bi\s+(don'?t|do\s+not)\s+want\s+to\s+be\s+(in\s+(the|this)\s+(video|clip|recording)|filmed|recorded|shown)\b",
    r"\bhide\s+my\s+face\b",
    r"\bkeep\s+me\s+blurred\b",
    r"\bdon'?t\s+unblur\s+me\b",
]
# Phrases that must NOT be fast-pathed (third person, negated, reversal, injection)
_DEFER = [r"\b(he|she|they|him|her|them|my\s+friend|whoever|everyone|everybody)\b",
          r"\bunblur\b(?!\s+me\b)", r"\bignore\b", r"\b(okay|ok|fine)\s+with\b", r"\bcan\s+film\b"]


def interpret(turn: SpeechTurn) -> Optional[ConsentInterpretation]:
    text = turn.text.lower().strip()
    if not text:
        return ConsentInterpretation(turn.turn_id, Intent.NO_REQUEST, SpeakerRef.UNKNOWN, False,
                                     "empty transcript", "local_rules")
    if any(re.search(p, text) for p in _DEFER):
        return None
    for p in _DENY:
        if re.search(p, text):
            return ConsentInterpretation(turn.turn_id, Intent.DENY, SpeakerRef.SELF, False,
                                         "explicit first-person fixed phrase", "local_rules")
    return None
