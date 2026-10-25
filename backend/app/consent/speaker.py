"""Bind a speech turn to a visible person. Conservative: ambiguity -> no target.

Methods (labeled in every result, never presented as speaker identification):
- `single_candidate`: exactly one confirmed person visible for most of the turn.
- `lip_motion_heuristic`: with 2+ people, the person whose lip openness moved
  clearly more during the turn window than everyone else. Requires a margin;
  otherwise AMBIGUOUS. Both talking, nobody moving, or offscreen -> no target.
"""
from __future__ import annotations

from collections import Counter, defaultdict

import numpy as np

from shared.contracts import SpeakerMatch, SpeechTurn

PRESENCE = 0.6
PAD_MS = 300
MIN_ACTIVITY = 0.012   # mean |Δ openness| per frame that counts as speaking (calibrate live)
MIN_RATIO = 2.0        # top activity must be this many times the runner-up
MIN_SAMPLES = 6


def lip_activity(samples: list[float]) -> float:
    if len(samples) < MIN_SAMPLES:
        return 0.0
    a = np.asarray(samples, dtype=np.float32)
    return float(np.mean(np.abs(np.diff(a))) + 0.5 * np.std(a))


def match_speaker(turn: SpeechTurn, visibility_history) -> SpeakerMatch:
    """visibility_history: iterable of (t_ms, person_ids[, {person_id: mouth_openness}])."""
    lo, hi = turn.start_ms - PAD_MS, turn.end_ms + PAD_MS
    window = [row for row in visibility_history if lo <= row[0] <= hi]
    if not window:
        return SpeakerMatch(turn.turn_id, None, "none", 0.0, 0.0, "UNKNOWN")
    counts = Counter(pid for row in window for pid in set(row[1]))
    present = {pid: n / len(window) for pid, n in counts.items() if n / len(window) >= PRESENCE}
    if len(present) == 0:
        return SpeakerMatch(turn.turn_id, None, "none", 0.0, 0.0, "OFFSCREEN")
    series = defaultdict(list)
    for row in window:
        if len(row) > 2:
            for pid, o in row[2].items():
                if pid in present:
                    series[pid].append(o)

    if len(present) == 1:
        pid, frac = next(iter(present.items()))
        samples = series.get(pid, [])
        if len(samples) >= MIN_SAMPLES and lip_activity(samples) < MIN_ACTIVITY:
            # one face visible but its lips did not move: voice is probably offscreen
            return SpeakerMatch(turn.turn_id, None, "single_candidate", round(lip_activity(samples), 4),
                                0.0, "OFFSCREEN")
        return SpeakerMatch(turn.turn_id, pid, "single_candidate", frac, frac, "MATCHED")
    scores = sorted(((lip_activity(series.get(pid, [])), pid) for pid in present), reverse=True)
    top, top_pid = scores[0]
    runner = scores[1][0]
    if top >= MIN_ACTIVITY and top >= MIN_RATIO * max(runner, 1e-6):
        return SpeakerMatch(turn.turn_id, top_pid, "lip_motion_heuristic", round(top, 4),
                            round(top - runner, 4), "MATCHED")
    return SpeakerMatch(turn.turn_id, None, "lip_motion_heuristic", round(top, 4),
                        round(top - runner, 4), "AMBIGUOUS")
