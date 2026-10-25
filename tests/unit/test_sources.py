import json
import time

import cv2
import numpy as np

from backend.app.capture import CaptureWorker, CompanionStreamSource, VideoFileSource
from backend.app.profiles import ThermalGovernor


class FlakySource:
    """Fake camera: delivers frames, then 'unplugs', then comes back."""
    source_id, kind = "usb_camera:Fake iPhone", "usb_camera"

    def __init__(self):
        self.mode, self.reopens = "ok", 0
    def initialize(self): pass
    def start(self): pass
    def read(self, timeout_s=1.0):
        time.sleep(0.005)
        return np.zeros((48, 64, 3), np.uint8) if self.mode == "ok" else None
    def reopen(self):
        self.reopens += 1
        return self.mode == "ok"
    def status(self): return {"state": "STREAMING" if self.mode == "ok" else "DISCONNECTED"}
    def capabilities(self): return {}
    def stop(self): pass
    cleanup = stop


def test_capture_worker_keeps_only_latest_and_counts_drops():
    src = FlakySource()
    w = CaptureWorker(src, lambda: int(time.monotonic() * 1000))
    w.start()
    time.sleep(0.2)                 # nobody consumes for 200 ms
    f = w.take(0.5)
    assert f is not None and w.dropped > 5 and w.queue_depth() == 0
    w.stop()


def test_disconnect_and_reconnect_events_same_device():
    events = []
    src = FlakySource()
    w = CaptureWorker(src, lambda: 0, lambda t, d: events.append(t))
    w.start()
    time.sleep(0.05)
    src.mode = "unplugged"
    deadline = time.time() + 3
    while "CAMERA_DISCONNECTED" not in events and time.time() < deadline:
        time.sleep(0.02)
    assert "CAMERA_DISCONNECTED" in events and not w.connected
    src.mode = "ok"
    deadline = time.time() + 4
    while "CAMERA_RECONNECTED" not in events and time.time() < deadline:
        time.sleep(0.05)
    assert "CAMERA_RECONNECTED" in events and w.connected and src.reopens >= 1
    w.stop()


def test_thermal_governor_throttles_and_restores():
    readings = iter(["nominal", "serious", "serious", "fair", "nominal", "nominal"])
    g = ThermalGovernor("QUALITY", read=lambda: next(readings))
    assert g.tick(0) is None and g.active == "QUALITY"
    assert g.tick(10) == "THERMAL_THROTTLE" and g.active == "ECO"
    g.choose("BALANCED")                       # user changes while hot: stays ECO
    assert g.tick(20) is None and g.active == "ECO"
    assert g.tick(30) is None                  # cooling starts
    assert g.tick(60) is None                  # < 60 s cool
    assert g.tick(95) == "THERMAL_RESTORED" and g.active == "BALANCED"


def _frame_msg(seq, img, origin="meta_mock_device"):
    ok, jpg = cv2.imencode(".jpg", img)
    header = json.dumps({"seq": seq, "origin": origin, "thermal_state": "nominal", "battery_level": 0.8}).encode()
    return len(header).to_bytes(4, "big") + header + jpg.tobytes()


def test_companion_ingest_requires_token_and_feeds_the_source(monkeypatch):
    import pytest
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect
    from backend.app import main
    monkeypatch.setattr(main.settings, "ingest_token", "t0ken")
    src = CompanionStreamSource(64, 48)
    main._state["companion"] = src
    c = TestClient(main.app)
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect("/api/ingest?token=wrong") as ws:
            ws.receive_json()
    img = np.full((48, 64, 3), 120, np.uint8)
    with c.websocket_connect("/api/ingest?token=t0ken") as ws:
        ws.send_bytes(_frame_msg(1, img))
        assert ws.receive_json()["accepted"] is True
        ws.send_bytes(_frame_msg(2, img))
        ws.receive_json()
    got = src.read(0.5)
    assert got is not None and got.shape == (48, 64, 3)
    assert src.dropped == 1                    # frame 1 was stale when frame 2 arrived
    st = src.status()
    assert "meta_mock_device" in st["source_id"] and "reported by app" in st["source_id"]
    assert src.capabilities()["battery"] == 0.8
    main._state["companion"] = None


def test_session_runs_any_source_through_the_same_engine(tmp_path):
    """TEST 10 shape: a video-file source drives Session -> engine -> recorder unchanged."""
    from backend.app.config import Settings
    from backend.app.runtime import Session
    path = str(tmp_path / "clip.mp4")
    vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 15, (64, 48))
    for i in range(30):
        vw.write(np.full((48, 64, 3), i * 5, np.uint8))
    vw.release()
    s = Settings(); s.width, s.height, s.recordings_dir = 64, 48, str(tmp_path / "rec")

    class M:
        detect = staticmethod(lambda b: [])
        feature = staticmethod(lambda b, d: None)
    sess = Session(s, VideoFileSource(path, 64, 48, fps=30), M(), "TEST INPUT", storage=None)
    sess.start()
    sess.start_recording()
    time.sleep(1.0)
    info = sess.stop()["recording"]
    m = sess.metrics()
    assert info["frames"] > 5 and info["error"] is None
    assert m["input_fps"] > 0 and m["frames"] > 5 and m["e2e_ms_p50"] is not None


def test_lan_clients_only_reach_ingest():
    from fastapi.testclient import TestClient
    from backend.app import main
    lan = TestClient(main.app, client=("192.168.1.50", 50000))
    for path in ("/api/health", "/api/state", "/api/preview/protected", "/", "/api/sources"):
        assert lan.get(path).status_code == 403, path
    assert lan.post("/api/session/start", headers={"X-ConsentLens": "1"}).status_code == 403
    local = TestClient(main.app)
    assert local.get("/api/health").status_code == 200



def test_rate_limiter_keeps_target_rate_without_halving():
    from backend.app.runtime import admit_frame
    def run(src_fps, target):
        next_due, n, t = 0.0, 0, 0.0
        for _ in range(int(src_fps * 10)):          # 10 s of frames
            if admit_frame(t, next_due, 1 / target):
                n += 1
                next_due = max(next_due + 1 / target, t)
            t += 1 / src_fps
        return n / 10
    assert 9.5 <= run(11.3, 10) <= 11.3            # previously 5.6
    assert 14 <= run(30, 15) <= 16
    assert 9 <= run(30, 10) <= 11
