import numpy as np
from backend.app.vision.engine import VisionEngine
from backend.app.consent.speaker import match_speaker
from shared.contracts import (OutputState, PrivacyRequest, RequestAction, RequestOrigin, SpeechTurn)
from tests.unit.fakes import Script, face, packet

def make():
    s = Script()
    return s, VisionEngine("s_test", s.detect, s.feature)

def run(e, s, frames, start):
    res = None
    for i in range(start, start + frames):
        res = e.step(packet(i))
    return res, start + frames

def pid_of(res, x):
    return next(t["person_id"] for t in res.tracks if t["box"][0] == x)

def protect(e, pid, eid="e1", origin=RequestOrigin.MANUAL_TEST, action=RequestAction.PROTECT, verified=True):
    e.submit(PrivacyRequest("s_test", eid, origin, None, pid, action, 0, verified))

def region_changed(src, out, x, y, size=100):
    return not np.array_equal(src[y:y+size, x:x+size], out[y:y+size, x:x+size])

def test_two_faces_get_distinct_ids_and_stay_visible():
    s, e = make()
    s.frame = [face("A", 100, 100), face("B", 400, 100)]
    res, _ = run(e, s, 6, 1)
    a, b = pid_of(res, 100), pid_of(res, 400)
    assert a and b and a != b
    assert res.output_state == OutputState.NORMAL
    assert all(not t["shielded"] for t in res.tracks)

def test_protect_blurs_only_target_in_pixels_and_source_untouched():
    s, e = make()
    s.frame = [face("A", 100, 100), face("B", 400, 100)]
    res, n = run(e, s, 6, 1)
    a = pid_of(res, 100)
    protect(e, a)
    pkt = packet(n)
    before = pkt.bgr.copy()
    res = e.step(pkt)
    assert np.array_equal(pkt.bgr, before), "source frame mutated"
    assert region_changed(pkt.bgr, res.protected_bgr, 100, 100)
    assert not region_changed(pkt.bgr, res.protected_bgr, 400, 100)
    assert any(ev["type"] == "PRIVACY_ACTIVATED" and ev["person_id"] == a for ev in res.events)

def test_reentry_is_shielded_while_pending_then_matched_protected_and_B_unaffected():
    s, e = make()
    s.frame = [face("A", 100, 100), face("B", 400, 100)]
    res, n = run(e, s, 6, 1)
    a, b = pid_of(res, 100), pid_of(res, 400)
    protect(e, a)
    res, n = run(e, s, 2, n)
    s.frame = [face("B", 400, 100)]                 # A leaves
    res, n = run(e, s, 30, n)
    assert all(t["person_id"] != a for t in res.tracks)
    s.frame = [face("B", 400, 100), face("A", 200, 300)]  # A returns elsewhere
    leaked = 0
    for i in range(n, n + 8):
        pkt = packet(i)
        r = e.step(pkt)
        if not region_changed(pkt.bgr, r.protected_bgr, 200, 300):
            leaked += 1
        assert not region_changed(pkt.bgr, r.protected_bgr, 400, 100), "B wrongly blurred"
    assert leaked == 0, f"{leaked} unblurred frames of protected A during re-entry"
    assert pid_of(r, 200) == a and pid_of(r, 400) == b

def test_new_stranger_shielded_while_protected_absent_then_visible_when_confirmed_new():
    s, e = make()
    s.frame = [face("A", 100, 100)]
    res, n = run(e, s, 6, 1)
    protect(e, pid_of(res, 100))
    res, n = run(e, s, 2, n)
    s.frame = []
    res, n = run(e, s, 30, n)
    s.frame = [face("C", 300, 200)]
    first = e.step(packet(n))
    assert first.tracks[0]["shielded"]
    res, n = run(e, s, 6, n + 1)
    t = res.tracks[0]
    assert t["person_id"] and not t["shielded"] and t["identity_status"] == "CONFIRMED_NEW"

def test_allow_and_unverified_requests_never_unblur():
    s, e = make()
    s.frame = [face("A", 100, 100)]
    res, n = run(e, s, 6, 1)
    a = pid_of(res, 100)
    protect(e, a)
    protect(e, a, eid="e2", origin=RequestOrigin.VOICE, action=RequestAction.REQUEST_ALLOW, verified=False)
    res, n = run(e, s, 3, n)
    assert res.tracks[0]["shielded"] and e.registry.get(a).protected

def test_unverified_protect_does_not_target_random_person_but_shields_briefly():
    s, e = make()
    s.frame = [face("A", 100, 100), face("B", 400, 100)]
    res, n = run(e, s, 6, 1)
    protect(e, None, eid="u1", origin=RequestOrigin.VOICE, action=RequestAction.UNRESOLVED, verified=False)
    res = e.step(packet(n))
    assert not e.registry.any_protected()
    assert all(t["shielded"] for t in res.tracks)  # temporary unresolved shield
    assert any(ev["type"] == "REQUEST_UNRESOLVED" for ev in res.events)

