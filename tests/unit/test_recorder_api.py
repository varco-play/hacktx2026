import numpy as np
from pathlib import Path
from backend.app.media.recorders import PairedRecorder, probe

def test_paired_recorder_writes_playable_protected_file(tmp_path: Path):
    rec = PairedRecorder(tmp_path, 640, 480, 15, diagnostic_original=True, t0_ms=1000)
    for i in range(30):
        src = np.full((480, 640, 3), i * 8 % 255, np.uint8)
        prot = src.copy(); prot[100:200, 100:200] = 0
        rec.write(src, prot, 1000 + i * 66)
    info = rec.close()
    assert info["frames"] == 30 and info["error"] is None
    p = probe(tmp_path / f"{info['recording_id']}_protected.mp4")
    assert p["frames"] == 30 and (p["width"], p["height"]) == (640, 480)
    assert 1.5 < p["duration_s"] < 2.5
    assert (tmp_path / f"{info['recording_id']}_original_DIAGNOSTIC.mp4").is_file()

def test_recorder_handles_30fps_jitter_and_duplicate_timestamps(tmp_path: Path):
    rec = PairedRecorder(tmp_path, 640, 480, 15, diagnostic_original=False, t0_ms=0)
    ts = [0, 33, 66, 66, 99, 140, 141, 170] + [200 + i * 33 for i in range(60)]
    for t in ts:
        rec.write(np.zeros((480, 640, 3), np.uint8), np.zeros((480, 640, 3), np.uint8), t)
    info = rec.close()
    assert info["error"] is None and info["frames"] == len(ts)
    assert probe(tmp_path / f"{info['recording_id']}_protected.mp4")["frames"] == len(ts)

def test_health_exposes_no_secrets_and_no_original_route(monkeypatch):
    monkeypatch.setenv("META_MODEL_API_KEY", "sk-test-SECRET-VALUE-123")
    from fastapi.testclient import TestClient
    from backend.app import main
    c = TestClient(main.app)
    r = c.get("/api/health")
    assert r.status_code == 200 and "sk-test-SECRET-VALUE-123" not in r.text
    paths = {getattr(rt, "path", "") for rt in main.app.routes}
    assert not any("original" in p for p in paths)
    assert c.post("/api/dev/protect/person_001").status_code in (404, 409) or not main.settings.dev_controls
    assert c.get("/api/recordings/../../etc/passwd/protected").status_code == 404


def test_state_changing_calls_need_app_header():
    from fastapi.testclient import TestClient
    from backend.app import main
    c = TestClient(main.app)
    assert c.post("/api/session/start").status_code == 403          # e.g. a cross-site form post
    assert c.post("/api/recording/start").status_code == 403
    assert c.post("/api/session/end", headers={"X-ConsentLens": "1"}).status_code == 409  # passes guard


class _FakeR2:
    def __init__(self, fail=False):
        self.bucket, self.fail, self.uploaded = "b", fail, {}
    def upload(self, path, key):
        if self.fail:
            raise ConnectionError("network down")
        self.uploaded[key] = path.read_bytes()[:4]
    def presign_protected(self, key, ttl_s=300):
        from backend.app.media.storage import PROTECTED_PREFIX
        if not key.startswith(PROTECTED_PREFIX):
            raise PermissionError
        return "https://example.invalid/" + key


def _session_with(storage, raw_upload=False):
    import time
    from backend.app.config import Settings
    from backend.app.runtime import Session
    s = Settings(); s.diagnostic_original, s.raw_upload = True, raw_upload
    class M: detect = staticmethod(lambda b: []); feature = staticmethod(lambda b, d: None)
    sess = Session(s, source=None, face_models=M(), source_label="TEST", storage=storage)
    sess.start_recording()
    for i in range(10):
        f = np.zeros((480, 640, 3), np.uint8)
        sess.recorder.write(f, f, sess.now_ms() + i * 33)
    info = sess.stop_recording()
    for _ in range(100):
        if info.get("upload") != "uploading":
            break
        time.sleep(0.05)
    return sess, info

def test_r2_mode_uploads_protected_deletes_local_and_skips_raw():
    r2 = _FakeR2()
    sess, info = _session_with(r2)
    assert info["upload"] == "uploaded" and info["protected_key"].startswith("protected/")
    assert list(r2.uploaded) == [info["protected_key"]]           # raw not recorded/uploaded by default
    assert not info.get("has_diagnostic_original")
    assert "local_path" not in info

def test_r2_raw_upload_only_when_enabled_and_never_presigned():
    import pytest
    r2 = _FakeR2()
    sess, info = _session_with(r2, raw_upload=True)
    assert info["restricted_key"].startswith("restricted/") and info["restricted_key"] in r2.uploaded
    with pytest.raises(PermissionError):
        r2.presign_protected(info["restricted_key"])

def test_r2_failure_keeps_local_protected_file():
    from pathlib import Path
    sess, info = _session_with(_FakeR2(fail=True))
    assert info["upload"].startswith("FAILED") and Path(info["local_path"]).is_file()
    Path(info["local_path"]).unlink()

def test_r2_config_parses_endpoint_and_bucket(monkeypatch):
    from backend.app.media.storage import r2_config
    monkeypatch.setenv("S3_API", "https://abc123.r2.cloudflarestorage.com/my-bucket")
    monkeypatch.setenv("R2_ACCESS_KEY_ID", "k"); monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "s")
    monkeypatch.delenv("R2_BUCKET", raising=False)
    c = r2_config()
    assert c["endpoint"] == "https://abc123.r2.cloudflarestorage.com" and c["bucket"] == "my-bucket"
    monkeypatch.delenv("R2_SECRET_ACCESS_KEY")
    assert r2_config() is None
