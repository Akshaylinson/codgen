import os
import uuid
import boto3
from botocore.exceptions import ClientError

S3_BUCKET      = os.environ.get("S3_BUCKET", "")
S3_REGION      = os.environ.get("S3_REGION", "us-east-1")
S3_ENDPOINT    = os.environ.get("S3_ENDPOINT", "")          # Cloudflare R2 or custom
S3_ACCESS_KEY  = os.environ.get("S3_ACCESS_KEY", "")
S3_SECRET_KEY  = os.environ.get("S3_SECRET_KEY", "")
CDN_BASE_URL   = os.environ.get("CDN_BASE_URL", "")         # e.g. https://cdn.yourdomain.com

_s3 = None


def _get_client():
    global _s3
    if _s3 is None:
        kwargs = dict(
            region_name=S3_REGION,
            aws_access_key_id=S3_ACCESS_KEY,
            aws_secret_access_key=S3_SECRET_KEY,
        )
        if S3_ENDPOINT:
            kwargs["endpoint_url"] = S3_ENDPOINT
        _s3 = boto3.client("s3", **kwargs)
    return _s3


def storage_enabled() -> bool:
    return bool(S3_BUCKET and S3_ACCESS_KEY and S3_SECRET_KEY)


async def upload_to_storage(file_bytes: bytes, filename: str, content_type: str) -> str:
    """
    Upload file_bytes to S3/R2 and return the public URL.
    Falls back to returning None if storage is not configured.
    """
    if not storage_enabled():
        return None

    ext = filename.rsplit(".", 1)[-1] if "." in filename else "bin"
    key = f"uploads/{uuid.uuid4().hex}.{ext}"

    client = _get_client()
    client.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=file_bytes,
        ContentType=content_type,
        ACL="public-read",
    )

    if CDN_BASE_URL:
        return f"{CDN_BASE_URL.rstrip('/')}/{key}"
    if S3_ENDPOINT:
        return f"{S3_ENDPOINT.rstrip('/')}/{S3_BUCKET}/{key}"
    return f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{key}"
