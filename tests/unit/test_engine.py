import numpy as np
from backend.app.vision.engine import VisionEngine
from backend.app.consent.speaker import match_speaker
from shared.contracts import (OutputState, PrivacyRequest, RequestAction, RequestOrigin, SpeechTurn)
from tests.unit.fakes import Script, face, face_sig, hand, hand_over_eyes, packet

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
    res, _ = run(e, s, 12, 1)
    a, b = pid_of(res, 100), pid_of(res, 400)
    assert a and b and a != b
    assert res.output_state == OutputState.NORMAL
    assert all(not t["shielded"] for t in res.tracks)

def test_protect_blurs_only_target_in_pixels_and_source_untouched():
    s, e = make()
    s.frame = [face("A", 100, 100), face("B", 400, 100)]
    res, n = run(e, s, 12, 1)
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
    res, n = run(e, s, 12, 1)
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
    res, n = run(e, s, 12, 1)
    protect(e, pid_of(res, 100))
    res, n = run(e, s, 2, n)
    s.frame = []
    res, n = run(e, s, 30, n)
    s.frame = [face("C", 300, 200)]
    first = e.step(packet(n))
    assert first.tracks[0]["shielded"]
    res, n = run(e, s, 12, n + 1)
    t = res.tracks[0]
    assert t["person_id"] and not t["shielded"] and t["identity_status"] == "CONFIRMED_NEW"

def test_unverified_allow_never_unblurs():
    s, e = make()
    s.frame = [face("A", 100, 100)]
    res, n = run(e, s, 12, 1)
    a = pid_of(res, 100)
    protect(e, a)
    protect(e, a, eid="e2", origin=RequestOrigin.VOICE, action=RequestAction.REQUEST_ALLOW, verified=False)
    res, n = run(e, s, 3, n)
    assert res.tracks[0]["shielded"] and e.registry.get(a).protected

def test_unverified_protect_does_not_target_random_person_but_shields_briefly():
    s, e = make()
    s.frame = [face("A", 100, 100), face("B", 400, 100)]
    res, n = run(e, s, 12, 1)
    protect(e, None, eid="u1", origin=RequestOrigin.VOICE, action=RequestAction.UNRESOLVED, verified=False)
    res = e.step(packet(n))
    assert not e.registry.any_protected()
    assert all(t["shielded"] for t in res.tracks)  # temporary unresolved shield
    assert any(ev["type"] == "REQUEST_UNRESOLVED" for ev in res.events)

def test_duplicate_event_ids_ignored():
    s, e = make()
    s.frame = [face("A", 100, 100)]
    res, n = run(e, s, 12, 1)
    a = pid_of(res, 100)
    protect(e, a, eid="same"); protect(e, a, eid="same")
    res = e.step(packet(n))
    assert sum(ev["type"] == "PRIVACY_ACTIVATED" for ev in res.events) == 1

def test_detector_exception_fails_closed_without_source_pixels():
    s, e = make()
    s.frame = [face("A", 100, 100)]
    run(e, s, 12, 1)
    s.fail = True
    pkt = packet(10)
    res = e.step(pkt)
    assert res.output_state == OutputState.ERROR
    assert not np.array_equal(res.protected_bgr[:, :, 0], pkt.bgr[:, :, 0])
    assert len(np.unique(res.protected_bgr[:50, :50])) <= 2  # flat slate, no image content

def test_protected_track_coasts_shielded_on_missed_detection():
    s, e = make()
    s.frame = [face("A", 100, 100)]
    res, n = run(e, s, 12, 1)
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
    e = VisionEngine("s_test", s.detect, s.feature, signals=bad_mouth)
    s.frame = [face("A", 100, 100)]
    res, n = run(e, s, 12, 1)
    assert res.output_state == OutputState.NORMAL and res.tracks[0]["person_id"]


def test_single_visible_face_with_still_lips_is_not_blamed_for_offscreen_voice():
    turn = SpeechTurn("s_test", "t1", 300, 1500, "please blur me", True)
    hist = [(t * 66, ("person_001",), {"person_001": 0.02}) for t in range(30)]
    m = match_speaker(turn, hist)
    assert m.status == "OFFSCREEN" and m.person_id is None



