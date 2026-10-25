"""Deterministic fixed-phrase interpreter. Runs before any LLM (no network).

Also runs on PARTIAL transcripts so explicit commands act ~1-2 s sooner.
Returns None when the phrase is not an explicit fixed command, so the caller
can ask the LLM. Emits only first-person DENY or first-person ALLOW.
"""
from __future__ import annotations

import re
from typing import Optional

from shared.contracts import ConsentInterpretation, Intent, SpeakerRef, SpeechTurn

# Checked first: negated unblur is a refusal ("please don't unblur me").
_DENY = [
    r"\b(do\s*n[o']?t|do\s+not|never)\s+unblur\s+(me|my\s+face)\b",
    r"\b(please\s+)?blur\s+(me|my\s+face)\b",
    r"\b(do\s*n[o']?t|do\s+not)\s+(record|film|show|tape)\s+(me|my\s+face)\b",
    r"\bi\s+(do\s*n[o']?t|do\s+not)\s+want\s+to\s+be\s+(in\s+(the|this)\s+(video|clip|recording)|filmed|recorded|shown)\b",
    r"\b(hide|cover)\s+my\s+face\b",
    r"\bkeep\s+me\s+blurred\b",
    r"\bi\s+(do\s*n[o']?t|do\s+not)\s+consent\b",
]
_ALLOW = [
    r"\bunblur\s+(me|my\s+face)\b",
    r"\b(you\s+can|it'?s\s+(ok|okay|fine)\s+to)\s+(film|record|show)\s+(me|my\s+face)\b",
    r"\bshow\s+my\s+face\b",
    r"\bi\s+(now\s+)?consent\b",
    r"\bi'?m\s+(ok|okay|fine)\s+(with\s+)?being\s+(filmed|recorded|shown)\b",
]
# Third person, injection, or anything not clearly about the speaker -> let the LLM decide.
_DEFER = [r"\b(he|she|they|him|her|them|his|their|my\s+friend|whoever|everyone|everybody|anyone)\b",
          r"\b(do\s*n[o']?t|do\s+not|no|stop)\s+(blur|blurring)\b",  # "don't blur me" is not a refusal
          r"\bignore\b", r"\b(not|don'?t)\s+(sure|know)\b", r"\bif\b", r"\?"]


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
                                         "explicit first-person refusal phrase", "local_rules")
    for p in _ALLOW:
        if re.search(p, text):
            return ConsentInterpretation(turn.turn_id, Intent.ALLOW, SpeakerRef.SELF, False,
                                         "explicit first-person consent phrase", "local_rules")
    return None
