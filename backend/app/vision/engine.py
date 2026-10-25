"""Single vision worker: detection -> tracks -> session identity -> gestures -> privacy -> pixels.

Only `VisionEngine.step` mutates the registry. Requests from voice/dev are
queued with `submit()` and applied at the start of the next step; gestures are
evaluated inside `step` from the same frame's landmarks.
"""
from __future__ import annotations

import itertools
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np

from backend.app.consent.registry import PersonRegistry
from backend.app.vision.detector import Detection, cosine
from backend.app.vision.renderer import full_shield, render_protected
from shared.contracts import (FramePacket, FrameResult, IdentityStatus,
                              OutputState, PrivacyRequest, RequestAction,
                              event_envelope)


@dataclass
class EngineConfig:
    # identity (SFace cosine)
    t_match: float = 0.40        # accept a gallery match
    t_new: float = 0.22          # below this vs every unbound person -> candidate new person
    margin: float = 0.06         # best minus runner-up
    votes_match: int = 3         # consecutive good frames agreeing on a match
    votes_new: int = 8           # consecutive good frames agreeing this is someone new
    recheck_sim: float = 0.12    # own-gallery similarity that suggests an ID swap
    recheck_votes: int = 3       # consecutive good-frame checks below recheck_sim
    gallery_every: int = 10      # frames between gallery samples for a matched track
    # face quality gate for identity decisions
    q_min_score: float = 0.85
    q_min_size: float = 48.0
    q_edge_px: float = 3.0
    q_max_yaw: float = 0.35      # |nose - eye midpoint| / eye distance
    # tracking
    coast_ms: int = 1200         # keep a lost box (shielded if protected/pending) this long
    pending_timeout: int = 90
    unresolved_shield_ms: int = 3000
    # gestures
    eyes_closed_thr: float = 0.50
    eyes_hold_ms: int = 2000     # eyes closed this long -> blur me
    cover_hold_ms: int = 1500    # hand(s) over both eyes this long -> blur me
    peace_hold_ms: int = 1000    # peace sign this long -> unblur me (own face only)
    gesture_cooldown_ms: int = 2500
    hand_max_dist: float = 3.5   # palm-to-face distance in face widths
    hand_ratio: float = 1.6      # nearest face must be this much closer than the next


@dataclass
class GestureState:
    eyes_since: Optional[int] = None
    cover_since: Optional[int] = None
    peace_since: Optional[int] = None
    cooldown_until: int = -1
    eyes_closed: float = 0.0
    covered: bool = False
    peace: bool = False


@dataclass
class Track:
    track_id: str
    box: tuple
    det: Optional[Detection]
    last_seen_ms: int = 0
    person_id: Optional[str] = None
    status: IdentityStatus = IdentityStatus.IDENTITY_PENDING
    missed: int = 0
    age: int = 0
    vote_pid: Optional[str] = None
    vote_count: int = 0
    pending_frames: int = 0
    swap_count: int = 0
    shielded: bool = False


def _iou(a, b) -> float:
    ax0, ay0, aw, ah = a
    bx0, by0, bw, bh = b
    ix = max(0.0, min(ax0 + aw, bx0 + bw) - max(ax0, bx0))
    iy = max(0.0, min(ay0 + ah, by0 + bh) - max(ay0, by0))
    inter = ix * iy
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def _center(b):
    return (b[0] + b[2] / 2, b[1] + b[3] / 2)


def _center_dist(a, b) -> float:
    (ax, ay), (bx, by) = _center(a), _center(b)
    return float(np.hypot(ax - bx, ay - by))


