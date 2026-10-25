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

from backend.app.capture import (AVFoundationCameraSource, CompanionStreamSource, VideoFileSource,
                                 list_video_devices)
from backend.app.config import ROOT, Settings
from backend.app.runtime import Session
from backend.app.vision.detector import FaceModels
from shared.contracts import PrivacyRequest, RequestAction, RequestOrigin

settings = Settings()
app = FastAPI(title="ConsentLens")
CSRF_HEADER = "x-consentlens"
LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


@app.middleware("http")
async def require_app_header(request, call_next):
    """State-changing calls must carry a custom header. Browsers cannot add it cross-site
    without a CORS preflight (which we never grant), so other web pages can't start the
    camera, recording, or voice on this machine."""
    host = request.client.host if request.client else ""
    if host not in LOCAL_HOSTS:
        # Phone/LAN clients may only use the token-protected ingest socket — never the
        # dashboard, preview, state, recordings or controls (no login on those).
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "local access only"}, status_code=403)
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get(CSRF_HEADER) != "1":
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "missing X-ConsentLens header"}, status_code=403)
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.endswith(".html"):
        response.headers["Cache-Control"] = "no-store"  # a reload always gets the current dashboard
    return response
_state: dict = {"session": None, "models": None, "voice": None, "storage": None, "companion": None}


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
    return {
        "python": sys.version.split()[0],
        "packages": {n: _pkg(n) for n in ("opencv-contrib-python", "mediapipe", "av", "fastapi")},
        "models_present": all((Path(settings.models_dir) / f).is_file() for f in
                              ("face_detection_yunet_2023mar.onnx", "face_recognition_sface_2021dec.onnx")),
        "session_active": _state["session"] is not None,
        "source_default": settings.test_video and "TEST INPUT" or (settings.camera or "first external camera, else built-in"),
        "cameras": [d["name"] for d in list_video_devices()],
        "diagnostic_original_enabled": settings.diagnostic_original,
        "dev_controls_enabled": settings.dev_controls,
        "voice_enabled": settings.voice_enabled,
        "meta_key_configured": bool(settings.meta_key),
        "recording_storage": "r2" if _storage() else "local (R2 not configured: missing " + ", ".join(_missing_r2()) + ")",
        "gemini_key_configured": bool(settings.gemini_key),
        "voice": _voice_public(),
    }


def _make_source(choice: str):
    """choice: "" (settings default) | "camera:<index or name part>" | "file:<path>" | "companion".
    The consent engine never changes with the source (TEST 10)."""
    choice = choice or (f"file:{settings.test_video}" if settings.test_video else f"camera:{settings.camera}")
    if choice.startswith("file:"):
        path = choice[5:]
        return VideoFileSource(path, settings.width, settings.height, settings.fps), f"TEST INPUT: {Path(path).name}"
    if choice == "companion":
        if not settings.ingest_token:
            raise HTTPException(400, "set INGEST_TOKEN in .env before accepting companion-app frames")
        src = CompanionStreamSource(settings.width, settings.height)
        _state["companion"] = src
        return src, "COMPANION APP (origin reported by app)"
    src = AVFoundationCameraSource(choice[7:] if choice.startswith("camera:") else "", settings.width,
                                   settings.height, 30)
    src.initialize()
    return src, f"CAMERA: {src.device['name']}" + (" (USB/external)" if src.kind == "usb_camera" else " (built-in)")


@app.get("/api/sources")
def sources():
    return {"cameras": list_video_devices(), "companion": {"enabled": bool(settings.ingest_token)},
            "test_video": settings.test_video or None,
            "default": f"file:{settings.test_video}" if settings.test_video else f"camera:{settings.camera}"}


