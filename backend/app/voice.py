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
from concurrent.futures import ThreadPoolExecutor
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
        self._acted: set = set()
        # decisions run off the receive loop so one slow LLM call never stalls later turns
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="voice-decide")
        self._gen = 0
        self._env: deque = deque(maxlen=50 * 60)  # (t_ms, rms) last ~60 s
        self._env_lock = threading.Lock()
        self.sync_decisions = False  # turn ids already decided (partial fast path or final)
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
            self._record_envelope(bytes(indata), self.session.now_ms())
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

    def _record_envelope(self, pcm: bytes, t_end_ms: int) -> None:
        """Mic loudness every 20 ms on the session clock (for audio-visual speaker sync).
        Only loudness numbers are kept — no audio is stored."""
        import numpy as np
        a = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
        step = meta_voice.SAMPLE_RATE // 50  # 20 ms
        n = len(a) // step
        if n == 0:
            return
        dur = len(a) * 1000 // meta_voice.SAMPLE_RATE
        with self._env_lock:
            for i in range(n):
                rms = float(np.sqrt(np.mean(a[i * step:(i + 1) * step] ** 2)))
                self._env.append((t_end_ms - dur + i * 20 + 10, rms))

    def audio_envelope(self) -> list:
        with self._env_lock:
            return list(self._env)

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
            self._gen += 1
            try:
                await meta_voice.stream(self.settings.meta_key, self._chunks(), self._on_turn,
                                        self._set_status)
            except Exception as exc:
                self.state, self.detail = "DEGRADED", f"{type(exc).__name__}: {str(exc)[:120]}"
                await asyncio.sleep(2)  # reconnect; existing blur states are unaffected

    def _set_status(self, s: str) -> None:
        if s == "CONNECTED":
            self.on_connected()
        self.state = "LIVE" if s == "CONNECTED" else "DEGRADED"
        self.detail = s

    def on_connected(self) -> None:
        """New Muse stream: its audio clock starts at 0 now. Drop audio queued while
        disconnected (stale commands must not execute late) and re-anchor the clock so
        turn timestamps line up with video frames for speaker binding."""
        dropped = 0
        while True:
            try:
                self._audio.get_nowait()
                dropped += 1
            except queue.Empty:
                break
        self._audio_t0_ms = self.session.now_ms()
        self.dropped_chunks = getattr(self, "dropped_chunks", 0) + dropped

    async def _on_turn(self, t: tuple) -> None:
        kind, tid, start, end, text = t
        base = self._audio_t0_ms or 0
        turn_id = f"turn_g{self._gen}_{tid}"  # Muse turn ids restart on every reconnect
        if kind == "partial":
            # Early action only for explicit REFUSALS (fail-safe). Consent waits for the final.
            if turn_id in self._acted:
                return
            early = SpeechTurn(self.session.session_id, turn_id, base + start, base + end, text, True)
            parsed = local_rules.interpret(early)
            if parsed is not None and parsed.intent.value == "DENY":
                self._acted.add(turn_id)
                self._dispatch(lambda: self.handle_turn(early, parsed=parsed, early=True))
            return
        turn = SpeechTurn(self.session.session_id, turn_id, base + start, base + end, text, True)
        if turn_id in self._acted:
            self._log_final_only(turn_id, text)
            final = local_rules.interpret(turn)
            if final is not None and final.intent.value == "DENY":
                return  # final agrees with the early refusal
            # final transcript changed meaning (e.g. partial "blur me" -> final "unblur me"): decide again
            turn = SpeechTurn(self.session.session_id, turn_id + "_final", turn.start_ms, turn.end_ms, text, True)
        self._acted.add(turn_id)
        self._dispatch(lambda: self.handle_turn(turn))

    def _dispatch(self, fn) -> None:
        if self.sync_decisions:  # unit tests
            fn()
        else:
            self._pool.submit(fn)

    def _log_final_only(self, turn_id: str, text: str) -> None:
        for r in self.turns:
            if r.get("turn_id") == turn_id:
                r["final_text"] = text

    def handle_turn(self, turn: SpeechTurn, parsed=None, early: bool = False) -> dict:
        t0 = time.monotonic()
        if parsed is None:
            parsed = local_rules.interpret(turn)
        if parsed is None and self.llm is not None:
            parsed = self.llm.interpret(turn)
            if parsed.reason_short.startswith("provider error") and self.fallback is not None:
                parsed = self.fallback.interpret(turn)
        record = {"turn_id": turn.turn_id, "text": turn.text, "start_ms": turn.start_ms,
                  "end_ms": turn.end_ms, "early_partial": early}
        if parsed is None:
            record.update(intent="UNCLEAR", source="none", action=None)
            self.turns.append(record)
            return record
        # Live-tested MVP binding: lip motion (+ single visible person). The audio-visual sync
        # variant (SPEAKER_AV=on) is experimental — it missed real "unblur me" turns on a laptop mic.
        env = self.audio_envelope() if os.getenv("SPEAKER_AV", "off").lower() in ("1", "on", "true") else None
        match = match_speaker(turn, self.session.engine.visibility_history(), env)
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
