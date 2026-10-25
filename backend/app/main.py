"""FastAPI surface. Protected media only; no route serves original/source pixels."""
from __future__ import annotations

import asyncio
import re
import secrets
import sys
import threading
import time
from importlib.metadata import version
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from backend.app.capture import CameraSource, FileSource
from backend.app.config import ROOT, Settings
from backend.app.runtime import Session
from backend.app.vision.detector import FaceModels
from shared.contracts import PrivacyRequest, RequestAction, RequestOrigin

settings = Settings()
app = FastAPI(title="ConsentLens")
CSRF_HEADER = "x-consentlens"


@app.middleware("http")
async def require_app_header(request, call_next):
    """State-changing calls must carry a custom header. Browsers cannot add it cross-site
    without a CORS preflight (which we never grant), so other web pages can't start the
    camera, recording, or voice on this machine."""
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get(CSRF_HEADER) != "1":
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "missing X-ConsentLens header"}, status_code=403)
    return await call_next(request)
_state: dict = {"session": None, "models": None, "voice": None, "storage": None}


def _storage():
    """R2 when configured (videos not kept locally), else local recordings/ folder."""
    from backend.app.media.storage import R2Storage, r2_config
    if _state["storage"] is None:
        cfg = r2_config()
        _state["storage"] = R2Storage(cfg) if cfg else False
    return _state["storage"] or None
_lock = threading.Lock()
REC_ID = re.compile(r"^rec_[0-9a-f]{12}$")


def _models() -> FaceModels:
    if _state["models"] is None:
        _state["models"] = FaceModels(settings.models_dir)
    return _state["models"]


def _session() -> Session:
    s = _state["session"]
    if s is None:
        raise HTTPException(409, "no active session")
    return s


def _missing_r2() -> list:
    from backend.app.media.storage import missing_r2_settings
    return missing_r2_settings()


def _pkg(name: str) -> Optional[str]:
    try:
        return version(name)
    except Exception:
        return None


@app.get("/api/health")
def health():
    voice = _state["voice"]
    return {
        "python": sys.version.split()[0],
        "packages": {n: _pkg(n) for n in ("opencv-contrib-python", "mediapipe", "av", "fastapi")},
        "models_present": all((Path(settings.models_dir) / f).is_file() for f in
                              ("face_detection_yunet_2023mar.onnx", "face_recognition_sface_2021dec.onnx")),
        "session_active": _state["session"] is not None,
        "source": settings.test_video and "TEST INPUT" or "CAMERA",
        "diagnostic_original_enabled": settings.diagnostic_original,
        "dev_controls_enabled": settings.dev_controls,
        "meta_key_configured": bool(settings.meta_key),
        "recording_storage": "r2" if _storage() else "local (R2 not configured: missing " + ", ".join(_missing_r2()) + ")",
        "gemini_key_configured": bool(settings.gemini_key),
        "voice": voice.status() if voice else {"state": "OFF"},
    }


@app.post("/api/session/start")
def session_start():
    with _lock:
        if _state["session"] is not None:
            raise HTTPException(409, "session already active (one camera owner)")
        if settings.test_video:
            src = FileSource(settings.test_video, settings.width, settings.height, settings.fps)
            label = f"TEST INPUT: {Path(settings.test_video).name}"
        else:
            src = CameraSource(settings.camera_index, settings.width, settings.height, settings.fps)
            label = "CAMERA"
        try:
            from backend.app.vision.landmarks import Signals
            signals = Signals(settings.models_dir)  # fresh per session (VIDEO-mode timestamps)
        except Exception:
            signals = None  # no gestures; speaker binding falls back to single_candidate (shown in state)
        sess = Session(settings, src, _models(), label, signals=signals, storage=_storage())
        try:
            sess.start()
        except Exception as exc:
            raise HTTPException(503, f"could not start capture: {exc}")
        _state["session"] = sess
        return {"session_id": sess.session_id, "source": label}


@app.post("/api/session/end")
def session_end():
    with _lock:
        sess = _session()
        voice = _state["voice"]
        if voice:
            voice.stop()
            _state["voice"] = None
        result = sess.stop()
        _state["session"] = None
        return result


@app.post("/api/recording/start")
def recording_start():
    return _session().start_recording()


@app.post("/api/recording/stop")
def recording_stop():
    info = _session().stop_recording()
    if info is None:
        raise HTTPException(409, "not recording")
    return info


@app.get("/api/state")
def state():
    s = _state["session"]
    if s is None:
        return {"session_id": None}
    snap = s.snapshot()
    voice = _state["voice"]
    snap["voice"] = voice.status() if voice else {"state": "OFF"}
    return snap


@app.get("/api/preview/protected")
def preview():
    sess = _session()

    def gen():
        last = None
        while _state["session"] is sess:
            jpg = sess.latest_jpeg
            if jpg is not None and jpg is not last:
                last = jpg
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
            time.sleep(0.02)

    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.websocket("/api/events")
async def events(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            s = _state["session"]
            await ws.send_json(state() if s else {"session_id": None})
            await asyncio.sleep(0.25)
    except (WebSocketDisconnect, RuntimeError):
        return


@app.get("/api/recordings/{recording_id}/protected")
def recording_protected(recording_id: str):
    """Protected video only. R2: short-lived presigned redirect. Raw is never linked."""
    from fastapi.responses import RedirectResponse
    if not REC_ID.match(recording_id):
        raise HTTPException(404)
    s = _state["session"]
    info = next((r for r in (s.finished_recordings if s else []) if r["recording_id"] == recording_id), None)
    if info and info.get("storage") == "r2":
        if info.get("upload") != "uploaded":
            raise HTTPException(409, f"upload {info.get('upload')}")
        return RedirectResponse(_storage().presign_protected(info["protected_key"], ttl_s=300), status_code=307)
    path = Path(settings.recordings_dir) / f"{recording_id}_protected.mp4"
    if info is None and s is not None:
        raise HTTPException(409, "recording not finalized")
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type="video/mp4")


@app.post("/api/dev/protect/{person_id}")
def dev_protect(person_id: str):
    """MANUAL_TEST injection for development. Disabled unless ENABLE_DEV_CONTROLS=true."""
    if not settings.dev_controls:
        raise HTTPException(404)
    sess = _session()
    if sess.engine.registry.get(person_id) is None:
        raise HTTPException(404, "unknown person_id")
    sess.engine.submit(PrivacyRequest(sess.session_id, "dev_" + secrets.token_hex(4),
                                      RequestOrigin.MANUAL_TEST, None, person_id,
                                      RequestAction.PROTECT, sess.now_ms(), True))
    return {"queued": person_id, "origin": "MANUAL_TEST"}


@app.post("/api/voice/start")
def voice_start():
    from backend.app.voice import VoicePipeline
    sess = _session()
    if _state["voice"] is not None:
        return _state["voice"].status()
    vp = VoicePipeline(settings, sess)
    vp.start()
    _state["voice"] = vp
    return vp.status()


@app.post("/api/voice/stop")
def voice_stop():
    vp = _state["voice"]
    if vp:
        vp.stop()
        _state["voice"] = None
    return {"state": "OFF"}


app.mount("/", StaticFiles(directory=str(ROOT / "frontend"), html=True), name="frontend")
