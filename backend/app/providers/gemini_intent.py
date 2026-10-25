"""Google Gemini structured-output intent classifier (text only).

Uses the official `google-genai` SDK with `response_json_schema`. The model ID
comes from GEMINI_MODEL (must be one the account can list); nothing is guessed.
Output is validated by the same strict parser as Muse Spark.
"""
from __future__ import annotations

import json
import os
from typing import Optional

from backend.app.providers.meta_intent import SCHEMA, SYSTEM, parse_output
from shared.contracts import ConsentInterpretation, Intent, SpeakerRef, SpeechTurn


class GeminiInterpreter:
    def __init__(self, api_key: str, model: Optional[str] = None, timeout_s: float = 10.0):
        from google import genai
        from google.genai import types
        self.model = model or os.getenv("GEMINI_MODEL", "")
        if not self.model:
            raise ValueError("GEMINI_MODEL not set")
        self._types = types
        self.client = genai.Client(api_key=api_key,
                                   http_options=types.HttpOptions(timeout=int(timeout_s * 1000)))

    def interpret(self, turn: SpeechTurn) -> ConsentInterpretation:
        t = self._types
        try:
            r = self.client.models.generate_content(
                model=self.model,
                contents=json.dumps({"transcript": turn.text}),
                config=t.GenerateContentConfig(
                    system_instruction=SYSTEM,
                    temperature=0,
                    response_mime_type="application/json",
                    response_json_schema=SCHEMA,
                ),
            )
            content = r.text
        except Exception as exc:
            return ConsentInterpretation(turn.turn_id, Intent.UNCLEAR, SpeakerRef.UNKNOWN, True,
                                         f"provider error {type(exc).__name__}", "gemini")
        return parse_output(turn.turn_id, content, source="gemini")


def check_access(api_key: str) -> tuple[bool, str]:
    """One cheap call: list models. Returns (ok, detail) without exposing the key."""
    try:
        from google import genai
        names = [m.name for m in genai.Client(api_key=api_key).models.list()]
        return True, f"{len(names)} models visible"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {str(exc)[:80]}"
