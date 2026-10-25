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

def test_unverified_protect_does_not_target_or_blur_anyone():
    s, e = make()
    s.frame = [face("A", 100, 100), face("B", 400, 100)]
    res, n = run(e, s, 12, 1)
    protect(e, None, eid="u1", origin=RequestOrigin.VOICE, action=RequestAction.UNRESOLVED, verified=False)
    res = e.step(packet(n))
    assert not e.registry.any_protected()
    assert not any(t["shielded"] for t in res.tracks)  # unclear speaker: nobody blurred (live feedback)
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
    s.sig = {"faces": [], "hands": [hand(470, 280, peace=True)],    # B's hand, next to B's face
             "heads": [body_of(100, 100), body_of(400, 100, wrist=(460, 270))]}
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

def test_bad_frames_do_not_create_duplicate_people():
    s, e = make_sig()
    a, b, n = two_people(s, e)
    s.bad_feature_for = {"A"}                    # A turns away / blurs for a while
    res, n = run(e, s, 60, n)
    assert len(e.registry.persons) == 2 and pid_of(res, 100) == a


def test_bystander_never_blurred_when_their_track_reforms_while_protected_flickers():
    """Regression for the live bug: B got blurred while A (protected) was briefly undetected."""
    s, e = make_sig()
    a, b, n = two_people(s, e)
    e.submit(PrivacyRequest("s_test", "pa", RequestOrigin.MANUAL_TEST, None, a, RequestAction.PROTECT, 0, True))
    res, n = run(e, s, 20, n)
    for i in range(n, n + 40):
        # A's detection flickers every other frame; B's box jumps slightly so its track can re-form
        s.frame = ([face("A", 100, 100)] if i % 2 else []) + [face("B", 400 + (i % 3) * 30, 100)]
        pkt = packet(i); r = e.step(pkt)
        assert not region_changed(pkt.bgr, r.protected_bgr, 430, 130, 40), f"B blurred at frame {i - n}"


def test_visible_track_that_is_really_a_protected_person_gets_blurred():
    s, e = make_sig()
    a, b, n = two_people(s, e)
    e.submit(PrivacyRequest("s_test", "pb", RequestOrigin.MANUAL_TEST, None, b, RequestAction.PROTECT, 0, True))
    res, n = run(e, s, 20, n)                  # B enrolled while protected
    s.frame = [face("B", 100, 100)]            # B's face now shows up on A's (visible) track
    res, n = run(e, s, 40, n)
    assert pid_of(res, 100) == b and res.tracks[0]["shielded"]
    assert any(ev["type"] == "IDENTITY_RECHECK" for ev in e.event_log)


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
    def detect(lm, bgr, t, do_hands, do_pose=None):
        calls["n"] += 1
        if calls["n"] == 2:
            gate.wait(10)  # simulate MediaPipe hanging on the 2nd frame
        return [], [], []
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



def test_session_end_deletes_all_face_data():
    s, e = make_sig()
    a, b, n = two_people(s, e)
    res, n = run(e, s, 20, n)
    assert e.registry.clear_biometrics() > 0
    assert all(len(p.gallery) == 0 for p in e.registry.persons.values())

def test_protect_enrolls_and_consent_deletes_face_data():
    s, e = make_sig()
    a, b, n = two_people(s, e)
    e.submit(PrivacyRequest("s_test", "pa", RequestOrigin.MANUAL_TEST, None, a, RequestAction.PROTECT, 0, True))
    res, n = run(e, s, 20, n)
    assert len(e.registry.get(a).gallery) >= 3
    e.submit(PrivacyRequest("s_test", "ua", RequestOrigin.VOICE, "t", a, RequestAction.UNPROTECT, 0, True))
    res, n = run(e, s, 1, n)
    assert not e.registry.get(a).protected



