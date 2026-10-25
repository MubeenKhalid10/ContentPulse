# ruff: noqa: E501  (long help strings)
"""Copy design files that were stored on this machine's disk into the S3 bucket.

Files uploaded or AI-generated while the backend used local storage live in
backend/storage. The database remembers them by key, so a deployed server that
uses S3 looks for the same key in the bucket and answers "NoSuchKey". This
uploads each local file under its own key, so those images show up again.

    cd backend
    # S3 settings: in your shell or in .env (the same values as on Render)
    #   S3_BUCKET, S3_ENDPOINT_URL, AWS_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
    .venv/Scripts/python scripts/upload_local_files_to_s3.py            # dry run: lists the files
    .venv/Scripts/python scripts/upload_local_files_to_s3.py --apply    # uploads

Safe to repeat: files already in the bucket are skipped, nothing is deleted
or overwritten, and local files are left where they are.
"""

import argparse
import mimetypes
import sys
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402

HINTS = {
    "NoSuchBucket": "The bucket name is wrong. Names are case-sensitive: copy it exactly from Supabase > Storage.",
    "InvalidAccessKeyId": "The access key ID is wrong. Create a new S3 access key in Supabase > Project Settings > Storage.",
    "SignatureDoesNotMatch": "The secret key (or the region) is wrong. Copy the secret again; it is shown only once.",
    "AccessDenied": "These keys can't use this bucket. Create a new access key in the same project.",
    "InvalidRequest": "Usually a wrong region. Use the region shown under Supabase > Storage > S3 Connection.",
}


def describe(exc: ClientError) -> str:
    error = exc.response.get("Error", {})
    status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return f"HTTP {status} | {error.get('Code') or '(no code)'} | {error.get('Message') or '(no message)'}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload local design files to the S3 bucket")
    parser.add_argument("--apply", action="store_true", help="upload (default: only list)")
    args = parser.parse_args()

    settings = get_settings()
    missing = [
        name
        for name, value in {
            "S3_BUCKET": settings.s3_bucket,
            "AWS_ACCESS_KEY_ID": settings.aws_access_key_id,
            "AWS_SECRET_ACCESS_KEY": settings.aws_secret_access_key,
        }.items()
        if not value
    ]
    if missing:
        print("Set these first (same values as on Render): " + ", ".join(missing))
        return 1

    root = Path(settings.local_storage_dir).resolve()
    files = sorted(p for p in root.rglob("*") if p.is_file())
    key_id = settings.aws_access_key_id or ""
    print(f"Local files in {root}: {len(files)}")
    print(f"Bucket:   {settings.s3_bucket!r}")
    print(f"Endpoint: {settings.s3_endpoint_url or 'AWS'}")
    print(f"Region:   {settings.aws_region or '(not set)'}")
    print(f"Key ID:   {key_id[:4]}...{key_id[-3:]} ({len(key_id)} characters)")

    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path" if settings.s3_endpoint_url else "auto"},
        ),
    )

    # One check before the files: can these settings reach this bucket at all?
    try:
        client.list_objects_v2(Bucket=settings.s3_bucket, MaxKeys=1)
    except ClientError as exc:
        print(f"\nCannot use the bucket: {describe(exc)}")
        code = exc.response.get("Error", {}).get("Code", "")
        print(HINTS.get(code, "Check the bucket name, endpoint, region and both keys."))
        return 1
    except Exception as exc:  # wrong endpoint, no network, bad region format ...
        print(f"\nCannot reach the endpoint: {exc.__class__.__name__}: {exc}")
        print(
            "Check S3_ENDPOINT_URL (https://<project-ref>.supabase.co/storage/v1/s3) and AWS_REGION."
        )
        return 1
    print("Bucket reachable.\n")

    uploaded = skipped = failed = 0
    for path in files:
        key = path.relative_to(root).as_posix()
        try:
            client.head_object(Bucket=settings.s3_bucket, Key=key)
            skipped += 1
            continue
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") not in ("404", "NoSuchKey", "NotFound"):
                print(f"  ! {key}: {describe(exc)}")
                failed += 1
                continue
        if not args.apply:
            print(f"  would upload  {key}")
            uploaded += 1
            continue
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        try:
            client.put_object(
                Bucket=settings.s3_bucket, Key=key, Body=path.read_bytes(), ContentType=content_type
            )
        except ClientError as exc:
            print(f"  ! {key}: {describe(exc)}")
            failed += 1
            continue
        print(f"  uploaded      {key}")
        uploaded += 1

    verb = "uploaded" if args.apply else "to upload"
    print(f"\n{uploaded} {verb}, {skipped} already in the bucket, {failed} failed.")
    if not args.apply and uploaded:
        print("Run again with --apply to upload them.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
