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
_NOT = r"(do\s*n[o']?t|do\s+not|dont|never)"
_VERB = r"(record|film|show|tape|capture|shoot)"
_DENY = [
    rf"\b{_NOT}\s+un[\s-]?blur\s+(me|my\s+face)\b",
    # not when ASR splits "unblur" ("un blur me" / "on blur me" are consent, not refusal)
    r"(?<!\bun )(?<!\bun-)(?<!\bon )\b(please\s+)?blur\s+(me|my\s+face|my\s+identity)\b",
    rf"\b{_NOT}\s+{_VERB}\s+(me|my\s+face)\b",
    rf"\bno\s+{_VERB}(ing)?\s+me\b",
    rf"\b(you\s+)?(can'?t|cannot|can\s+not)\s+{_VERB}\s+(me|my\s+face)\b",
    r"\b(stop|quit)\s+(recording|filming|taping|shooting)\s+me\b",
    r"\bi\s+(do\s*n[o']?t|do\s+not|dont)\s+want\s+to\s+be\s+(in\s+(the|this|your)\s+(video|clip|recording|shot)|filmed|recorded|shown|on\s+camera)\b",
    r"\b(not|aint|ain't)\s+(trying|tryna)\s+(to\s+)?be\s+(on\s+camera|in\s+(the|this|your)\s+(video|clip|shot))\b",
    r"\b(get|take|keep)\s+me\s+out\s+of\s+(the|this|your)\s+(video|shot|frame|recording|clip)\b",
    r"\b(hide|cover)\s+(my\s+face|my\s+identity|me)\b",
    r"\bkeep\s+me\s+blurred\b",
    r"\bi\s+(do\s*n[o']?t|do\s+not|dont)\s+consent\b",
]
_PERMIT = (r"(you\s+can|you\s+could|go\s+ahead(\s+and)?|feel\s+free\s+to|"
           r"it'?s\s+(all\s+good|ok|okay|fine|cool)(\s+to)?|you'?re\s+(good|fine|ok|okay)\s+to)")
_TAIL = r"(\s+(now|again|then|bro|bruh|man|dude|it'?s\s+fine|it'?s\s+cool))*\s*[.!,]*\s*$"  # must END the sentence
_ALLOW = [
    r"\b(un[\s-]?blur|on\s+blur)\s+(me|my\s+face)\b",              # ASR sometimes splits "unblur"
    rf"\b{_PERMIT}\s+{_VERB}\s+(me|my\s+face)\b",                  # "go ahead and film me"
    rf"\b{_PERMIT}\s+(record|film){_TAIL}",                         # "yeah you can record." (nothing after)
    rf"^\W*(yeah|yes|yep|yup|sure|ok|okay|alright|bet|aight)?\W*(record|film)\s+me\b",   # "yeah, record me"
    r"\bshow\s+my\s+face\b",
    r"\bi\s+(now\s+)?consent\b",
    r"\b(i'?m|im|i\s+am)\s+(good|fine|ok|okay|cool|down)\s+(with\s+(it|that|being\s+(filmed|recorded|shown|on\s+camera))|"
    r"being\s+(filmed|recorded|shown|on\s+camera)|on\s+camera)\b",
]
# Never fast-path: third person, injection, "don't blur me" (not a refusal) -> LLM decides.
_DEFER = [r"\b(he|she|they|him|her|them|his|their|my\s+friend|whoever|everyone|everybody|anyone)\b",
          r"\b(do\s*n[o']?t|do\s+not|dont|no|stop)\s+(blur|blurring)\b",
          r"\bignore\b"]
# Consent must be unambiguous: questions / conditionals / doubt never fast-path an ALLOW.
# (A refusal phrased as a question — "can you blur me?" — is still honoured: blurring is safe.)
_DEFER_ALLOW = [r"\b(not|don'?t)\s+(sure|know)\b", r"\bif\b", r"\?", r"\bmaybe\b", r"\b(was|were|would)\b"]


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
    if any(re.search(p, text) for p in _DEFER_ALLOW):
        return None  # possible consent but hedged/conditional/question -> let the LLM judge
    for p in _ALLOW:
        if re.search(p, text):
            return ConsentInterpretation(turn.turn_id, Intent.ALLOW, SpeakerRef.SELF, False,
                                         "explicit first-person consent phrase", "local_rules")
    return None