def make_sig():
    s = Script()
    return s, VisionEngine("s_test", s.detect, s.feature, signals=s.signals)

def two_people(s, e):
    s.frame = [face("A", 100, 100), face("B", 400, 100)]
    res, n = run(e, s, 12, 1)
    return pid_of(res, 100), pid_of(res, 400), n

def test_eyes_closed_two_seconds_blurs_only_that_person_and_blink_does_not():
    s, e = make_sig()
    a, b, n = two_people(s, e)
    s.sig = {"faces": [face_sig(100, 100, eyes_closed=0.9), face_sig(400, 100)], "hands": []}
    res, n = run(e, s, 8, n)                     # ~0.5 s blink-length closure
    assert not e.registry.get(a).protected
    s.sig = {"faces": [face_sig(100, 100), face_sig(400, 100)], "hands": []}
    res, n = run(e, s, 2, n)
    s.sig = {"faces": [face_sig(100, 100, eyes_closed=0.9), face_sig(400, 100)], "hands": []}
    res, n = run(e, s, 33, n)                    # ~2.1 s
    assert e.registry.get(a).protected and not e.registry.get(b).protected
    assert any(ev["type"] == "PRIVACY_ACTIVATED" and ev["details"].get("gesture") == "eyes_closed"
               for ev in e.event_log)

def test_hands_over_eyes_blurs_even_if_detector_loses_the_face():
    s, e = make_sig()
    a, b, n = two_people(s, e)
    s.frame = [face("B", 400, 100)]              # A's face hidden by hands
    s.sig = {"faces": [face_sig(400, 100)], "hands": [hand_over_eyes(100, 100)]}
    res, n = run(e, s, 26, n)                    # ~1.7 s
    assert e.registry.get(a).protected and not e.registry.get(b).protected

def test_peace_sign_unblurs_only_its_owner():
    s, e = make_sig()
    a, b, n = two_people(s, e)
    for pid in (a, b):
        e.submit(PrivacyRequest("s_test", "p" + pid, RequestOrigin.MANUAL_TEST, None, pid, RequestAction.PROTECT, 0, True))
    res, n = run(e, s, 2, n)
    s.sig = {"faces": [], "hands": [hand(470, 280, peace=True)]}   # B's hand, next to B's face
    res, n = run(e, s, 17, n)                    # ~1.1 s
    assert not e.registry.get(b).protected, "B's own peace sign should unblur B"
    assert e.registry.get(a).protected, "B's peace sign must never unblur A"
    assert any(ev["type"] == "PRIVACY_RELEASED" and ev["person_id"] == b for ev in e.event_log)

def test_peace_sign_between_two_faces_is_ignored():
    s, e = make_sig()
    a, b, n = two_people(s, e)
    e.submit(PrivacyRequest("s_test", "pa", RequestOrigin.MANUAL_TEST, None, a, RequestAction.PROTECT, 0, True))
    res, n = run(e, s, 2, n)
    s.sig = {"faces": [], "hands": [hand(325, 150, peace=True)]}   # equidistant
    res, n = run(e, s, 30, n)
    assert e.registry.get(a).protected

def test_brief_peace_sign_does_not_unblur():
    s, e = make_sig()
    a, b, n = two_people(s, e)
    e.submit(PrivacyRequest("s_test", "pa", RequestOrigin.MANUAL_TEST, None, a, RequestAction.PROTECT, 0, True))
    res, n = run(e, s, 2, n)
    s.sig = {"faces": [], "hands": [hand(170, 280, peace=True)]}
    res, n = run(e, s, 8, n)                     # ~0.5 s
    assert e.registry.get(a).protected

def test_voice_unprotect_request_applies():
    s, e = make_sig()
    a, b, n = two_people(s, e)
    e.submit(PrivacyRequest("s_test", "pa", RequestOrigin.MANUAL_TEST, None, a, RequestAction.PROTECT, 0, True))
    res, n = run(e, s, 2, n)
    e.submit(PrivacyRequest("s_test", "ua", RequestOrigin.VOICE, "t9", a, RequestAction.UNPROTECT, 0, True))
    res = e.step(packet(n))
    assert not e.registry.get(a).protected and not res.tracks[0]["shielded"]