def test_protected_head_stays_blurred_while_face_is_turned_away_for_long():
    s, e = make_sig()
    e.follow_heads = True                                  # experimental, opt-in
    a, b, n = two_people(s, e)
    e.submit(PrivacyRequest("s_test", "pa", RequestOrigin.MANUAL_TEST, None, a, RequestAction.PROTECT, 0, True))
    res, n = run(e, s, 20, n)
    s.frame = [face("B", 400, 100)]                       # A turns sideways: face detector loses A
    leaked = 0
    for i in range(n, n + 90):                            # ~6 s, head drifting right
        s.sig = {"faces": [], "hands": [], "heads": [{"box": (95 + (i - n) * 0.5, 95, 110, 120)}]}
        pkt = packet(i); r = e.step(pkt)
        tr = [t for t in r.tracks if t["person_id"] == a]
        if not tr or not tr[0]["shielded"]:
            leaked += 1
        else:
            x, y = tr[0]["box"][:2]
            assert region_changed(pkt.bgr, r.protected_bgr, int(x) + 10, int(y) + 10, 60)
    assert leaked == 0
    s.frame = [face("A", 140, 100), face("B", 400, 100)]  # turns back: same track, same person, still blurred
    s.sig = {"faces": [], "hands": [], "heads": []}
    r = e.step(packet(n + 90))
    t = next(t for t in r.tracks if t["person_id"] == a)
    assert t["shielded"] and not t["head_only"]

def test_without_a_head_estimate_lost_face_still_expires():
    s, e = make_sig()
    a, b, n = two_people(s, e)
    s.frame = [face("B", 400, 100)]
    res, n = run(e, s, 30, n)                             # 2 s, no pose head
    assert all(t["person_id"] != a for t in res.tracks)

def test_head_box_from_profile_keypoints():
    import numpy as np
    from backend.app.vision.landmarks import head_box
    pts = np.zeros((33, 2), np.float32); vis = np.zeros(33, np.float32)
    pts[0], pts[8], pts[11], pts[12] = (200, 150), (180, 145), (170, 230), (260, 230)  # nose, one ear, shoulders
    vis[[0, 8, 11, 12]] = 1.0
    x, y, w, h = head_box(pts, vis)
    assert x < 180 < x + w and y < 145 < y + h and w >= 40
    vis[:] = 0
    assert head_box(pts, vis) is None


def _av_case(a_lips, b_lips, voice, n=40):
    """30 fps lips for A/B and a 50 Hz mic envelope over 2.6 s."""
    import numpy as np
    hist = [(t * 33, ("person_001", "person_002"), {"person_001": a_lips(t * 33), "person_002": b_lips(t * 33)})
            for t in range(-150, n + 30)]
    env = [(t, voice(t)) for t in range(-5000, (n + 30) * 33, 20)]
    return hist, env

def test_av_sync_picks_lips_that_follow_the_voice_not_the_laugher():
    import math
    voice = lambda t: 800 * max(0.0, math.sin(t / 90.0)) if 0 <= t <= 1300 else 20.0
    talker = lambda t: 0.03 + 0.00012 * voice(t)                       # lips track loudness
    laugher = lambda t: 0.03 + 0.09 * abs(math.sin(t / 37.0 + 1.0))    # big motion, wrong rhythm
    still = lambda t: 0.03
    turn = SpeechTurn("s_test", "t1", 0, 1300, "please blur me", True)
    hist, env = _av_case(talker, laugher, voice)
    m = match_speaker(turn, hist, env)
    assert m.status == "MATCHED" and m.person_id == "person_001" and m.method == "av_sync"
    hist, env = _av_case(laugher, talker, voice)
    assert match_speaker(turn, hist, env).person_id == "person_002"
    hist, env = _av_case(talker, talker, voice)                          # both "speaking" in sync
    assert match_speaker(turn, hist, env).person_id is None
    hist, env = _av_case(laugher, still, voice)                          # voice from someone offscreen
    assert match_speaker(turn, hist, env).person_id is None

def test_av_single_visible_person_not_blamed_for_offscreen_voice():
    import math
    voice = lambda t: 800 * max(0.0, math.sin(t / 90.0)) if 0 <= t <= 1300 else 20.0
    turn = SpeechTurn("s_test", "t1", 0, 1300, "please blur me", True)
    hist = [(t * 33, ("person_001",), {"person_001": 0.03 + 0.0005 * (t % 3)}) for t in range(-150, 70)]
    env = [(t, voice(t)) for t in range(-5000, 2400, 20)]
    m = match_speaker(turn, hist, env)
    assert m.status == "OFFSCREEN" and m.person_id is None
    hist = [(t * 33, ("person_001",), {"person_001": 0.03 + 0.00012 * voice(t * 33)}) for t in range(-150, 70)]
    assert match_speaker(turn, hist, env).person_id == "person_001"

def test_voice_envelope_is_recorded_on_session_clock():
    import numpy as np
    from tests.unit.test_voice import pipeline
    vp, _ = pipeline()
    loud = (np.ones(2400, np.int16) * 1000).tobytes()                    # 100 ms
    vp._record_envelope(loud, 5000)
    env = vp.audio_envelope()
    assert len(env) == 5 and env[0][0] == 4910 and abs(env[0][1] - 1000) < 1



