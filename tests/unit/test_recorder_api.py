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

def test_health_exposes_no_secrets_and_no_original_route(monkeypatch):
    monkeypatch.setenv("META_MODEL_API_KEY", "sk-test-SECRET-VALUE-123")
    from fastapi.testclient import TestClient
    from backend.app import main
    c = TestClient(main.app)
    r = c.get("/api/health")
    assert r.status_code == 200 and "SECRET" not in r.text
    paths = {getattr(rt, "path", "") for rt in main.app.routes}
    assert not any("original" in p for p in paths)
    assert c.post("/api/dev/protect/person_001").status_code in (404, 409) or not main.settings.dev_controls
    assert c.get("/api/recordings/../../etc/passwd/protected").status_code == 404