@app.post("/api/session/start")
def session_start(source: str = ""):
    with _lock:
        if _state["session"] is not None:
            raise HTTPException(409, "session already active (one camera owner)")
        try:
            src, label = _make_source(source)
        except RuntimeError as exc:
            raise HTTPException(503, str(exc))
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
        if settings.voice_enabled and _state["voice"] is None:
            # Voice commands run automatically with the session (no button). Failure to get the
            # mic or API never blocks the camera session; status shows UNAVAILABLE instead.
            try:
                from backend.app.voice import VoicePipeline
                vp = VoicePipeline(settings, sess)
                vp.start()
                _state["voice"] = vp
            except Exception:
                _state["voice"] = None
        return {"session_id": sess.session_id, "source": label}


@app.post("/api/profile/{name}")
def set_profile(name: str):
    from backend.app.profiles import PROFILES
    if name.upper() not in PROFILES:
        raise HTTPException(404, f"profiles: {list(PROFILES)}")
    sess = _session()
    sess.governor.choose(name.upper())
    return {"chosen": sess.governor.chosen, "active": sess.governor.active, "throttled": sess.governor.throttled}


@app.websocket("/api/ingest")
async def ingest(ws: WebSocket):
    """Companion app (iOS, Meta Wearables DAT) pushes frames: each binary message is
    4-byte big-endian header length + JSON header + JPEG bytes. Token required."""
    import hmac
    import json
    token = ws.query_params.get("token", "")
    if not settings.ingest_token or not hmac.compare_digest(token, settings.ingest_token):
        await ws.close(code=1008)
        return
    await ws.accept()
    try:
        while True:
            msg = await ws.receive_bytes()
            if len(msg) < 4:
                continue
            n = int.from_bytes(msg[:4], "big")
            if n > 4096 or len(msg) < 4 + n:
                continue
            header = json.loads(msg[4:4 + n] or b"{}")
            src = _state.get("companion")
            ok = src.push(msg[4 + n:], header) if src is not None else False
            await ws.send_json({"ack": header.get("seq"), "accepted": bool(ok),
                                "session_active": _state["session"] is not None})
    except (WebSocketDisconnect, RuntimeError, ValueError):
        return


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
    snap["voice"] = _voice_public()
    return snap


def _voice_public() -> dict:
    """Voice status WITHOUT transcripts: the UI/API never exposes what people said, only the
    outcome of the last command."""
    vp = _state["voice"]
    if vp is None:
        return {"state": "OFF" if settings.voice_enabled else "DISABLED"}
    st = vp.status()
    keep = ("outcome", "intent", "action", "target", "speaker_status", "speaker_method", "source", "decide_ms",
            "apply_delay_ms", "early_partial", "turn_id")
    last = [{k: t.get(k) for k in keep} for t in st.get("turns", [])][-5:]
    env = vp.audio_envelope()[-10:] if hasattr(vp, "audio_envelope") else []
    # mic level 0..1 over the last 200 ms (rounded so the UI isn't pushed for noise)
    level = round(min(1.0, max((v for _, v in env), default=0.0) / 3000.0), 1)
    return {"state": st["state"], "detail": st.get("detail", ""), "intent_engine": st.get("intent"),
            "recent": last, "mic_level": level}


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
    if (ws.client.host if ws.client else "") not in LOCAL_HOSTS:
        await ws.close(code=1008)
        return
    await ws.accept()
    import json
    last = None
    try:
        while True:
            s = _state["session"]
            payload = json.dumps(state() if s else {"session_id": None}, default=str)
            if payload != last:  # one local socket; only push when something changed
                await ws.send_text(payload)
                last = payload
            await asyncio.sleep(0.1)  # 10 Hz so the face overlay keeps up with people moving
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
    if not settings.voice_enabled:
        raise HTTPException(404, "voice is disabled (set VOICE=on to enable)")
    from backend.app.voice import VoicePipeline
    sess = _session()
    if _state["voice"] is None:
        vp = VoicePipeline(settings, sess)
        vp.start()
        _state["voice"] = vp
    return _voice_public()


@app.post("/api/voice/stop")
def voice_stop():
    vp = _state["voice"]
    if vp:
        vp.stop()
        _state["voice"] = None
    return {"state": "OFF"}


app.mount("/", StaticFiles(directory=str(ROOT / "frontend"), html=True), name="frontend")