def test_lost_track_never_jumps_onto_a_visible_friends_head():
    s, e = make_sig()
    a, b, n = two_people(s, e)                          # A at x=100, B at x=400
    s.frame = [face("A", 100, 100)]                     # B's face lost (hand over face)
    heads = [{"box": (95, 95, 110, 120)},               # A's head (A visible)
             {"box": (255, 95, 110, 120)}]              # some head between them, not overlapping B's box
    for i in range(n, n + 10):
        s.sig = {"faces": [], "hands": [], "heads": heads}
        r = e.step(packet(i))
    tb = next(t for t in r.tracks if t["person_id"] == b)
    assert tb["box"][0] > 300, f"B's track drifted to {tb['box']}"
    s.frame = [face("A", 100, 100), face("B", 400, 100)]  # B's face back: same track, same ID
    s.sig = {"faces": [], "hands": [], "heads": []}
    r = e.step(packet(n + 10))
    assert pid_of(r, 400) == b



def test_consent_states_unknown_denied_granted_revoked_uncertain():
    s, e = make_sig()
    a, b, n = two_people(s, e)
    snap = {p["person_id"]: p["consent_state"] for p in e.registry.snapshot()}
    assert snap[a] == "UNKNOWN"
    e.submit(PrivacyRequest("s_test", "1", RequestOrigin.VOICE, "t", a, RequestAction.PROTECT, 0, True)); run(e, s, 1, n)
    assert e.registry.get(a).consent_state == "DENIED"
    e.submit(PrivacyRequest("s_test", "2", RequestOrigin.VOICE, "t", a, RequestAction.UNPROTECT, 0, True)); run(e, s, 1, n + 1)
    assert e.registry.get(a).consent_state == "GRANTED"
    e.submit(PrivacyRequest("s_test", "3", RequestOrigin.VOICE, "t", a, RequestAction.PROTECT, 0, True)); run(e, s, 1, n + 2)
    assert e.registry.get(a).consent_state == "REVOKED"
    res, n2 = run(e, s, 10, n + 3)               # enrol A's face
    s.frame = [face("B", 400, 100)]              # protected A leaves
    res, n2 = run(e, s, 30, n2)
    s.frame = [face("B", 400, 100), face("C", 250, 300)]
    r = e.step(packet(n2))
    assert any(t["consent_state"] == "UNCERTAIN" for t in r.tracks if t["person_id"] is None)

def test_strict_mode_blurs_everyone_until_peace_sign_opt_in():
    s, e = make_sig()
    e.strict = True
    a, b, n = two_people(s, e)
    r = e.step(packet(n))
    assert all(t["shielded"] for t in r.tracks)
    s.sig = {"faces": [], "hands": [hand(170, 280, peace=True)],
             "heads": [body_of(100, 100, wrist=(160, 270)), body_of(400, 100)]}
    res, n = run(e, s, 20, n + 1)
    assert not next(t for t in res.tracks if t["person_id"] == a)["shielded"]
    assert next(t for t in res.tracks if t["person_id"] == b)["shielded"]



def test_protected_face_teleporting_while_old_track_coasts_is_never_shown():
    s, e = make_sig()
    a, b, n = two_people(s, e)
    e.submit(PrivacyRequest("s_test", "pa", RequestOrigin.MANUAL_TEST, None, a, RequestAction.PROTECT, 0, True))
    res, n = run(e, s, 20, n)
    s.frame = [face("A", 250, 330), face("B", 400, 100)]   # A jumps far away in one frame
    for i in range(n, n + 6):
        pkt = packet(i); r = e.step(pkt)
        assert region_changed(pkt.bgr, r.protected_bgr, 250, 330), f"A visible at frame {i - n}"
    assert pid_of(r, 250) == a


def test_bystander_track_reforming_while_protected_person_is_away_is_never_shielded():
    """Live bug: friend showed 'checking...' and was blurred for seconds while the protected
    person was out of frame and the friend's tracking flickered (turned head = no clean frame)."""
    s, e = make_sig()
    a, b, n = two_people(s, e)
    e.submit(PrivacyRequest("s_test", "pa", RequestOrigin.MANUAL_TEST, None, a, RequestAction.PROTECT, 0, True))
    res, n = run(e, s, 20, n)
    s.frame = [face("B", 400, 100)]                    # protected A leaves
    res, n = run(e, s, 30, n)
    s.frame = []                                       # B's detection drops for ~1.5 s (track expires)
    res, n = run(e, s, 22, n)
    s.frame = [face("B", 405, 104, score=0.75)]        # B back in the same spot, turned (not a clean frame)
    for i in range(n, n + 15):
        pkt = packet(i); r = e.step(pkt)
        tb = r.tracks[0]
        assert not tb["shielded"], f"bystander shielded at frame {i - n}"
    assert tb["person_id"] == b