def test_bad_frames_and_edge_faces_do_not_create_duplicate_people():
    s, e = make_sig()
    a, b, n = two_people(s, e)
    s.bad_feature_for = {"A"}                    # A turns away / blurs for a while
    res, n = run(e, s, 60, n)
    s.bad_feature_for = set()
    s.frame = [face("A", 100, 100), face("B", 400, 100), face("C", 250, 0)]  # partial face at top edge
    res, n = run(e, s, 30, n)
    assert len(e.registry.persons) == 2, [p for p in e.registry.persons]


def test_real_track_swap_is_rechecked():
    s, e = make_sig()
    a, b, n = two_people(s, e)
    s.frame = [face("B", 100, 100)]          # A's track position now shows B's face (B left right side)
    res, n = run(e, s, 60, n)
    assert any(ev["type"] == "IDENTITY_RECHECK" and ev["person_id"] == a for ev in e.event_log)
    assert pid_of(res, 100) == b and len(e.registry.persons) == 2


def _hand_pts(fingers_up):
    """Synthetic upright hand: wrist at (0,0) pixel space flipped (y up = negative)."""
    import numpy as np
    pts = np.zeros((21, 2), np.float32)
    pts[0] = (0, 0)
    bases = {1: -30, 5: -15, 9: 0, 13: 15, 17: 28}
    for mcp, x in bases.items():
        if mcp == 1:
            pts[1:5] = [(x, -15), (x - 8, -25), (x - 14, -33), (x - 18, -40)]
            continue
        pts[mcp] = (x, -60)
        name = {5: "index", 9: "middle", 13: "ring", 17: "pinky"}[mcp]
        if name in fingers_up:
            lean = -6 if name == "index" else 6
            pts[mcp + 1:mcp + 4] = [(x + lean * 0.4, -85), (x + lean * 0.7, -100), (x + lean, -115)]
        else:  # curled back toward palm
            pts[mcp + 1:mcp + 4] = [(x, -78), (x, -66), (x, -55)]
    return pts + np.array([300, 300], np.float32)

def test_peace_sign_geometry():
    from backend.app.vision.landmarks import is_peace
    assert is_peace(_hand_pts({"index", "middle"}))
    assert not is_peace(_hand_pts({"index"}))                       # pointing
    assert not is_peace(_hand_pts({"index", "middle", "ring", "pinky"}))  # open palm
    assert not is_peace(_hand_pts(set()))                           # fist

def test_peace_hand_resting_on_a_face_is_ignored():
    s, e = make_sig()
    a, b, n = two_people(s, e)
    e.submit(PrivacyRequest("s_test", "pa", RequestOrigin.MANUAL_TEST, None, a, RequestAction.PROTECT, 0, True))
    res, n = run(e, s, 2, n)
    s.sig = {"faces": [], "hands": [hand(150, 150, peace=True)]}   # palm inside A's face box
    res, n = run(e, s, 30, n)
    assert e.registry.get(a).protected


def test_stalled_landmarker_never_blocks_the_frame_loop_and_restarts():
    import threading, time
    from backend.app.vision import landmarks as L
    gate = threading.Event()
    calls = {"n": 0}

    class FakeLM:
        last_ts = -1

    orig_detect, orig_lm = L.Signals._detect, L._Landmarkers
    def detect(lm, bgr, t, do_hands):
        calls["n"] += 1
        if calls["n"] == 2:
            gate.wait(10)  # simulate MediaPipe hanging on the 2nd frame
        return [], []
    L.Signals._detect = staticmethod(detect)
    L._Landmarkers = lambda *a: FakeLM()
    try:
        sg = L.Signals("models", budget_ms=50, restart_ms=300)
        img = packet(1).bgr
        assert "stalled" not in sg(img, 0)
        t0 = time.monotonic(); r = sg(img, 33)
        assert r.get("stalled") and time.monotonic() - t0 < 0.3     # returned within budget
        assert sg(img, 66).get("stalled")                             # still stuck: skip, don't queue
        time.sleep(0.35)
        assert sg(img, 99).get("stalled") and sg.restarts == 1        # abandoned + fresh worker
        assert "stalled" not in sg(img, 132)                          # new worker serves frames
    finally:
        gate.set()
        L.Signals._detect, L._Landmarkers = orig_detect, orig_lm
