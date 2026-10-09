"""S3 (or S3-compatible) storage with presigned URLs. The browser uploads
straight to the bucket, so the bucket needs a CORS rule allowing PUT from the
web app's origin (see README)."""

import asyncio
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import Settings
from app.storage import ObjectInfo, UploadTarget, check_key


class StorageUnavailable(Exception):
    pass


class S3Storage:
    name = "s3"

    def __init__(self, settings: Settings, client=None) -> None:
        assert settings.s3_bucket
        self.bucket = settings.s3_bucket
        self.ttl = settings.signed_url_ttl_seconds
        # Credentials fall back to the standard AWS chain (env, profile, IAM role).
        self.client = client or boto3.client(
            "s3",
            region_name=settings.aws_region,
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 3},
                # S3-compatible stores (Supabase Storage, R2, MinIO) expect
                # bucket-in-path URLs; AWS itself prefers virtual hosts.
                s3={"addressing_style": "path" if settings.s3_endpoint_url else "auto"},
            ),
        )

    async def upload_target(self, key: str, content_type: str, max_bytes: int) -> UploadTarget:
        # A presigned PUT can't cap the size; it's checked when the upload is registered.
        url = await asyncio.to_thread(
            self.client.generate_presigned_url,
            "put_object",
            Params={"Bucket": self.bucket, "Key": check_key(key), "ContentType": content_type},
            ExpiresIn=self.ttl,
        )
        return UploadTarget(
            url=url,
            method="PUT",
            headers={"Content-Type": content_type},
            key=key,
            expires_at=datetime.now(UTC) + timedelta(seconds=self.ttl),
        )

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        try:
            await asyncio.to_thread(
                self.client.put_object,
                Bucket=self.bucket,
                Key=check_key(key),
                Body=data,
                ContentType=content_type,
            )
        except (BotoCoreError, ClientError) as exc:
            raise StorageUnavailable(str(exc)) from exc

    async def get(self, key: str) -> bytes | None:
        def read() -> bytes:
            response = self.client.get_object(Bucket=self.bucket, Key=check_key(key))
            return response["Body"].read()

        try:
            return await asyncio.to_thread(read)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return None
            raise StorageUnavailable(f"Storage error: {exc}") from exc
        except BotoCoreError as exc:
            raise StorageUnavailable(f"Storage unreachable: {exc}") from exc

    async def head(self, key: str) -> ObjectInfo | None:
        try:
            resp = await asyncio.to_thread(
                self.client.head_object, Bucket=self.bucket, Key=check_key(key)
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return None
            raise StorageUnavailable(f"Storage error: {exc}") from exc
        except BotoCoreError as exc:
            raise StorageUnavailable(f"Storage unreachable: {exc}") from exc
        return ObjectInfo(size=resp["ContentLength"], content_type=resp.get("ContentType"))

    async def download_url(self, key: str, filename: str, *, inline: bool = True) -> str:
        disposition = f"{'inline' if inline else 'attachment'}; filename*=UTF-8''{quote(filename)}"
        return await asyncio.to_thread(
            self.client.generate_presigned_url,
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": check_key(key),
                "ResponseContentDisposition": disposition,
            },
            ExpiresIn=self.ttl,
        )

    async def delete(self, key: str) -> None:
        try:
            await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=key)
        except (ClientError, BotoCoreError):
            pass  # best effort: orphaned objects can be cleaned by a lifecycle rule
