"""Mic -> Muse realtime STT -> rules / Muse Spark -> speaker binding -> policy -> engine queue.

Runs on its own thread with its own asyncio loop; it never touches the registry
directly, only `engine.submit()`.
"""
from __future__ import annotations

import asyncio
import os
import queue
import threading
import time
from collections import deque
from typing import Optional

from backend.app.consent.policy import resolve_request
from backend.app.consent.speaker import match_speaker
from backend.app.providers import local_rules, meta_voice
from backend.app.providers.meta_intent import MuseSparkInterpreter
from shared.contracts import SpeechTurn


class VoicePipeline:
    def __init__(self, settings, session):
        self.settings = settings
        self.session = session
        self.state = "STARTING"
        self.detail = ""
        self.turns: deque = deque(maxlen=20)
        self._audio: "queue.Queue[bytes]" = queue.Queue(maxsize=200)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._mic = None
        self._audio_t0_ms: Optional[int] = None  # session ms of first audio sample sent
        self._n = 0
        self.llm, self.fallback, self.intent_label = self._build_interpreters(settings)

    @staticmethod
    def _build_interpreters(settings):
        """Primary per INTENT_PROVIDER (default gemini); Muse Spark is the fallback on error."""
        spark = MuseSparkInterpreter(settings.meta_key) if settings.meta_key else None
        if settings.intent_provider == "gemini":
            from backend.app.providers.gemini_intent import GeminiInterpreter, check_access
            why = ""
            if not settings.gemini_key:
                why = "no GEMINI_API_KEY"
            elif not os.getenv("GEMINI_MODEL"):
                why = "GEMINI_MODEL not set"
            else:
                ok, detail = check_access(settings.gemini_key)
                if ok:
                    return GeminiInterpreter(settings.gemini_key), spark, \
                        f"local_rules → gemini:{os.getenv('GEMINI_MODEL')} (fallback muse-spark-1.3)"
                why = detail
            return spark, None, f"local_rules → muse-spark-1.3 (gemini UNAVAILABLE: {why})"
        return spark, None, "local_rules → muse-spark-1.3" if spark else "local_rules only"

    def status(self) -> dict:
        return {"state": self.state, "detail": self.detail, "stt": "muse-voice-transcribe-1.0",
                "intent": self.intent_label,
                "turns": list(self.turns)}

    def start(self) -> None:
        if not self.settings.meta_key:
            self.state, self.detail = "UNAVAILABLE", "META_MODEL_API_KEY not set"
            return
        import sounddevice as sd

        def cb(indata, frames, t, status):
            if self._audio_t0_ms is None:
                self._audio_t0_ms = self.session.now_ms()
            try:
                self._audio.put_nowait(bytes(indata))
            except queue.Full:
                pass

        try:
            self._mic = sd.RawInputStream(samplerate=meta_voice.SAMPLE_RATE, channels=1, dtype="int16",
                                          blocksize=meta_voice.SAMPLE_RATE * meta_voice.CHUNK_MS // 1000,
                                          callback=cb)
            self._mic.start()
        except Exception as exc:
            self.state, self.detail = "UNAVAILABLE", f"microphone: {exc}"
            return
        self._thread = threading.Thread(target=lambda: asyncio.run(self._run()), name="voice", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._mic is not None:
            self._mic.stop(); self._mic.close(); self._mic = None
        self.state = "OFF"

    async def _chunks(self):
        loop = asyncio.get_running_loop()
        while not self._stop.is_set():
            try:
                chunk = await loop.run_in_executor(None, self._audio.get, True, 0.5)
            except queue.Empty:
                continue
            yield chunk

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                await meta_voice.stream(self.settings.meta_key, self._chunks(), self._on_turn,
                                        self._set_status)
            except Exception as exc:
                self.state, self.detail = "DEGRADED", f"{type(exc).__name__}: {str(exc)[:120]}"
                await asyncio.sleep(2)  # reconnect; existing blur states are unaffected

    def _set_status(self, s: str) -> None:
        self.state = "LIVE" if s == "CONNECTED" else "DEGRADED"
        self.detail = s

    async def _on_turn(self, t: tuple) -> None:
        tid, start, end, text = t
        base = self._audio_t0_ms or 0
        self._n += 1
        turn = SpeechTurn(self.session.session_id, f"turn_{self._n:03d}_{tid}", base + start, base + end,
                          text, True)
        await asyncio.get_running_loop().run_in_executor(None, self.handle_turn, turn)

    def handle_turn(self, turn: SpeechTurn) -> dict:
        t0 = time.monotonic()
        parsed = local_rules.interpret(turn)
        if parsed is None and self.llm is not None:
            parsed = self.llm.interpret(turn)
            if parsed.reason_short.startswith("provider error") and self.fallback is not None:
                parsed = self.fallback.interpret(turn)
        record = {"turn_id": turn.turn_id, "text": turn.text, "start_ms": turn.start_ms,
                  "end_ms": turn.end_ms}
        if parsed is None:
            record.update(intent="UNCLEAR", source="none", action=None)
            self.turns.append(record)
            return record
        match = match_speaker(turn, self.session.engine.visibility_history())
        req = resolve_request(turn, parsed, match, self.session.session_id, f"voice_{turn.turn_id}")
        if req is not None:
            self.session.engine.submit(req)
        record.update(intent=parsed.intent.value, speaker_ref=parsed.speaker_ref.value,
                      source=parsed.source, speaker_method=match.method, speaker_status=match.status,
                      speaker_score=match.evidence_score, speaker_margin=match.runner_up_margin,
                      target=req.target_person_id if req else None,
                      action=req.action.value if req else None,
                      decide_ms=round((time.monotonic() - t0) * 1000),
                      apply_delay_ms=self.session.now_ms() - turn.end_ms)
        self.turns.append(record)
        return record
