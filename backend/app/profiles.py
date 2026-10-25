"""Quality profiles + thermal governor.

Processing rate and landmark cadence are the main heat/battery levers (measured on M4:
YuNet ~5 ms, face landmarks ~6 ms, hand ~8 ms, pose ~6 ms per call). Thermal state comes
from macOS (NSProcessInfo.thermalState) — the Mac stands in for the phone/back end that
would process glasses video. Glasses/phone thermal is shown only if the companion app
reports it; otherwise "unavailable".
"""
from __future__ import annotations

import time

PROFILES = {
    # process_fps: frames analysed per second (others dropped, never queued)
    # signals_every: run MediaPipe landmarks every Nth processed frame (reuse last otherwise)
    "ECO": {"process_fps": 10, "signals_every": 2, "jpeg_quality": 70},
    "BALANCED": {"process_fps": 15, "signals_every": 1, "jpeg_quality": 80},
    "QUALITY": {"process_fps": 30, "signals_every": 1, "jpeg_quality": 85},
}
THERMAL_NAMES = {0: "nominal", 1: "fair", 2: "serious", 3: "critical"}


def mac_thermal_state() -> str:
    try:
        import Foundation
        return THERMAL_NAMES.get(int(Foundation.NSProcessInfo.processInfo().thermalState()), "unknown")
    except Exception:
        return "unavailable"


class ThermalGovernor:
    """Drops to ECO when the host reports 'serious'/'critical'; restores the user's choice
    after 60 s back at nominal/fair. Never raises quality above what the user picked."""

    def __init__(self, chosen: str = "BALANCED", read=mac_thermal_state):
        self.chosen = chosen if chosen in PROFILES else "BALANCED"
        self.active = self.chosen
        self.read = read
        self.state = "unknown"
        self._last_check = float("-inf")
        self._cool_since = None
        self.throttled = False

    def choose(self, name: str) -> None:
        if name in PROFILES:
            self.chosen = name
            if not self.throttled:
                self.active = name

    def tick(self, now: float | None = None) -> str | None:
        """Returns an event type when the active profile changes."""
        now = time.monotonic() if now is None else now
        if now - self._last_check < 5.0:
            return None
        self._last_check = now
        self.state = self.read()
        hot = self.state in ("serious", "critical")
        if hot and not self.throttled and self.chosen != "ECO":
            self.throttled, self.active, self._cool_since = True, "ECO", None
            return "THERMAL_THROTTLE"
        if self.throttled and not hot:
            self._cool_since = self._cool_since or now
            if now - self._cool_since >= 60:
                self.throttled, self.active = False, self.chosen
                return "THERMAL_RESTORED"
        elif hot:
            self._cool_since = None
        return None

    def profile(self) -> dict:
        return PROFILES[self.active]
