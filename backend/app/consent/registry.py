"""The single canonical person registry for one session.

Only `VisionEngine.step` (one thread) mutates it. Embeddings never leave this
module through `snapshot()`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from shared.contracts import Privacy

GALLERY_MAX = 12


@dataclass
class Person:
    person_id: str
    privacy: Privacy = Privacy.VISIBLE_NO_REQUEST
    gallery: list = field(default_factory=list)  # SFace features — ONLY while this person is protected
    first_seen_ms: int = 0
    last_seen_ms: int = 0
    protected_at_ms: Optional[int] = None
    protect_source: Optional[str] = None
    released_at_ms: Optional[int] = None
    revoked: bool = False  # had consented, then asked for blur again

    @property
    def consent_state(self) -> str:
        """Reporting vocabulary: UNKNOWN (no request — NOT consent), DENIED, GRANTED, REVOKED.
        UNCERTAIN is reported for faces whose identity is still being checked (no person yet)."""
        if self.privacy == Privacy.BLURRED_BY_REQUEST:
            return "REVOKED" if self.revoked else "DENIED"
        if self.privacy == Privacy.VISIBLE_BY_CONSENT:
            return "GRANTED"
        return "UNKNOWN"

    @property
    def protected(self) -> bool:
        return self.privacy == Privacy.BLURRED_BY_REQUEST

    def add_feature(self, feat: np.ndarray) -> None:
        self.gallery.append(feat.copy())
        if len(self.gallery) > GALLERY_MAX:
            # keep the earliest sample as an anchor, drop the oldest of the rest
            del self.gallery[1]


class PersonRegistry:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.persons: dict[str, Person] = {}
        self._next = 1

    def new_person(self, t_ms: int) -> Person:
        pid = f"person_{self._next:03d}"
        self._next += 1
        p = Person(person_id=pid, first_seen_ms=t_ms, last_seen_ms=t_ms)
        self.persons[pid] = p
        return p

    def get(self, person_id: Optional[str]) -> Optional[Person]:
        return self.persons.get(person_id) if person_id else None

    def protect(self, person_id: str, t_ms: int, source: str) -> bool:
        """Record refusal. Returns True if state changed. Only `unprotect` reverses it."""
        p = self.persons.get(person_id)
        if p is None or p.protected:
            return False
        p.revoked = p.privacy == Privacy.VISIBLE_BY_CONSENT
        p.privacy = Privacy.BLURRED_BY_REQUEST
        p.protected_at_ms = t_ms
        p.protect_source = source
        return True

    def unprotect(self, person_id: str, t_ms: int, source: str) -> bool:
        """Subject's own consent (bound by gesture/voice evidence). Returns True if changed."""
        p = self.persons.get(person_id)
        if p is None or not p.protected:
            return False
        p.privacy = Privacy.VISIBLE_BY_CONSENT
        p.released_at_ms = t_ms
        p.protect_source = source
        p.gallery.clear()  # consented: no reason to keep their face features
        return True

    def remove(self, person_id: str) -> None:
        self.persons.pop(person_id, None)

    def any_protected(self) -> bool:
        return any(p.protected for p in self.persons.values())

    def snapshot(self) -> list[dict]:
        return [
            {
                "person_id": p.person_id,
                "privacy": p.privacy.value,
                "consent_state": p.consent_state,
                "last_seen_ms": p.last_seen_ms,
                "protected_at_ms": p.protected_at_ms,
                "protect_source": p.protect_source,
                "embedding_gallery_size": len(p.gallery),
            }
            for p in self.persons.values()
        ]

    def clear_biometrics(self) -> int:
        n = sum(len(p.gallery) for p in self.persons.values())
        for p in self.persons.values():
            p.gallery.clear()
        return n
