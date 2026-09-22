import mimetypes
from pathlib import Path
from uuid import uuid4

from Service.config import get_settings


def _get_s3_client():
    import boto3

    settings = get_settings()
    kwargs = {"region_name": settings.aws_region}

    if settings.aws_access_key_id and settings.aws_secret_access_key:
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key

    return boto3.client("s3", **kwargs)


def _require_bucket() -> str:
    bucket = get_settings().aws_s3_bucket
    if not bucket:
        raise RuntimeError("AWS_S3_BUCKET is not configured.")
    return bucket


def _public_url(bucket: str, key: str) -> str:
    settings = get_settings()
    if settings.aws_s3_public_base_url:
        return f"{settings.aws_s3_public_base_url.rstrip('/')}/{key}"

    if settings.aws_region == "us-east-1":
        return f"https://{bucket}.s3.amazonaws.com/{key}"

    return f"https://{bucket}.s3.{settings.aws_region}.amazonaws.com/{key}"


def upload_bytes(
    content: bytes,
    *,
    folder: str,
    filename: str,
    content_type: str,
) -> dict:
    bucket = _require_bucket()
    key = f"{folder.strip('/')}/{uuid4().hex}-{filename}"

    _get_s3_client().put_object(
        Bucket=bucket,
        Key=key,
        Body=content,
        ContentType=content_type,
    )

    return {
        "bucket": bucket,
        "key": key,
        "s3_uri": f"s3://{bucket}/{key}",
        "url": _public_url(bucket, key),
    }


def upload_file(path: str, *, folder: str, content_type: str | None = None) -> dict:
    file_path = Path(path)
    resolved_content_type = (
        content_type
        or mimetypes.guess_type(file_path.name)[0]
        or "application/octet-stream"
    )
    return upload_bytes(
        file_path.read_bytes(),
        folder=folder,
        filename=file_path.name,
        content_type=resolved_content_type,
    )