def test_returning_protected_person_cannot_inherit_a_bystanders_spot():
    s, e = make_sig()
    a, b, n = two_people(s, e)
    e.submit(PrivacyRequest("s_test", "pa", RequestOrigin.MANUAL_TEST, None, a, RequestAction.PROTECT, 0, True))
    res, n = run(e, s, 20, n)
    s.frame = [face("B", 400, 100)]
    res, n = run(e, s, 30, n)                          # A away
    s.frame = []
    res, n = run(e, s, 22, n)                          # B's track expires
    s.frame = [face("A", 405, 104)]                    # A appears exactly where B was
    for i in range(n, n + 10):
        pkt = packet(i); r = e.step(pkt)
        assert region_changed(pkt.bgr, r.protected_bgr, 405, 104), f"A visible at frame {i - n}"



def body_of(x, y, size=100, wrist=None):
    """Fake pose body for a face at (x, y): nose inside the face box, optional wrist position."""
    return {"box": (x - 5, y - 5, size + 10, size + 15), "body": (x - 40, y - 10, size + 80, 300),
            "nose": (x + size / 2, y + size / 2), "wrists": [wrist] if wrist else [], "shoulder_w": 120.0}

def test_someone_elses_peace_sign_next_to_your_face_never_unblurs_you():
    """Live bug: A held a peace sign beside B's (blurred) face and B got unblurred."""
    s, e = make_sig()
    a, b, n = two_people(s, e)
    e.submit(PrivacyRequest("s_test", "pb", RequestOrigin.MANUAL_TEST, None, b, RequestAction.PROTECT, 0, True))
    res, n = run(e, s, 2, n)
    # A's hand is right next to B's face, but its wrist belongs to A's body (A's arm reaches over)
    s.sig = {"faces": [], "hands": [hand(380, 230, peace=True)],
             "heads": [body_of(100, 100, wrist=(372, 222)), body_of(400, 100, wrist=(560, 400))]}
    res, n = run(e, s, 30, n)
    assert e.registry.get(b).protected, "A's peace sign must not unblur B"

def test_peace_sign_without_body_link_is_ignored_when_two_people_are_present():
    s, e = make_sig()
    a, b, n = two_people(s, e)
    e.submit(PrivacyRequest("s_test", "pb", RequestOrigin.MANUAL_TEST, None, b, RequestAction.PROTECT, 0, True))
    res, n = run(e, s, 2, n)
    s.sig = {"faces": [], "hands": [hand(470, 280, peace=True)], "heads": []}   # pose unavailable
    res, n = run(e, s, 30, n)
    assert e.registry.get(b).protected

def test_peace_sign_works_alone_without_pose():
    s, e = make_sig()
    s.frame = [face("A", 100, 100)]
    res, n = run(e, s, 12, 1)
    a = pid_of(res, 100)
    e.submit(PrivacyRequest("s_test", "pa", RequestOrigin.MANUAL_TEST, None, a, RequestAction.PROTECT, 0, True))
    res, n = run(e, s, 2, n)
    s.sig = {"faces": [], "hands": [hand(170, 280, peace=True)], "heads": []}
    res, n = run(e, s, 20, n)
    assert not e.registry.get(a).protected


def test_unblur_needs_clearer_speaker_evidence_than_blur():
    import math
    # A's lips move ~2.2x more than B's: enough to attribute "blur me", not "unblur me"
    a = lambda t: 0.03 + 0.022 * abs(math.sin(t / 60.0))
    b = lambda t: 0.03 + 0.0105 * abs(math.sin(t / 60.0 + 1))
    hist = [(t * 66, ("person_001", "person_002"), {"person_001": a(t * 66), "person_002": b(t * 66)}) for t in range(30)]
    turn = SpeechTurn("s_test", "t1", 300, 1500, "x", True)
    assert match_speaker(turn, hist).person_id == "person_001"
    assert match_speaker(turn, hist, strict=True).person_id is None

