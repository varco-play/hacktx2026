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
from shared.contracts import (FramePacket, FrameResult, IdentityStatus, Privacy,
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
    gallery_every: int = 10      # frames between gallery samples / swap checks
    enroll_samples: int = 5      # quick gallery samples right after someone asks for blur
    # face quality gate for identity decisions
    q_min_score: float = 0.85
    q_min_size: float = 48.0
    q_edge_px: float = 3.0
    q_max_yaw: float = 0.35      # |nose - eye midpoint| / eye distance
    # tracking
    coast_ms: int = 1200         # keep a lost box (shielded if protected/pending) this long
    continuity_ms: int = 3000    # a face reappearing where a known person was lost <3 s ago is them
    pending_timeout: int = 90
    unresolved_shield_ms: int = 0   # unclear speaker: change nobody (was 3 s blur-everyone)
    # gestures
    eyes_closed_thr: float = 0.50  # both eyes (live-tested MVP value)
    look_down_veto: float = 1.01   # disabled (was 0.55); kept configurable
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
    eyes_last: int = 0
    cover_last: int = 0
    peace_last: int = 0
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
    head_only: bool = False  # face lost; position follows the pose-estimated head


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
        self.strict = False         # PRIVACY_DEFAULT=protect: blur everyone until they consent
        self.follow_heads = False   # pose head-following (experimental; can drift onto neighbours)
        self._lost: list = []       # (person_id, last box, last_seen_ms) of recently expired tracks
        self.confirm: Optional[dict] = None  # {"intent": "ALLOW"|"DENY", "until": t_ms} after an unclear voice turn
        self.signals_every = 1      # quality profile: run landmarks every Nth frame, reuse otherwise
        self._sig_n = 0
        self._sig_last = {"faces": [], "hands": [], "heads": []}
        self.cfg = config or EngineConfig()
        self.registry = PersonRegistry(session_id)
        self.tracks: list[Track] = []
        self.gestures: dict[str, GestureState] = {}
        self.mouth_now: dict = {}
        self.bodies_now: dict = {}  # person_id -> pose body box (UI: whose hands are whose)
        self._tid = itertools.count(1)
        self._eid = itertools.count(1)
        self._requests: "queue.Queue[PrivacyRequest]" = queue.Queue()
        self._seen_event_ids: set[str] = set()
        self.unresolved_until_ms = -1
        self.last_events: list[dict] = []
        self.event_log: deque = deque(maxlen=2000)  # bounded for long sessions
        self._vis_lock = threading.Lock()
        self._visibility: deque = deque(maxlen=1800)  # (t_ms, person_ids, {pid: mouth}) ~60 s

    # ---- inputs from other threads -------------------------------------
    def submit(self, req: PrivacyRequest) -> None:
        self._requests.put(req)

    def request_confirmation(self, intent: str, t_ms: int, window_ms: int = 6000) -> None:
        """A voice request was heard but the speaker couldn't be identified (e.g. both talking).
        For a few seconds the asking person can confirm with a SHORT gesture of their own:
        peace sign (0.3 s) for "unblur", eye cover (0.5 s) for "blur". Ownership rules still apply,
        so a confirmation only ever changes the person who makes it."""
        self.confirm = {"intent": intent, "until": t_ms + window_ms}

    def visibility_history(self) -> list:
        with self._vis_lock:
            return list(self._visibility)

    def visible_person_ids(self) -> list[str]:
        """Confirmed identities with a live (non-coasting) detection right now."""
        return [t.person_id for t in self.tracks if t.person_id and t.missed == 0]

    # ---- main step -----------------------------------------------------
    def step(self, pkt: FramePacket, analyze: bool = True) -> FrameResult:
        """analyze=False is the cheap per-frame path (detect + track + identity + blur, ~5-8 ms)
        so the preview and recording run at camera rate; MediaPipe landmarks, head-following
        and gestures run only on analysis frames (quality profile sets their rate)."""
        t0 = time.perf_counter()
        events: list[dict] = []
        try:
            self._apply_requests(pkt, events)
            dets = self.detect(pkt.bgr)
            self._associate(dets, pkt)
            self._identify(pkt, events)
            if analyze or self._face_every_frame:
                # face landmarks (lips/eyes) every frame when supported; hands/pose only on
                # analysis frames — dense lip samples are what make "who spoke" work
                sig = self._signals(pkt, heavy=analyze)
                if analyze and self.follow_heads:
                    self._follow_heads(pkt, sig)  # off by default: can drift onto a nearby person
                mouths = self._map_faces(sig)
                self._gestures(pkt, sig, events)
                with self._vis_lock:
                    self._visibility.append((pkt.t_ms, tuple(self.visible_person_ids()), mouths))
            # (light frames: head-followed tracks stay alive via coast_ms > analysis interval)
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
            t.head_only = False
            t.age += 1
        for ti, t in enumerate(self.tracks):
            if ti not in used_t:
                t.missed += 1
                t.det = None
        keep = []
        for t in self.tracks:
            if pkt.t_ms - t.last_seen_ms <= self.cfg.coast_ms:
                keep.append(t)
            elif t.person_id:  # remember where a known person was last seen (position continuity)
                self._lost.append((t.person_id, t.box, t.last_seen_ms))
        self.tracks = keep
        self._lost = [l for l in self._lost if pkt.t_ms - l[2] <= self.cfg.continuity_ms]
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
        """Session identity as in the live-tested MVP (f251ec0): every person keeps a small
        in-memory face gallery for the session (deleted at session end), so a person whose
        track briefly breaks is recognised as THEMSELF within a few frames instead of being
        treated as an unknown face (which is what blurred bystanders in later versions)."""
        cfg = self.cfg
        live_bound = {t.person_id for t in self.tracks if t.person_id and t.missed == 0}
        for t in self.tracks:
            if t.det is None:
                continue
            good = self._good(t.det, pkt.bgr.shape)
            p = self.registry.get(t.person_id)
            if p is not None:
                p.last_seen_ms = pkt.t_ms
                if good and (len(p.gallery) < 3 or t.age % cfg.gallery_every == 0):
                    f = self.feature(pkt.bgr, t.det)
                    own = max((cosine(f, g) for g in p.gallery), default=1.0)
                    # A real ID swap = this face now clearly matches a DIFFERENT known person.
                    # Low similarity to everyone is just a bad angle: keep the identity.
                    other = max((max(cosine(f, g) for g in q.gallery) for q in self.registry.persons.values()
                                 if q.person_id != p.person_id and q.gallery), default=-1.0)
                    if own < cfg.recheck_sim and other >= cfg.t_match:
                        t.swap_count += 1
                        if t.swap_count >= cfg.recheck_votes:
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

            # pending track: someone we know (returning / track broke), or someone new?
            t.pending_frames += 1
            if t.pending_frames > cfg.pending_timeout:
                t.status = IdentityStatus.AMBIGUOUS_MATCH
            if self._overlaps_tracked_person(t):
                # A second detection on top of someone already tracked (e.g. a hand over the
                # eyes detected as a "face"). Never make it a new person — that created ghost
                # identities in live tests (a protected ghost then shielded everyone as "checking").
                continue
            pid = self._continuity(t, pkt, live_bound)
            if pid is not None:
                self._bind(pkt, t, self.registry.get(pid), IdentityStatus.MATCHED, -1.0, events,
                           method="position_continuity")
                live_bound.add(pid)
                continue
            if not good:
                # Small / turned faces never give a clean sample. If nobody protected is
                # unaccounted for, they can't be a protected person: give them an ID so they
                # can still use gestures (their gallery fills in once a clean frame arrives).
                protected_missing = any(q.protected and q.person_id not in live_bound
                                        for q in self.registry.persons.values())
                if not protected_missing and t.pending_frames >= 10:
                    person = self.registry.new_person(pkt.t_ms)
                    self._bind(pkt, t, person, IdentityStatus.CONFIRMED_NEW, -1.0, events)
                    live_bound.add(person.person_id)
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
                person.add_feature(f)
                self._bind(pkt, t, person, IdentityStatus.CONFIRMED_NEW, best, events)
            else:
                person = self.registry.get(vote)
                person.add_feature(f)
                self._bind(pkt, t, person, IdentityStatus.MATCHED, best, events)
            live_bound.add(person.person_id)

    def _overlaps_tracked_person(self, t: Track) -> bool:
        return any(o is not t and o.person_id and o.missed == 0 and
                   (_iou(t.box, o.box) > 0.2 or _center_dist(t.box, o.box) < 0.5 * max(o.box[2], o.box[3]))
                   for o in self.tracks)

    def _continuity(self, t: Track, pkt: FramePacket, live_bound: set):
        """A face that appears where a known person's track just broke (still coasting, or lost
        <3 s ago) is that person — no waiting for a clean frontal frame. This is what stops a
        bystander being shielded as "checking…" when their tracking flickers.

        Safety: re-binding to a PROTECTED person is always allowed (keeps them blurred). Re-binding
        to an unprotected person is refused if someone protected is missing and this face
        resembles them, so a returning protected person can't inherit a bystander's identity."""
        cands = [(o.person_id, o.box) for o in self.tracks if o is not t and o.person_id and o.missed > 0]
        cands += [(pid, box) for pid, box, _ in self._lost]
        best, best_d = None, None
        for pid, box in cands:
            if pid in live_bound or self.registry.get(pid) is None:
                continue
            d = _center_dist(t.box, box)
            if (_iou(t.box, box) > 0.2 or d < 0.6 * max(box[2], box[3])) and (best_d is None or d < best_d):
                best, best_d = pid, d
        if best is None:
            return None
        person = self.registry.get(best)
        if person.protected or t.det is None:
            return best if person.protected else None
        missing = [q for q in self.registry.persons.values()
                   if q.protected and q.gallery and q.person_id not in live_bound]
        if missing:
            f = self.feature(pkt.bgr, t.det)
            if max(max(cosine(f, g) for g in q.gallery) for q in missing) >= self.cfg.t_new:
                return None  # could be the missing protected person: decide by face, not position
        return best

    def _bind(self, pkt, t: Track, person, status: IdentityStatus, score: float, events: list,
              method: str = "face") -> None:
        if status == IdentityStatus.MATCHED:
            # the same person can't also be a lingering lost box elsewhere
            self.tracks = [o for o in self.tracks if o is t or o.person_id != person.person_id]
            self._lost = [l for l in self._lost if l[0] != person.person_id]
            events.append(self._event(pkt, "PERSON_MATCHED", person.person_id,
                                      details={"track_id": t.track_id, "protected": person.protected,
                                               "score": round(score, 3), "method": method}))
        else:
            events.append(self._event(pkt, "PERSON_NEW", person.person_id,
                                      details={"track_id": t.track_id, "best_protected": round(score, 2)}))
        person.last_seen_ms = pkt.t_ms
        t.person_id, t.status = person.person_id, status
        t.vote_pid, t.vote_count, t.swap_count = None, 0, 0

    def _maintain_protected(self, pkt, t: Track, p, good: bool, live_bound: set, events: list) -> None:
        """Enrol (first samples) and maintain the gallery of a person who asked for blur."""
        cfg = self.cfg
        enrolling = len(p.gallery) < cfg.enroll_samples
        if not good or not (enrolling and t.age % 3 == 0 or t.age % cfg.gallery_every == 0):
            return
        f = self.feature(pkt.bgr, t.det)
        if not p.gallery:
            p.add_feature(f)
            events.append(self._event(pkt, "PROTECTED_ENROLLED", p.person_id, details={"track_id": t.track_id}))
            return
        own = max(cosine(f, g) for g in p.gallery)
        other = max((max(cosine(f, g) for g in q.gallery) for q in self.registry.persons.values()
                     if q.person_id != p.person_id and q.protected and q.gallery), default=-1.0)
        if own < cfg.recheck_sim and other >= cfg.t_match:
            t.swap_count += 1
            if t.swap_count >= cfg.recheck_votes:  # consistently another protected person: re-verify
                events.append(self._event(pkt, "IDENTITY_RECHECK", p.person_id,
                                          details={"track_id": t.track_id, "own_sim": round(own, 2),
                                                   "other_sim": round(other, 2)}))
                live_bound.discard(t.person_id)
                t.person_id, t.status = None, IdentityStatus.IDENTITY_PENDING
                t.vote_pid, t.vote_count, t.pending_frames, t.swap_count = None, 0, 0, 0
            return
        if own >= cfg.recheck_sim:
            t.swap_count = 0
        if own >= 0.5 or (enrolling and own >= cfg.t_match):
            p.add_feature(f)

    def _forget_departed_visible(self) -> None:
        """People who never asked for blur (or consented) leave no record once they're gone."""
        bound = {t.person_id for t in self.tracks if t.person_id}
        for pid in [pid for pid, q in self.registry.persons.items() if not q.protected and pid not in bound]:
            self.registry.remove(pid)
            self.gestures.pop(pid, None)

    @property
    def _face_every_frame(self) -> bool:
        return bool(getattr(self.signals, "supports_heavy", False))

    def _signals(self, pkt: FramePacket, heavy: bool = True) -> dict:
        """Landmark evidence. Failure = no evidence (never unshields, never blurs)."""
        if self.signals is None:
            return {"faces": [], "hands": [], "heads": []}
        self._sig_n += 1
        if self.signals_every > 1 and self._sig_n % self.signals_every:
            return self._sig_last
        try:
            if self._face_every_frame:
                self._sig_last = self.signals(pkt.bgr, pkt.t_ms, heavy=heavy)
            else:
                self._sig_last = self.signals(pkt.bgr, pkt.t_ms)
        except Exception:
            self._sig_last = {"faces": [], "hands": [], "heads": []}
        return self._sig_last

    def _follow_heads(self, pkt: FramePacket, sig: dict) -> None:
        """Face lost (profile, looking away, hand over face)? Follow the pose-estimated head
        instead, so a protected person stays blurred while turned sideways.

        Guard rails (from a real-footage bug where a lost track jumped onto a friend's head):
        a head that belongs to a currently visible face is never taken; the head must overlap
        where the face was last seen; the box moves at most a fraction of its size per frame."""
        heads = sig.get("heads", [])
        if not heads:
            return
        live = [t.box for t in self.tracks if t.missed == 0]

        def owned_by_visible_face(hb) -> bool:
            hx, hy = _center(hb)
            return any(x - 0.1 * w <= hx <= x + 1.1 * w and y - 0.2 * h <= hy <= y + 1.1 * h for x, y, w, h in live)

        free = [i for i, hd in enumerate(heads) if not owned_by_visible_face(hd["box"])]
        used = set()
        for t in sorted((t for t in self.tracks if t.missed > 0), key=lambda t: t.missed):
            size = max(t.box[2], t.box[3])
            cx, cy = _center(t.box)
            best, best_d = None, 0.6 * size
            for i in free:
                if i in used or _iou(heads[i]["box"], t.box) <= 0.05:
                    continue
                hx, hy = _center(heads[i]["box"])
                d = float(np.hypot(hx - cx, hy - cy))
                if d < best_d:
                    best, best_d = i, d
            if best is None:
                continue
            used.add(best)
            hb = heads[best]["box"]
            hx, hy = _center(hb)
            step = 0.35 * size  # limit per-frame movement
            d = max(float(np.hypot(hx - cx, hy - cy)), 1e-6)
            k = min(1.0, step / d)
            nx, ny = cx + (hx - cx) * k, cy + (hy - cy) * k
            # never shrink below the last face box
            w, h = max(hb[2], t.box[2]), max(hb[3], t.box[3])
            t.box = (nx - w / 2, ny - h / 2, w, h)
            t.last_seen_ms = pkt.t_ms
            t.head_only = True

    def _map_faces(self, sig: dict) -> dict:
        """Attach face-landmark samples (mouth, eyes) to live identified tracks."""
        mouths, eyes, look = {}, {}, {}
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
                look[t.person_id] = f.get("look_down", 0.0)
        self.mouth_now, self._eyes_now, self._look_down_now = mouths, eyes, look
        return mouths

    def _body_of(self, track: Track, bodies: list) -> Optional[dict]:
        """The pose body whose nose/head sits inside this face's box (one body per face)."""
        x, y, w, h = track.box
        best, best_d = None, None
        for b in bodies:
            p = b.get("nose") or _center(b["box"])
            if x - 0.25 * w <= p[0] <= x + 1.25 * w and y - 0.25 * h <= p[1] <= y + 1.25 * h:
                d = _center_dist(track.box, (p[0], p[1], 0, 0))
                if best_d is None or d < best_d:
                    best, best_d = b, d
        return best

    def _hand_owner_by_body(self, hand: dict, cands: list, bodies: list) -> Optional[Track]:
        """Whose hand is this? Follow it to a body: the hand's wrist must sit on one body's pose
        wrist, and that body's head must be a tracked face. A hand held next to someone ELSE's
        face therefore belongs to its own body, not to the nearest face."""
        wx, wy = hand["pts"][0]
        palm = float(np.linalg.norm(hand["pts"][9] - hand["pts"][0])) or 20.0
        owner_body, best = None, None
        for b in bodies:
            for px, py in b.get("wrists", []):
                d = float(np.hypot(px - wx, py - wy))
                if d <= 1.6 * palm and (best is None or d < best):
                    owner_body, best = b, d
        if owner_body is None:
            return None
        for t in cands:
            if self._body_of(t, bodies) is owner_body:
                return t
        return None

    def _hand_owner(self, hand: dict, cands: list, bodies: Optional[list] = None) -> Optional[Track]:
        """Body-based ownership when pose is available. Without pose: only if ONE person is in
        view (nobody else's hand to confuse) — never "nearest face" with two people."""
        if bodies:
            return self._hand_owner_by_body(hand, cands, bodies)
        live = [t for t in cands if t.missed == 0]
        if len(live) != 1:
            return None
        return self._nearest_face_owner(hand, live)

    def _nearest_face_owner(self, hand: dict, cands: list) -> Optional[Track]:
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
        """Both eyes covered: hand points span both halves of the eye band (live-tested MVP rule)."""
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
        bodies = [b for b in sig.get("heads", []) if "wrists" in b]  # pose bodies (whose hand is whose)
        self.bodies_now = {}
        for t in cands:
            b = self._body_of(t, bodies)
            if b is not None and b.get("body"):
                self.bodies_now[t.person_id] = b["body"]
        peace_owner = set()
        for hd in sig["hands"]:
            # a hand resting on any face (touching, scratching) is never a consent sign
            on_face = any(t.box[0] <= hd["c"][0] <= t.box[0] + t.box[2] and t.box[1] <= hd["c"][1] <= t.box[1] + t.box[3]
                          for t in self.tracks)
            if hd["peace"] and not on_face:
                owner = self._hand_owner(hd, cands, bodies)
                if owner is not None:
                    peace_owner.add(owner.person_id)
        eyes_now = getattr(self, "_eyes_now", {})
        look_now = getattr(self, "_look_down_now", {})

        def held(since, last, active):
            """Hold timer that tolerates brief detector flicker (<350 ms) instead of resetting."""
            if active:
                return (since or now), now
            if since is not None and now - last <= 350:
                return since, last
            return None, last

        for t in cands:
            pid = t.person_id
            g = self.gestures.setdefault(pid, GestureState())
            g.eyes_closed = eyes_now.get(pid, 0.0)
            g.covered = self._covers_eyes(t, sig["hands"])
            g.peace = pid in peace_owner
            if g.covered:  # hands over the face hide it from the detector: keep the track alive
                t.last_seen_ms = now
            # "Eyes closed" must not fire when someone just looks DOWN (e.g. at the laptop
            # keyboard below the webcam) — MediaPipe's eyeLookDown separates the two.
            closed = (g.eyes_closed >= cfg.eyes_closed_thr and t.missed == 0
                      and (look_now.get(pid, 0.0) < cfg.look_down_veto or g.eyes_closed >= 0.9))
            g.eyes_since, g.eyes_last = held(g.eyes_since, g.eyes_last, closed)
            g.cover_since, g.cover_last = held(g.cover_since, g.cover_last, g.covered)
            g.peace_since, g.peace_last = held(g.peace_since, g.peace_last, g.peace)
            if now < g.cooldown_until:
                continue
            p = self.registry.get(pid)
            conf = self.confirm if self.confirm and now < self.confirm["until"] else None
            eyes_hold = 500 if conf and conf["intent"] == "DENY" else cfg.eyes_hold_ms
            cover_hold = 500 if conf and conf["intent"] == "DENY" else cfg.cover_hold_ms
            peace_hold = 300 if conf and conf["intent"] == "ALLOW" else cfg.peace_hold_ms
            if not p.protected:
                which = None
                if g.eyes_since is not None and now - g.eyes_since >= eyes_hold:
                    which = "eyes_closed"
                elif g.cover_since is not None and now - g.cover_since >= cover_hold:
                    which = "hands_over_eyes"
                if which:
                    self._protect(pkt, pid, "VOICE+GESTURE" if conf else "GESTURE",
                                  {"gesture": which, "confirmed_voice": bool(conf)}, events)
                    g.cooldown_until = now + cfg.gesture_cooldown_ms
                    g.eyes_since = g.cover_since = None
                    if conf and conf["intent"] == "DENY":
                        self.confirm = None
            elif g.peace_since is not None and now - g.peace_since >= peace_hold:
                self._unprotect(pkt, pid, "VOICE+GESTURE" if conf else "GESTURE",
                                {"gesture": "peace_sign", "confirmed_voice": bool(conf)}, events)
                g.cooldown_until = now + cfg.gesture_cooldown_ms
                g.peace_since = None
                if conf and conf["intent"] == "ALLOW":
                    self.confirm = None
            if self.strict and not p.protected and p.privacy != Privacy.VISIBLE_BY_CONSENT \
                    and g.peace_since is not None and now - g.peace_since >= cfg.peace_hold_ms:
                p.privacy = Privacy.VISIBLE_BY_CONSENT  # strict mode: explicit opt-in to be shown
                events.append(self._event(pkt, "PRIVACY_RELEASED", pid, "GESTURE", {"gesture": "peace_sign", "mode": "strict_opt_in"}))
                g.cooldown_until = now + cfg.gesture_cooldown_ms
                g.peace_since = None

    def _decide_regions(self, pkt: FramePacket):
        regions = []
        shielded_any = False
        unresolved = pkt.t_ms < self.unresolved_until_ms
        bound = {t.person_id for t in self.tracks if t.person_id}
        live_bound = {t.person_id for t in self.tracks if t.person_id and t.missed == 0}
        # protected person not in the frame at all -> any unknown face could be them. A protected
        # record with NO face samples can never be re-identified (e.g. a ghost from a bad detection),
        # so it only counts for 10 s after it was last seen instead of shielding newcomers forever.
        protected_gone = any(p.protected and p.person_id not in bound and
                             (p.gallery or pkt.t_ms - p.last_seen_ms < 10_000)
                             for p in self.registry.persons.values())
        # protected person only briefly undetected -> an unknown face far from everyone could be
        # them "teleporting" (fast move), but an unknown face sitting where a known VISIBLE person
        # just was is that person's own track re-forming — never blur a bystander for that.
        protected_flicker = any(p.protected and p.person_id in bound and p.person_id not in live_bound
                                for p in self.registry.persons.values())
        visible_boxes = [o.box for o in self.tracks if o.person_id and not self.registry.get(o.person_id).protected]

        def near_visible_person(box) -> bool:
            return any(_iou(box, vb) > 0.2 or _center_dist(box, vb) < 0.6 * max(vb[2], vb[3]) for vb in visible_boxes)

        for t in self.tracks:
            p = self.registry.get(t.person_id)
            if p is not None:
                # strict policy: anyone without explicit consent is blurred
                shield = p.protected or (self.strict and p.privacy != Privacy.VISIBLE_BY_CONSENT)
            else:
                shield = protected_gone or (protected_flicker and not near_visible_person(t.box)) or self.strict
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
                "consent_state": p.consent_state if p else "UNCERTAIN",
                "shielded": t.shielded,
                "coasting": t.missed > 0,
                "head_only": t.head_only,
                "box": [round(v) for v in t.box],
                "mouth_open": round(self.mouth_now[t.person_id], 3) if t.person_id in self.mouth_now else None,
                "body": [round(v) for v in self.bodies_now[t.person_id]] if t.person_id in self.bodies_now else None,
                "confirm": (self.confirm or {}).get("intent") if self.confirm and pkt.t_ms < self.confirm["until"] else None,
                "gesture": None if g is None else {
                    "eyes_closed_s": held(g.eyes_since), "cover_s": held(g.cover_since),
                    "peace_s": held(g.peace_since)},
            })
        return out
