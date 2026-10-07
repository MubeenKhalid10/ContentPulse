"""Signed upload/download URLs for local storage (no S3 configured). The token
in the URL is the authorization; no session is needed, just like S3."""

import tempfile
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from app.core.errors import AppError, ErrorCode, Forbidden, NotFound
from app.storage import get_storage
from app.storage.local import InvalidToken, LocalStorage

router = APIRouter(prefix="/storage/local", tags=["storage"])


def _discard(path: Path) -> None:
    path.unlink(missing_ok=True)


def _local() -> LocalStorage:
    storage = get_storage()
    if not isinstance(storage, LocalStorage):
        raise NotFound("File")
    return storage


@router.put("/{token}")
async def upload(token: str, request: Request) -> dict:
    storage = _local()
    try:
        claims = storage.verify(token, "put")
    except InvalidToken as exc:
        raise Forbidden(str(exc)) from exc
    content_type = request.headers.get("content-type", "").split(";")[0].strip()
    if content_type != claims["ct"]:
        raise AppError(
            ErrorCode.FILE_UPLOAD_FAILED,
            f"Expected a {claims['ct']} file but received {content_type or 'no content type'}.",
        )
    max_bytes = int(claims["max"])
    tmp_dir = storage.root / ".incoming"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    received = 0
    with tempfile.NamedTemporaryFile(dir=tmp_dir, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        try:
            async for chunk in request.stream():
                received += len(chunk)
                if received > max_bytes:
                    raise AppError(
                        ErrorCode.FILE_UPLOAD_FAILED,
                        f"The file is larger than the {max_bytes // 1_000_000} MB limit.",
                    )
                tmp.write(chunk)
        except BaseException:
            tmp.close()
            _discard(tmp_path)
            raise
    if received == 0:
        _discard(tmp_path)
        raise AppError(ErrorCode.FILE_UPLOAD_FAILED, "The file is empty.")
    storage.write(claims["key"], tmp_path, content_type)
    return {"key": claims["key"], "size": received}


@router.get("/{token}")
async def download(token: str) -> FileResponse:
    storage = _local()
    try:
        claims = storage.verify(token, "get")
    except InvalidToken as exc:
        raise Forbidden(str(exc)) from exc
    info = await storage.head(claims["key"])
    if info is None:
        raise NotFound("File")
    return FileResponse(
        storage.path(claims["key"]),
        media_type=info.content_type,
        filename=claims.get("fn"),
        content_disposition_type="inline" if claims.get("in", True) else "attachment",
    )
