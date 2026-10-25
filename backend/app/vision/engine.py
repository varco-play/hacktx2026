"""Single vision worker: detection -> tracks -> session identity -> privacy -> pixels.

Only `VisionEngine.step` mutates the registry. Requests from voice/gesture/dev
are queued with `submit()` and applied at the start of the next step.
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
    t_match: float = 0.40       # cosine to accept a gallery match
    t_new: float = 0.28         # below this vs everyone -> new person
    margin: float = 0.06        # best minus runner-up
    votes_needed: int = 3       # consecutive agreeing frames to decide identity
    pending_timeout: int = 60   # frames before a pending track is AMBIGUOUS
    coast_frames: int = 15      # keep shielding a lost protected/pending box this long
    clear_min_score: float = 0.80
    clear_min_size: float = 40.0
    gallery_every: int = 10     # frames between gallery samples for a matched track
    swap_sim: float = 0.20      # own-gallery similarity that suggests an ID swap
    unresolved_shield_ms: int = 3000


@dataclass
class Track:
    track_id: str
    box: tuple
    det: Optional[Detection]
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


def _center_dist(a, b) -> float:
    return float(np.hypot((a[0] + a[2] / 2) - (b[0] + b[2] / 2),
                          (a[1] + a[3] / 2) - (b[1] + b[3] / 2)))


class VisionEngine:
    def __init__(self, session_id: str, detect: Callable, feature: Callable,
                 config: Optional[EngineConfig] = None, mouth: Optional[Callable] = None):
        self.session_id = session_id
        self.detect = detect      # bgr -> list[Detection]
        self.feature = feature    # (bgr, Detection) -> unit (1,128) feature
        self.mouth = mouth        # optional (bgr, t_ms) -> [(cx, cy, openness)]
        self.mouth_now: dict = {}  # person_id -> latest openness (UI/diagnostics)
        self.cfg = config or EngineConfig()
        self.registry = PersonRegistry(session_id)
        self.tracks: list[Track] = []
        self._tid = itertools.count(1)
        self._eid = itertools.count(1)
        self._requests: "queue.Queue[PrivacyRequest]" = queue.Queue()
        self._seen_event_ids: set[str] = set()
        self.unresolved_until_ms = -1
        self.last_events: list[dict] = []
        self.event_log: list[dict] = []
        self._vis_lock = threading.Lock()
        self._visibility: deque = deque(maxlen=900)  # (t_ms, visible person_ids) ~60 s

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
            self._associate(dets)
            self._identify(pkt, events)
            mouths = self._mouths(pkt)
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
                           protected_bgr=out, tracks=self._track_snapshot(), events=events,
                           output_state=state, vision_ms=(time.perf_counter() - t0) * 1000)

    # ---- internals -----------------------------------------------------
    def _event(self, pkt, type_, person_id=None, source=None, details=None) -> dict:
        return event_envelope(self.session_id, f"event_{next(self._eid)}", type_, pkt.t_ms,
                              person_id, source, details)

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
            if req.action == RequestAction.PROTECT and req.verified and req.target_person_id:
                if self.registry.protect(req.target_person_id, pkt.t_ms, src):
                    events.append(self._event(pkt, "PRIVACY_ACTIVATED", req.target_person_id, src,
                                              {"turn_id": req.turn_id, "request_event": req.event_id}))
            elif req.action == RequestAction.UNRESOLVED or (req.action == RequestAction.PROTECT):
                self.unresolved_until_ms = pkt.t_ms + self.cfg.unresolved_shield_ms
                events.append(self._event(pkt, "REQUEST_UNRESOLVED", None, src,
                                          {"turn_id": req.turn_id}))
            elif req.action == RequestAction.REQUEST_ALLOW:
                events.append(self._event(pkt, "ALLOW_REQUEST_IGNORED", req.target_person_id, src,
                                          {"turn_id": req.turn_id,
                                           "reason": "no verified reauthorization in MVP"}))

    def _associate(self, dets: list[Detection]) -> None:
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
            t.box, t.det, t.missed = dets[di].box, dets[di], 0
            t.age += 1
        for ti, t in enumerate(self.tracks):
            if ti not in used_t:
                t.missed += 1
                t.det = None
        self.tracks = [t for t in self.tracks if t.missed <= self.cfg.coast_frames]
        for di, d in enumerate(dets):
            if di not in used_d:
                self.tracks.append(Track(track_id=f"track_{next(self._tid)}", box=d.box, det=d))

    def _mouths(self, pkt: FramePacket) -> dict:
        """Lip openness per visible confirmed person. Failure = no evidence, never unshields."""
        if self.mouth is None:
            return {}
        try:
            samples = self.mouth(pkt.bgr, pkt.t_ms)
        except Exception:
            return {}
        out = {}
        for t in self.tracks:
            if not t.person_id or t.missed:
                continue
            x, y, w, h = t.box
            inside = [(o, (cx - x - w / 2) ** 2 + (cy - y - h / 2) ** 2) for cx, cy, o in samples
                      if x - 0.2 * w <= cx <= x + 1.2 * w and y - 0.2 * h <= cy <= y + 1.2 * h]
            if inside:
                out[t.person_id] = min(inside, key=lambda v: v[1])[0]
        self.mouth_now = out
        return out

    def _is_clear(self, d: Detection) -> bool:
        return d.score >= self.cfg.clear_min_score and min(d.box[2], d.box[3]) >= self.cfg.clear_min_size

    def _identify(self, pkt: FramePacket, events: list) -> None:
        cfg = self.cfg
        bound = {t.person_id for t in self.tracks if t.person_id}
        for t in self.tracks:
            if t.det is None:
                continue
            p = self.registry.get(t.person_id)
            if p is not None:
                p.last_seen_ms = pkt.t_ms
                if t.age % cfg.gallery_every == 0 and self._is_clear(t.det):
                    f = self.feature(pkt.bgr, t.det)
                    own = max((cosine(f, g) for g in p.gallery), default=1.0)
                    if own < cfg.swap_sim:
                        t.swap_count += 1
                        if t.swap_count >= 2:  # identity no longer matches: re-verify
                            events.append(self._event(pkt, "IDENTITY_RECHECK", p.person_id,
                                                      details={"track_id": t.track_id}))
                            bound.discard(t.person_id)
                            t.person_id, t.status = None, IdentityStatus.IDENTITY_PENDING
                            t.vote_pid, t.vote_count, t.pending_frames = None, 0, 0
                    else:
                        t.swap_count = 0
                        if own >= cfg.t_match + 0.1:
                            p.add_feature(f)
                continue

            # pending track: decide identity before it can be shown as a known person
            t.pending_frames += 1
            if t.pending_frames > cfg.pending_timeout:
                t.status = IdentityStatus.AMBIGUOUS_MATCH
            if not self._is_clear(t.det):
                continue
            f = self.feature(pkt.bgr, t.det)
            scores = sorted(
                ((max(cosine(f, g) for g in q.gallery), q.person_id)
                 for q in self.registry.persons.values() if q.gallery and q.person_id not in bound),
                reverse=True)
            best, best_pid = scores[0] if scores else (-1.0, None)
            second = scores[1][0] if len(scores) > 1 else -1.0
            if best >= cfg.t_match and best - second >= cfg.margin:
                vote = best_pid
            elif best < cfg.t_new:
                vote = "__new__"
            else:
                vote = None  # ambiguous frame
            if vote is not None and vote == t.vote_pid:
                t.vote_count += 1
            else:
                t.vote_pid, t.vote_count = vote, (1 if vote else 0)
            if t.vote_count >= cfg.votes_needed:
                if vote == "__new__":
                    person = self.registry.new_person(pkt.t_ms)
                    t.status = IdentityStatus.CONFIRMED_NEW
                    events.append(self._event(pkt, "PERSON_NEW", person.person_id,
                                              details={"track_id": t.track_id}))
                else:
                    person = self.registry.get(vote)
                    t.status = IdentityStatus.MATCHED
                    events.append(self._event(pkt, "PERSON_MATCHED", person.person_id,
                                              details={"track_id": t.track_id,
                                                       "protected": person.protected,
                                                       "score": round(best, 3)}))
                person.add_feature(f)
                person.last_seen_ms = pkt.t_ms
                t.person_id = person.person_id
                bound.add(person.person_id)

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

    def _track_snapshot(self) -> list[dict]:
        out = []
        for t in self.tracks:
            p = self.registry.get(t.person_id)
            out.append({
                "track_id": t.track_id,
                "person_id": t.person_id,
                "identity_status": t.status.value,
                "privacy": p.privacy.value if p else None,
                "shielded": t.shielded,
                "coasting": t.missed > 0,
                "mouth_open": round(self.mouth_now[t.person_id], 3) if t.person_id in self.mouth_now else None,
                "box": [round(v) for v in t.box],
            })
        return out
