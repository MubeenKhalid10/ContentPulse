"""Local-disk storage behind signed URLs, so the upload flow is identical to
S3: the browser PUTs to a short-lived URL, then tells the API what it sent.

Tokens are JWTs signed with JWT_SECRET carrying the operation, key, content
type, size cap and expiry. Use S3 in production: this keeps files on the API
server's disk and streams uploads through it.
"""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt

from app.core.config import Settings
from app.storage import ObjectInfo, UploadTarget, check_key

ROUTE = "/api/v1/storage/local"
ALGORITHM = "HS256"
AUDIENCE = "contentpulse-storage"


class InvalidToken(Exception):
    pass


class LocalStorage:
    name = "local"

    def __init__(self, settings: Settings) -> None:
        self.root = Path(settings.local_storage_dir).resolve()
        self.secret = settings.jwt_secret
        self.ttl = settings.signed_url_ttl_seconds

    # --- paths ---------------------------------------------------------------------

    def path(self, key: str) -> Path:
        path = (self.root / check_key(key)).resolve()
        if self.root not in path.parents:
            raise ValueError("Key escapes the storage directory")
        return path

    def _meta_path(self, key: str) -> Path:
        return self.path(key).with_name(self.path(key).name + ".meta.json")

    # --- tokens --------------------------------------------------------------------

    def _token(self, claims: dict) -> tuple[str, datetime]:
        expires = datetime.now(UTC) + timedelta(seconds=self.ttl)
        token = jwt.encode(
            {**claims, "exp": expires, "aud": AUDIENCE}, self.secret, algorithm=ALGORITHM
        )
        return token, expires

    def verify(self, token: str, op: str) -> dict:
        try:
            claims = jwt.decode(token, self.secret, algorithms=[ALGORITHM], audience=AUDIENCE)
        except jwt.PyJWTError as exc:
            raise InvalidToken("This link has expired or is invalid.") from exc
        if claims.get("op") != op:
            raise InvalidToken("This link can't be used for that.")
        return claims

    # --- Storage protocol ----------------------------------------------------------

    async def upload_target(self, key: str, content_type: str, max_bytes: int) -> UploadTarget:
        token, expires = self._token(
            {"op": "put", "key": check_key(key), "ct": content_type, "max": max_bytes}
        )
        return UploadTarget(
            url=f"{ROUTE}/{token}",
            method="PUT",
            headers={"Content-Type": content_type},
            key=key,
            expires_at=expires,
        )

    async def head(self, key: str) -> ObjectInfo | None:
        path = self.path(key)
        if not path.is_file():
            return None
        meta = self._meta_path(key)
        content_type = json.loads(meta.read_text())["content_type"] if meta.exists() else None
        return ObjectInfo(size=path.stat().st_size, content_type=content_type)

    async def download_url(self, key: str, filename: str, *, inline: bool = True) -> str:
        token, _ = self._token({"op": "get", "key": check_key(key), "fn": filename, "in": inline})
        return f"{ROUTE}/{token}"

    async def delete(self, key: str) -> None:
        for path in (self.path(key), self._meta_path(key)):
            path.unlink(missing_ok=True)

    async def get(self, key: str) -> bytes | None:
        path = self.path(key)
        return path.read_bytes() if path.is_file() else None

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        target = self.path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        self._meta_path(key).write_text(json.dumps({"content_type": content_type}))

    # --- used by the upload route --------------------------------------------------

    def write(self, key: str, chunks_path: Path, content_type: str) -> None:
        target = self.path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(chunks_path, target)
        self._meta_path(key).write_text(json.dumps({"content_type": content_type}))
