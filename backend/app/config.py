from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes")


@dataclass
class Settings:
    camera_index: int = int(os.getenv("CAMERA_INDEX", "0"))
    width: int = int(os.getenv("CAPTURE_WIDTH", "640"))
    height: int = int(os.getenv("CAPTURE_HEIGHT", "480"))
    fps: int = int(os.getenv("CAPTURE_FPS", "15"))
    recordings_dir: str = str(ROOT / os.getenv("RECORDINGS_DIR", "recordings"))
    models_dir: str = str(ROOT / os.getenv("MODELS_DIR", "models"))
    diagnostic_original: bool = _bool("ENABLE_DIAGNOSTIC_ORIGINAL")
    dev_controls: bool = _bool("ENABLE_DEV_CONTROLS")  # manual test protect; off for judges
    raw_upload: bool = _bool("RAW_UPLOAD_R2")  # raw/original to R2 restricted/ prefix (off)
    burn_in_labels: bool = _bool("BURN_IN_LABELS")  # draw status labels into the preview JPEG (off: UI overlay)
    voice_enabled: bool = os.getenv("VOICE", "on").strip().lower() in ("1", "on", "true", "yes")  # voice commands; VOICE=off for gestures only
    intent_provider: str = os.getenv("INTENT_PROVIDER", "gemini").strip().lower()  # gemini | muse
    profile: str = os.getenv("QUALITY_PROFILE", "BALANCED").upper()  # ECO | BALANCED | QUALITY
    camera: str = os.getenv("CAMERA", "")  # "" = first external (USB phone) else built-in; index; or name part
    ingest_token: str = os.getenv("INGEST_TOKEN", "")  # companion app must send this
    privacy_default: str = os.getenv("PRIVACY_DEFAULT", "visible").lower()  # visible | protect (strict opt-in)
    test_video: str = os.getenv("TEST_VIDEO", "")  # replay file instead of camera (labeled)

    # Secrets: read here, never returned by any endpoint.
    @property
    def meta_key(self) -> str:
        return os.getenv("META_MODEL_API_KEY", "")

    @property
    def gemini_key(self) -> str:
        return os.getenv("GEMINI_API_KEY", "")
