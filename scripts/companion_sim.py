"""Companion-app PROTOCOL SIMULATOR (not the Meta SDK).

Sends frames from a video file to /api/ingest using exactly the wire format the iOS
companion (ios/ConsentLensCompanion/Sources/FrameUplink.swift) uses: 4-byte big-endian
header length + JSON header + JPEG, one frame in flight, rate-limited. Use it to test the
server side of Mode B/C without Xcode. Its frames are labeled origin="protocol_simulator".

  .venv/bin/python scripts/companion_sim.py clip.mp4 --token $INGEST_TOKEN [--fps 12]
"""
import argparse
import asyncio
import json
import time

import cv2
import websockets


async def main(a):
    cap = cv2.VideoCapture(a.video)
    url = f"{a.server}/api/ingest?token={a.token}"
    sent = 0
    async with websockets.connect(url) as ws:
        t_end = time.monotonic() + a.seconds
        while time.monotonic() < t_end:
            ok, frame = cap.read()
            if not ok:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
            header = json.dumps({"seq": sent + 1, "origin": "protocol_simulator",
                                 "thermal_state": "unavailable", "battery_level": "unavailable"}).encode()
            await ws.send(len(header).to_bytes(4, "big") + header + jpg.tobytes())
            ack = json.loads(await ws.recv())  # one frame in flight, like the iOS uplink
            sent += 1
            await asyncio.sleep(1.0 / a.fps)
    print(f"sent {sent} frames; last ack {ack}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("video")
    p.add_argument("--server", default="ws://127.0.0.1:8000")
    p.add_argument("--token", required=True)
    p.add_argument("--fps", type=float, default=12)
    p.add_argument("--seconds", type=float, default=20)
    asyncio.run(main(p.parse_args()))