def test_duplicate_event_ids_ignored():
    s, e = make()
    s.frame = [face("A", 100, 100)]
    res, n = run(e, s, 6, 1)
    a = pid_of(res, 100)
    protect(e, a, eid="same"); protect(e, a, eid="same")
    res = e.step(packet(n))
    assert sum(ev["type"] == "PRIVACY_ACTIVATED" for ev in res.events) == 1

def test_detector_exception_fails_closed_without_source_pixels():
    s, e = make()
    s.frame = [face("A", 100, 100)]
    run(e, s, 3, 1)
    s.fail = True
    pkt = packet(10)
    res = e.step(pkt)
    assert res.output_state == OutputState.ERROR
    assert not np.array_equal(res.protected_bgr[:, :, 0], pkt.bgr[:, :, 0])
    assert len(np.unique(res.protected_bgr[:50, :50])) <= 2  # flat slate, no image content

def test_protected_track_coasts_shielded_on_missed_detection():
    s, e = make()
    s.frame = [face("A", 100, 100)]
    res, n = run(e, s, 6, 1)
    protect(e, pid_of(res, 100))
    res, n = run(e, s, 2, n)
    s.frame = []                     # detector misses A for a few frames
    res = e.step(packet(n))
    assert res.tracks and res.tracks[0]["coasting"] and res.tracks[0]["shielded"]

def test_speaker_binding_single_candidate_vs_ambiguous():
    s, e = make()
    s.frame = [face("A", 100, 100)]
    res, n = run(e, s, 20, 1)
    a = pid_of(res, 100)
    turn = SpeechTurn("s_test", "t1", 500, 1200, "please blur me", True)
    m = match_speaker(turn, e.visibility_history())
    assert m.status == "MATCHED" and m.person_id == a and m.method == "single_candidate"
    s.frame = [face("A", 100, 100), face("B", 400, 100)]
    res, n = run(e, s, 20, n)
    turn2 = SpeechTurn("s_test", "t2", (n - 10) * 66, (n - 2) * 66, "please blur me", True)
    m2 = match_speaker(turn2, e.visibility_history())
    assert m2.status == "AMBIGUOUS" and m2.person_id is None
    m3 = match_speaker(SpeechTurn("s_test", "t3", 10**7, 10**7 + 500, "x", True), e.visibility_history())
    assert m3.status == "UNKNOWN" and m3.person_id is None


def _hist(n, a_open, b_open):
    return [(t * 66, ("person_001", "person_002"), {"person_001": a_open(t), "person_002": b_open(t)})
            for t in range(n)]

def test_lip_motion_picks_the_moving_mouth_and_rejects_ties():
    import math
    talk = lambda t: 0.05 + 0.12 * abs(math.sin(t * 1.3))
    still = lambda t: 0.02
    turn = SpeechTurn("s_test", "t1", 300, 1500, "please blur me", True)
    m = match_speaker(turn, _hist(30, talk, still))
    assert m.status == "MATCHED" and m.person_id == "person_001" and m.method == "lip_motion_heuristic"
    m = match_speaker(turn, _hist(30, still, talk))
    assert m.person_id == "person_002"
    both = match_speaker(turn, _hist(30, talk, talk))      # both talking
    assert both.status == "AMBIGUOUS" and both.person_id is None
    none = match_speaker(turn, _hist(30, still, still))    # offscreen voice, nobody moving
    assert none.status == "AMBIGUOUS" and none.person_id is None
    no_mouth = match_speaker(turn, [(t * 66, ("person_001", "person_002")) for t in range(30)])
    assert no_mouth.person_id is None

def test_mouth_failure_does_not_break_privacy_path():
    s = Script()
    def bad_mouth(bgr, t):
        raise RuntimeError("landmarker down")
    e = VisionEngine("s_test", s.detect, s.feature, mouth=bad_mouth)
    s.frame = [face("A", 100, 100)]
    res, n = run(e, s, 6, 1)
    assert res.output_state == OutputState.NORMAL and res.tracks[0]["person_id"]


def test_single_visible_face_with_still_lips_is_not_blamed_for_offscreen_voice():
    turn = SpeechTurn("s_test", "t1", 300, 1500, "please blur me", True)
    hist = [(t * 66, ("person_001",), {"person_001": 0.02}) for t in range(30)]
    m = match_speaker(turn, hist)
    assert m.status == "OFFSCREEN" and m.person_id is None
