"""Cloudflare R2 (S3-compatible) storage for finished recordings.

Env: S3_API = https://<account>.r2.cloudflarestorage.com/<bucket>
     R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY (R2 → Manage API tokens; object read/write)
The bucket must stay PRIVATE (no public bucket URL). Protected videos are shared
only through short-lived presigned links; restricted (raw) objects never are.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

PROTECTED_PREFIX = "protected/"
RESTRICTED_PREFIX = "restricted/"


def r2_config() -> Optional[dict]:
    api = os.getenv("S3_API", "").strip()
    key_id = os.getenv("R2_ACCESS_KEY_ID", "").strip()
    secret = os.getenv("R2_SECRET_ACCESS_KEY", "").strip()
    if not (api and key_id and secret):
        return None
    u = urlparse(api)
    bucket = os.getenv("R2_BUCKET", "").strip() or u.path.strip("/").split("/")[0]
    if not bucket:
        return None
    return {"endpoint": f"{u.scheme}://{u.netloc}", "bucket": bucket, "key_id": key_id, "secret": secret}


def missing_r2_settings() -> list[str]:
    return [n for n in ("S3_API", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY") if not os.getenv(n, "").strip()]


class R2Storage:
    def __init__(self, cfg: dict, client=None):
        self.bucket = cfg["bucket"]
        if client is None:
            import boto3
            from botocore.config import Config
            client = boto3.client("s3", endpoint_url=cfg["endpoint"], aws_access_key_id=cfg["key_id"],
                                  aws_secret_access_key=cfg["secret"], region_name="auto",
                                  config=Config(signature_version="s3v4", retries={"max_attempts": 3}))
        self.client = client

    def check(self) -> tuple[bool, str]:
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return True, "bucket reachable"
        except Exception as exc:
            return False, f"{type(exc).__name__}: {str(exc)[:100]}"

    def upload(self, path: Path, key: str) -> None:
        self.client.upload_file(str(path), self.bucket, key, ExtraArgs={"ContentType": "video/mp4"})

    def presign_protected(self, key: str, ttl_s: int = 300) -> str:
        if not key.startswith(PROTECTED_PREFIX):
            raise PermissionError("only protected recordings can be linked")
        return self.client.generate_presigned_url("get_object", Params={"Bucket": self.bucket, "Key": key},
                                                  ExpiresIn=ttl_s)
