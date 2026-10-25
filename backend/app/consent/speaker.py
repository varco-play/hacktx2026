"""Bind a speech turn to a visible person. Conservative: ambiguity -> no target.

Current method: `single_candidate` — exactly one confirmed person visible for
most of the utterance window. With two or more visible people this returns
AMBIGUOUS until the lip-motion heuristic (Gate 3) is implemented. This is a
labeled assumption, not speaker identification.
"""
from __future__ import annotations

from collections import Counter

from shared.contracts import SpeakerMatch, SpeechTurn

PRESENCE = 0.6
PAD_MS = 300


def match_speaker(turn: SpeechTurn, visibility_history) -> SpeakerMatch:
    """visibility_history: iterable of (t_ms, tuple(person_ids visible))."""
    lo, hi = turn.start_ms - PAD_MS, turn.end_ms + PAD_MS
    window = [ids for t, ids in visibility_history if lo <= t <= hi]
    if not window:
        return SpeakerMatch(turn.turn_id, None, "none", 0.0, 0.0, "UNKNOWN")
    counts = Counter(pid for ids in window for pid in set(ids))
    present = {pid: n / len(window) for pid, n in counts.items() if n / len(window) >= PRESENCE}
    if len(present) == 0:
        return SpeakerMatch(turn.turn_id, None, "none", 0.0, 0.0, "OFFSCREEN")
    if len(present) == 1:
        pid, frac = next(iter(present.items()))
        return SpeakerMatch(turn.turn_id, pid, "single_candidate", frac, frac, "MATCHED")
    return SpeakerMatch(turn.turn_id, None, "none", 0.0, 0.0, "AMBIGUOUS")
