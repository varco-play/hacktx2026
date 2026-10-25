"""Bind a speech turn to a visible person. Conservative: ambiguity -> no target.

Methods (labeled in every result, never presented as speaker identification):
- `av_sync`: the person whose lip opening rises and falls WITH the microphone's
  loudness during the turn (Pearson correlation, best lag within ±200 ms). People
  laughing/chewing out of sync with the voice score low. Primary method.
- `lip_motion_heuristic`: fallback when no audio envelope is available: the person
  whose lips moved clearly more than everyone else's.
- `single_candidate`: one person visible and no lip data at all (landmarks missing).

Self-calibrating: each person's lip "noise floor" is measured from moments when the
mic is quiet, so the speaking threshold adapts to the person, camera and lighting.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Optional

import numpy as np

from shared.contracts import SpeakerMatch, SpeechTurn

PRESENCE = 0.6
PAD_MS = 300
MIN_SAMPLES = 6
# lip-only fallback
MIN_ACTIVITY = 0.012
MIN_RATIO = 2.0
# audio-visual sync
AV_MIN_CORR = 0.30       # top person's lips must follow the voice at least this well
AV_MARGIN = 0.15         # ...and clearly better than anyone else
AV_SINGLE_MIN = 0.15     # one visible person: still must loosely follow the voice
LAGS_MS = range(-200, 201, 40)
FLOOR_ABS = 0.004        # absolute minimum lip activity to count as speaking
FLOOR_MULT = 1.5         # speaking = activity above 1.5x the person's quiet-time jitter


def lip_activity(samples: list[float]) -> float:
    if len(samples) < MIN_SAMPLES:
        return 0.0
    a = np.asarray(samples, dtype=np.float32)
    return float(np.mean(np.abs(np.diff(a))) + 0.5 * np.std(a))


def _series(rows, present) -> dict:
    out = defaultdict(list)
    for row in rows:
        if len(row) > 2:
            for pid, o in row[2].items():
                if pid in present:
                    out[pid].append((row[0], o))
    return out


def _corr(ts: np.ndarray, lips: np.ndarray, env_t: np.ndarray, env_v: np.ndarray) -> float:
    if lips.std() < 1e-6:
        return 0.0
    best = -1.0
    for lag in LAGS_MS:
        a = np.interp(ts + lag, env_t, env_v)
        if a.std() < 1e-9:
            continue
        best = max(best, float(np.corrcoef(lips, a)[0, 1]))
    return best


def noise_floor(pid: str, history, audio_env) -> float:
    """Lip jitter of this person while the mic is quiet (bottom 30% loudness)."""
    if not audio_env:
        return MIN_ACTIVITY
    env_t = np.array([t for t, _ in audio_env], dtype=np.float64)
    env_v = np.array([v for _, v in audio_env], dtype=np.float64)
    quiet = np.percentile(env_v, 30)
    samples = [row[2][pid] for row in history if len(row) > 2 and pid in row[2]
               and np.interp(row[0], env_t, env_v) <= quiet]
    if len(samples) < 20:
        return MIN_ACTIVITY
    return max(FLOOR_ABS, FLOOR_MULT * lip_activity(samples[-150:]))


def match_speaker(turn: SpeechTurn, visibility_history, audio_env: Optional[list] = None) -> SpeakerMatch:
    """visibility_history: iterable of (t_ms, person_ids[, {person_id: lip_openness}]).
    audio_env: optional [(t_ms, mic_rms)] on the same session clock."""
    history = list(visibility_history)
    lo, hi = turn.start_ms - PAD_MS, turn.end_ms + PAD_MS
    window = [row for row in history if lo <= row[0] <= hi]
    if not window:
        return SpeakerMatch(turn.turn_id, None, "none", 0.0, 0.0, "UNKNOWN")
    counts = Counter(pid for row in window for pid in set(row[1]))
    present = {pid: n / len(window) for pid, n in counts.items() if n / len(window) >= PRESENCE}
    if not present:
        return SpeakerMatch(turn.turn_id, None, "none", 0.0, 0.0, "OFFSCREEN")
    series = _series(window, present)
    env = [(t, v) for t, v in (audio_env or []) if lo - 300 <= t <= hi + 300]

    if len(env) >= 10 and any(len(v) >= MIN_SAMPLES for v in series.values()):
        env_t = np.array([t for t, _ in env], dtype=np.float64)
        env_v = np.array([v for _, v in env], dtype=np.float64)
        scored = []
        for pid in present:
            s = series.get(pid, [])
            if len(s) < MIN_SAMPLES:
                scored.append((-1.0, 0.0, pid))
                continue
            ts = np.array([t for t, _ in s], dtype=np.float64)
            lips = np.array([o for _, o in s], dtype=np.float64)
            act = lip_activity(list(lips))
            c = _corr(ts, lips, env_t, env_v) if act >= noise_floor(pid, history, audio_env) else 0.0
            scored.append((c, act, pid))
        scored.sort(reverse=True)
        top_c, top_act, top_pid = scored[0]
        runner = scored[1][0] if len(scored) > 1 else -1.0
        if len(present) == 1:
            # One person in view: their lips merely MOVING above their own quiet-time level is
            # enough (laptop mics make tight audio-visual correlation unreliable). Still lips =
            # the voice came from someone off camera -> no target.
            moved = top_act >= noise_floor(top_pid, history, audio_env)
            if top_c >= AV_SINGLE_MIN or moved:
                return SpeakerMatch(turn.turn_id, top_pid, "av_sync" if top_c >= AV_SINGLE_MIN else "lips_moved",
                                    round(top_c, 3), round(top_c, 3), "MATCHED")
            return SpeakerMatch(turn.turn_id, None, "av_sync", round(top_c, 3), 0.0, "OFFSCREEN")
        if top_c >= AV_MIN_CORR and top_c - runner >= AV_MARGIN:
            return SpeakerMatch(turn.turn_id, top_pid, "av_sync", round(top_c, 3), round(top_c - runner, 3), "MATCHED")
        return SpeakerMatch(turn.turn_id, None, "av_sync", round(top_c, 3), round(top_c - runner, 3), "AMBIGUOUS")

    # ---- no audio envelope: lip-motion-only fallback ----
    if len(present) == 1:
        pid, frac = next(iter(present.items()))
        samples = [o for _, o in series.get(pid, [])]
        if len(samples) >= MIN_SAMPLES and lip_activity(samples) < MIN_ACTIVITY:
            return SpeakerMatch(turn.turn_id, None, "single_candidate", round(lip_activity(samples), 4),
                                0.0, "OFFSCREEN")
        return SpeakerMatch(turn.turn_id, pid, "single_candidate", frac, frac, "MATCHED")
    scores = sorted(((lip_activity([o for _, o in series.get(pid, [])]), pid) for pid in present), reverse=True)
    top, top_pid = scores[0]
    runner = scores[1][0]
    if top >= MIN_ACTIVITY and top >= MIN_RATIO * max(runner, 1e-6):
        return SpeakerMatch(turn.turn_id, top_pid, "lip_motion_heuristic", round(top, 4),
                            round(top - runner, 4), "MATCHED")
    return SpeakerMatch(turn.turn_id, None, "lip_motion_heuristic", round(top, 4),
                        round(top - runner, 4), "AMBIGUOUS")