def test_lips_vs_voice_disagreement_targets_nobody():
    import math
    voice = lambda t: 800 * max(0.0, math.sin(t / 90.0)) if 0 <= t <= 1500 else 20.0
    laugher = lambda t: 0.03 + 0.09 * abs(math.sin(t / 37.0 + 1.0))   # big lip motion, wrong rhythm
    talker = lambda t: 0.03 + 0.00004 * voice(t)                        # smaller motion, follows the voice
    hist = [(t * 33, ("person_001", "person_002"), {"person_001": laugher(t * 33), "person_002": talker(t * 33)})
            for t in range(-150, 70)]
    env = [(t, voice(t)) for t in range(-5000, 2400, 20)]
    turn = SpeechTurn("s_test", "t1", 0, 1500, "x", True)
    m = match_speaker(turn, hist, agree_env=env)
    assert m.person_id is None and m.status == "AMBIGUOUS"


def test_speech_window_comes_from_mic_loudness_not_drifting_stt_times():
    from backend.app.consent.speaker import speech_window
    # real speech 2000-3200 ms on the session clock; STT reports it 600 ms early (stream drift)
    env = [(t, 900.0 if 2000 <= t <= 3200 else 40.0) for t in range(0, 6000, 20)]
    turn = SpeechTurn("s_test", "t1", 1400, 2600, "x", True)
    lo, hi = speech_window(turn, env)
    assert abs(lo - 2000) <= 40 and abs(hi - 3200) <= 40
    assert speech_window(turn, [(t, 40.0) for t in range(0, 6000, 20)]) is None   # silence: can't tell

def test_lip_window_uses_mic_timing_to_pick_the_real_speaker():
    import math
    # A talks 2000-3200 (mic loud then); B talks 1000-2000. STT says 1400-2600 (drifted).
    a = lambda t: 0.03 + (0.03 * abs(math.sin(t / 50.0)) if 2000 <= t <= 3200 else 0.0)
    b = lambda t: 0.03 + (0.03 * abs(math.sin(t / 50.0)) if 1000 <= t <= 2000 else 0.0)
    hist = [(t, ("person_001", "person_002"), {"person_001": a(t), "person_002": b(t)}) for t in range(0, 6000, 50)]
    env = [(t, 900.0 if 2000 <= t <= 3200 else 40.0) for t in range(-20000, 6000, 20)]
    dbg = {}
    m = match_speaker(SpeechTurn("s_test", "t1", 1400, 2600, "x", True), hist, agree_env=env, debug=dbg)
    assert m.person_id == "person_001" and dbg["window_source"] == "mic_loudness"


def test_unclear_voice_unblur_confirmed_by_a_quick_own_peace_sign():
    s, e = make_sig()
    a, b, n = two_people(s, e)
    for pid in (a, b):
        e.submit(PrivacyRequest("s_test", "p" + pid, RequestOrigin.MANUAL_TEST, None, pid, RequestAction.PROTECT, 0, True))
    res, n = run(e, s, 2, n)
    e.request_confirmation("ALLOW", packet(n).t_ms)
    s.sig = {"faces": [], "hands": [hand(470, 280, peace=True)],
             "heads": [body_of(100, 100), body_of(400, 100, wrist=(460, 270))]}
    res, n = run(e, s, 6, n)                      # ~0.4 s: enough only because confirmation is open
    assert not e.registry.get(b).protected and e.registry.get(a).protected
    assert e.confirm is None

def test_quick_peace_without_confirmation_does_not_unblur():
    s, e = make_sig()
    a, b, n = two_people(s, e)
    e.submit(PrivacyRequest("s_test", "pb", RequestOrigin.MANUAL_TEST, None, b, RequestAction.PROTECT, 0, True))
    res, n = run(e, s, 2, n)
    s.sig = {"faces": [], "hands": [hand(470, 280, peace=True)],
             "heads": [body_of(100, 100), body_of(400, 100, wrist=(460, 270))]}
    res, n = run(e, s, 6, n)
    assert e.registry.get(b).protected

def test_unclear_voice_blur_confirmed_by_quick_eye_cover():
    s, e = make_sig()
    a, b, n = two_people(s, e)
    e.request_confirmation("DENY", packet(n).t_ms)
    s.frame = [face("B", 400, 100)]
    s.sig = {"faces": [face_sig(400, 100)], "hands": [hand_over_eyes(100, 100)], "heads": []}
    res, n = run(e, s, 10, n)                     # ~0.66 s
    assert e.registry.get(a).protected and not e.registry.get(b).protected