class VisionEngine:
    def __init__(self, session_id: str, detect: Callable, feature: Callable,
                 config: Optional[EngineConfig] = None, signals: Optional[Callable] = None):
        self.session_id = session_id
        self.detect = detect        # bgr -> list[Detection]
        self.feature = feature      # (bgr, Detection) -> unit (1,128) feature
        self.signals = signals      # optional (bgr, t_ms) -> {"faces": [...], "hands": [...]}
        self.cfg = config or EngineConfig()
        self.registry = PersonRegistry(session_id)
        self.tracks: list[Track] = []
        self.gestures: dict[str, GestureState] = {}
        self.mouth_now: dict = {}
        self._tid = itertools.count(1)
        self._eid = itertools.count(1)
        self._requests: "queue.Queue[PrivacyRequest]" = queue.Queue()
        self._seen_event_ids: set[str] = set()
        self.unresolved_until_ms = -1
        self.last_events: list[dict] = []
        self.event_log: list[dict] = []
        self._vis_lock = threading.Lock()
        self._visibility: deque = deque(maxlen=1800)  # (t_ms, person_ids, {pid: mouth}) ~60 s

    # ---- inputs from other threads -------------------------------------
    def submit(self, req: PrivacyRequest) -> None:
        self._requests.put(req)

    def visibility_history(self) -> list:
        with self._vis_lock:
            return list(self._visibility)

    def visible_person_ids(self) -> list[str]:
        """Confirmed identities with a live (non-coasting) detection right now."""
        return [t.person_id for t in self.tracks if t.person_id and t.missed == 0]

    # ---- main step -----------------------------------------------------
    def step(self, pkt: FramePacket) -> FrameResult:
        t0 = time.perf_counter()
        events: list[dict] = []
        try:
            self._apply_requests(pkt, events)
            dets = self.detect(pkt.bgr)
            self._associate(dets, pkt)
            self._identify(pkt, events)
            sig = self._signals(pkt)
            mouths = self._map_faces(sig)
            self._gestures(pkt, sig, events)
            with self._vis_lock:
                self._visibility.append((pkt.t_ms, tuple(self.visible_person_ids()), mouths))
            regions, state = self._decide_regions(pkt)
            out = render_protected(pkt.bgr, regions) if regions else pkt.bgr.copy()
        except Exception as exc:  # fail closed: no source pixels on error
            out = full_shield(pkt.bgr.shape, "VISION ERROR - SHIELDED")
            state = OutputState.ERROR
            events.append(self._event(pkt, "VISION_ERROR", details={"error": type(exc).__name__}))
        self.last_events = events
        self.event_log.extend(events)
        return FrameResult(session_id=self.session_id, frame_id=pkt.frame_id, t_ms=pkt.t_ms,
                           protected_bgr=out, tracks=self._track_snapshot(pkt), events=events,
                           output_state=state, vision_ms=(time.perf_counter() - t0) * 1000)

    # ---- internals -----------------------------------------------------
    def _event(self, pkt, type_, person_id=None, source=None, details=None) -> dict:
        return event_envelope(self.session_id, f"event_{next(self._eid)}", type_, pkt.t_ms,
                              person_id, source, details)

    def _protect(self, pkt, pid, source, details, events) -> None:
        if self.registry.protect(pid, pkt.t_ms, source):
            events.append(self._event(pkt, "PRIVACY_ACTIVATED", pid, source, details))

    def _unprotect(self, pkt, pid, source, details, events) -> None:
        if self.registry.unprotect(pid, pkt.t_ms, source):
            events.append(self._event(pkt, "PRIVACY_RELEASED", pid, source, details))

    def _apply_requests(self, pkt: FramePacket, events: list) -> None:
        while True:
            try:
                req = self._requests.get_nowait()
            except queue.Empty:
                return
            if req.session_id != self.session_id or req.event_id in self._seen_event_ids:
                continue
            self._seen_event_ids.add(req.event_id)
            src = req.origin.value
            details = {"turn_id": req.turn_id, "request_event": req.event_id}
            if req.action == RequestAction.PROTECT and req.verified and req.target_person_id:
                self._protect(pkt, req.target_person_id, src, details, events)
            elif req.action == RequestAction.UNPROTECT and req.verified and req.target_person_id:
                self._unprotect(pkt, req.target_person_id, src, details, events)
            elif req.action in (RequestAction.UNRESOLVED, RequestAction.PROTECT):
                self.unresolved_until_ms = pkt.t_ms + self.cfg.unresolved_shield_ms
                events.append(self._event(pkt, "REQUEST_UNRESOLVED", None, src, details))
            else:  # REQUEST_ALLOW or unverified UNPROTECT: recorded, no effect
                events.append(self._event(pkt, "ALLOW_REQUEST_IGNORED", req.target_person_id, src,
                                          {**details, "reason": "consent not bound to the protected person"}))

    def _associate(self, dets: list[Detection], pkt: FramePacket) -> None:
        pairs = []
        for ti, t in enumerate(self.tracks):
            for di, d in enumerate(dets):
                iou = _iou(t.box, d.box)
                dist = _center_dist(t.box, d.box)
                gate = 0.8 * max(t.box[2], t.box[3], d.box[2], d.box[3])
                if iou > 0.1 or dist < gate:
                    pairs.append((iou - dist / 1000.0, ti, di))
        pairs.sort(reverse=True)
        used_t, used_d = set(), set()
        for _, ti, di in pairs:
            if ti in used_t or di in used_d:
                continue
            used_t.add(ti); used_d.add(di)
            t = self.tracks[ti]
            t.box, t.det, t.missed, t.last_seen_ms = dets[di].box, dets[di], 0, pkt.t_ms
            t.age += 1
        for ti, t in enumerate(self.tracks):
            if ti not in used_t:
                t.missed += 1
                t.det = None
        self.tracks = [t for t in self.tracks if pkt.t_ms - t.last_seen_ms <= self.cfg.coast_ms]
        for di, d in enumerate(dets):
            if di not in used_d:
                self.tracks.append(Track(track_id=f"track_{next(self._tid)}", box=d.box, det=d,
                                         last_seen_ms=pkt.t_ms))

    def _good(self, d: Detection, shape) -> bool:
        """Only frontal, confident, fully-visible faces may decide identity."""
        c = self.cfg
        x, y, w, h = d.box
        H, W = shape[:2]
        if d.score < c.q_min_score or min(w, h) < c.q_min_size:
            return False
        if x < c.q_edge_px or y < c.q_edge_px or x + w > W - c.q_edge_px or y + h > H - c.q_edge_px:
            return False
        r = d.raw
        re_, le, nose = np.array(r[4:6]), np.array(r[6:8]), np.array(r[8:10])
        eye = float(np.linalg.norm(le - re_))
        if eye < 0.25 * w:
            return False
        mid = (le + re_) / 2
        return abs(nose[0] - mid[0]) / eye <= c.q_max_yaw and abs(le[1] - re_[1]) / eye <= 0.35

    def _identify(self, pkt: FramePacket, events: list) -> None:
        cfg = self.cfg
        live_bound = {t.person_id for t in self.tracks if t.person_id and t.missed == 0}
        for t in self.tracks:
            if t.det is None:
                continue
            good = self._good(t.det, pkt.bgr.shape)
            p = self.registry.get(t.person_id)
            if p is not None:
                p.last_seen_ms = pkt.t_ms
                if good and t.age % cfg.gallery_every == 0:
                    f = self.feature(pkt.bgr, t.det)
                    own = max((cosine(f, g) for g in p.gallery), default=1.0)
                    # A real ID swap = this face now clearly matches a DIFFERENT known person.
                    # Low similarity to everyone is just a bad angle: keep the identity.
                    other = max((max(cosine(f, g) for g in q.gallery) for q in self.registry.persons.values()
                                 if q.person_id != p.person_id and q.gallery), default=-1.0)
                    if own < cfg.recheck_sim and other >= cfg.t_match:
                        t.swap_count += 1
                        if t.swap_count >= cfg.recheck_votes:  # consistently someone else: re-verify
                            events.append(self._event(pkt, "IDENTITY_RECHECK", p.person_id,
                                                      details={"track_id": t.track_id, "own_sim": round(own, 2),
                                                               "other_sim": round(other, 2)}))
                            live_bound.discard(t.person_id)
                            t.person_id, t.status = None, IdentityStatus.IDENTITY_PENDING
                            t.vote_pid, t.vote_count, t.pending_frames, t.swap_count = None, 0, 0, 0
                    else:
                        if own >= cfg.recheck_sim:
                            t.swap_count = 0
                        if own >= 0.5:
                            p.add_feature(f)
                continue

            # pending track: decide identity before it can be shown as a known person
            t.pending_frames += 1
            if t.pending_frames > cfg.pending_timeout:
                t.status = IdentityStatus.AMBIGUOUS_MATCH
            if not good:
                continue
            f = self.feature(pkt.bgr, t.det)
            scores = sorted(
                ((max(cosine(f, g) for g in q.gallery), q.person_id)
                 for q in self.registry.persons.values() if q.gallery and q.person_id not in live_bound),
                reverse=True)
            best, best_pid = scores[0] if scores else (-1.0, None)
            second = scores[1][0] if len(scores) > 1 else -1.0
            if best >= cfg.t_match and best - second >= cfg.margin:
                vote = best_pid
            elif best < cfg.t_new:
                vote = "__new__"
            else:
                vote = None  # ambiguous frame: stay pending
            if vote is not None and vote == t.vote_pid:
                t.vote_count += 1
            else:
                t.vote_pid, t.vote_count = vote, (1 if vote else 0)
            needed = cfg.votes_new if vote == "__new__" else cfg.votes_match
            if vote is None or t.vote_count < needed:
                continue
            if vote == "__new__":
                person = self.registry.new_person(pkt.t_ms)
                t.status = IdentityStatus.CONFIRMED_NEW
                events.append(self._event(pkt, "PERSON_NEW", person.person_id,
                                          details={"track_id": t.track_id, "best_other": round(best, 2)}))
            else:
                person = self.registry.get(vote)
                # the same person can't also be a lingering lost box elsewhere
                self.tracks = [o for o in self.tracks if o is t or o.person_id != vote]
                t.status = IdentityStatus.MATCHED
                events.append(self._event(pkt, "PERSON_MATCHED", person.person_id,
                                          details={"track_id": t.track_id, "protected": person.protected,
                                                   "score": round(best, 3)}))
            person.add_feature(f)
            person.last_seen_ms = pkt.t_ms
            t.person_id = person.person_id
            live_bound.add(person.person_id)

    def _signals(self, pkt: FramePacket) -> dict:
        """Landmark evidence. Failure = no evidence (never unshields, never blurs)."""
        if self.signals is None:
            return {"faces": [], "hands": []}
        try:
            return self.signals(pkt.bgr, pkt.t_ms)
        except Exception:
            return {"faces": [], "hands": []}

    def _map_faces(self, sig: dict) -> dict:
        """Attach face-landmark samples (mouth, eyes) to live identified tracks."""
        mouths, eyes = {}, {}
        for t in self.tracks:
            if not t.person_id or t.missed:
                continue
            x, y, w, h = t.box
            cands = [(f, (f["c"][0] - x - w / 2) ** 2 + (f["c"][1] - y - h / 2) ** 2) for f in sig["faces"]
                     if x - 0.2 * w <= f["c"][0] <= x + 1.2 * w and y - 0.2 * h <= f["c"][1] <= y + 1.2 * h]
            if cands:
                f = min(cands, key=lambda v: v[1])[0]
                mouths[t.person_id] = f["mouth"]
                eyes[t.person_id] = f["eyes_closed"]
        self.mouth_now, self._eyes_now = mouths, eyes
        return mouths

    def _hand_owner(self, hand: dict, cands: list) -> Optional[Track]:
        """Nearest identified face to the palm, only if clearly nearer than any other face."""
        scored = []
        for t in cands:
            cx, cy = _center(t.box)
            d = float(np.hypot(hand["c"][0] - cx, hand["c"][1] - cy)) / max(t.box[2], 1.0)
            scored.append((d, t))
        scored.sort(key=lambda v: v[0])
        if not scored or scored[0][0] > self.cfg.hand_max_dist:
            return None
        if len(scored) > 1 and scored[1][0] < self.cfg.hand_ratio * scored[0][0]:
            return None  # two faces about equally close: don't guess whose hand it is
        return scored[0][1]

    @staticmethod
    def _covers_eyes(t: Track, hands: list) -> bool:
        x, y, w, h = t.box
        y0, y1 = y + 0.10 * h, y + 0.60 * h
        left = right = 0
        for hd in hands:
            if hd["peace"]:
                continue
            for px, py in hd["pts"]:
                if x <= px <= x + w and y0 <= py <= y1:
                    if px < x + w / 2:
                        left += 1
                    else:
                        right += 1
        return left >= 3 and right >= 3

    def _gestures(self, pkt: FramePacket, sig: dict, events: list) -> None:
        cfg = self.cfg
        now = pkt.t_ms
        cands = [t for t in self.tracks if t.person_id]
        peace_owner = set()
        for hd in sig["hands"]:
            # a hand resting on any face (touching, scratching) is never a consent sign
            on_face = any(t.box[0] <= hd["c"][0] <= t.box[0] + t.box[2] and t.box[1] <= hd["c"][1] <= t.box[1] + t.box[3]
                          for t in self.tracks)
            if hd["peace"] and not on_face:
                owner = self._hand_owner(hd, cands)
                if owner is not None:
                    peace_owner.add(owner.person_id)
        eyes_now = getattr(self, "_eyes_now", {})
        for t in cands:
            pid = t.person_id
            g = self.gestures.setdefault(pid, GestureState())
            g.eyes_closed = eyes_now.get(pid, 0.0)
            g.covered = self._covers_eyes(t, sig["hands"])
            g.peace = pid in peace_owner
            if g.covered:  # hands over the face hide it from the detector: keep the track alive
                t.last_seen_ms = now
            g.eyes_since = (g.eyes_since or now) if g.eyes_closed >= cfg.eyes_closed_thr and t.missed == 0 else None
            g.cover_since = (g.cover_since or now) if g.covered else None
            g.peace_since = (g.peace_since or now) if g.peace else None
            if now < g.cooldown_until:
                continue
            p = self.registry.get(pid)
            if not p.protected:
                which = None
                if g.eyes_since is not None and now - g.eyes_since >= cfg.eyes_hold_ms:
                    which = "eyes_closed"
                elif g.cover_since is not None and now - g.cover_since >= cfg.cover_hold_ms:
                    which = "hands_over_eyes"
                if which:
                    self._protect(pkt, pid, "GESTURE", {"gesture": which}, events)
                    g.cooldown_until = now + cfg.gesture_cooldown_ms
                    g.eyes_since = g.cover_since = None
            elif g.peace_since is not None and now - g.peace_since >= cfg.peace_hold_ms:
                self._unprotect(pkt, pid, "GESTURE", {"gesture": "peace_sign"}, events)
                g.cooldown_until = now + cfg.gesture_cooldown_ms
                g.peace_since = None

    def _decide_regions(self, pkt: FramePacket):
        regions = []
        shielded_any = False
        unresolved = pkt.t_ms < self.unresolved_until_ms
        bound = {t.person_id for t in self.tracks if t.person_id}
        protected_unbound = any(p.protected and p.person_id not in bound
                                for p in self.registry.persons.values())
        for t in self.tracks:
            p = self.registry.get(t.person_id)
            if p is not None:
                shield = p.protected
            else:
                # unknown face while a protected person is unaccounted for: shield until decided
                shield = protected_unbound
            if unresolved:
                shield = True
            t.shielded = shield
            if shield:
                regions.append(t.box)
                shielded_any = True
        return regions, (OutputState.REGION_SHIELDED if shielded_any else OutputState.NORMAL)

    def _track_snapshot(self, pkt: FramePacket) -> list[dict]:
        out = []
        for t in self.tracks:
            p = self.registry.get(t.person_id)
            g = self.gestures.get(t.person_id) if t.person_id else None
            held = lambda since: round((pkt.t_ms - since) / 1000, 1) if since is not None else None
            out.append({
                "track_id": t.track_id,
                "person_id": t.person_id,
                "identity_status": t.status.value,
                "privacy": p.privacy.value if p else None,
                "shielded": t.shielded,
                "coasting": t.missed > 0,
                "box": [round(v) for v in t.box],
                "mouth_open": round(self.mouth_now[t.person_id], 3) if t.person_id in self.mouth_now else None,
                "gesture": None if g is None else {
                    "eyes_closed_s": held(g.eyes_since), "cover_s": held(g.cover_since),
                    "peace_s": held(g.peace_since)},
            })
        return out
