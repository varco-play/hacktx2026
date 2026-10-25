"""Meta Muse Voice Transcribe realtime client (verified against docs 2026-10-24).

wss://api.meta.ai/v1/asr/realtime; first text frame is the handshake carrying
`authorization.accessToken`. Audio: raw s16le mono 24 kHz binary frames paced
~real time. Turn timing comes from `speechStart`/`speechEnd` audioProcessedMs.
"""
from __future__ import annotations

import asyncio
import json
from typing import Awaitable, Callable, Optional

import websockets

URL = "wss://api.meta.ai/v1/asr/realtime"
SAMPLE_RATE = 24000
CHUNK_MS = 100
CHUNK_BYTES = SAMPLE_RATE * 2 * CHUNK_MS // 1000


def handshake(api_key: str, model: str = "muse-voice-transcribe-1.0") -> dict:
    return {
        "authorization": {"accessToken": f"Bearer {api_key}"},
        "model": model,
        "audioEncoding": "PCM_24KHZ",
        "mode": "ENDPOINTING",
    }


class TurnAssembler:
    """Collects server events into final turns: (turn_id, start_ms, end_ms, text)."""

    def __init__(self):
        self.starts: dict = {}
        self.ends: dict = {}
        self.seen: set = set()
        self.partial = ""

    def feed(self, msg: dict) -> Optional[tuple]:
        t = msg.get("type")
        if t == "speechStart":
            self.starts[msg.get("turnId")] = int(msg.get("audioProcessedMs", 0))
        elif t == "speechEnd":
            self.ends[msg.get("turnId")] = int(msg.get("audioProcessedMs", 0))
        elif t == "transcript" and not msg.get("final"):
            self.partial = msg.get("transcript", "")
        elif t == "speechComplete":
            tid = msg.get("turnId")
            if tid in self.seen:  # duplicate final -> ignore
                return None
            self.seen.add(tid)
            end = self.ends.get(tid, int(msg.get("audioProcessedMs", 0)))
            start = self.starts.get(tid, max(0, end - 2000))
            self.partial = ""
            return (str(tid), start, end, msg.get("transcript", ""))
        return None


async def stream(api_key: str, audio_chunks, on_turn: Callable[[tuple], Awaitable[None] | None],
                 on_status: Callable[[str], None] = lambda s: None) -> None:
    """audio_chunks: async iterator of bytes (s16le 24 kHz mono); ends the stream when exhausted."""
    asm = TurnAssembler()
    async with websockets.connect(URL, max_size=2**22) as ws:
        await ws.send(json.dumps(handshake(api_key)))
        ack = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        if "sessionId" not in ack or ack.get("type") == "error":
            raise RuntimeError(f"handshake rejected: {str(ack)[:200]}")
        on_status("CONNECTED")

        async def sender():
            async for chunk in audio_chunks:
                await ws.send(chunk)
            await ws.send(json.dumps({"type": "endStream"}))

        send_task = asyncio.create_task(sender())
        try:
            async for raw in ws:
                if isinstance(raw, bytes):
                    continue
                msg = json.loads(raw)
                if msg.get("type") == "error":
                    on_status(f"ERROR {msg.get('message', '')[:120]}")
                    break
                turn = asm.feed(msg)
                if turn is not None:
                    r = on_turn(turn)
                    if asyncio.iscoroutine(r):
                        await r
        finally:
            send_task.cancel()
