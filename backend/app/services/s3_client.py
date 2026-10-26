import os
import uuid

import boto3

PRESIGNED_URL_EXPIRY_SECONDS = 300  # 5 minutes
MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024  # invoices/statements are tiny; generous ceiling


def _client():
    return boto3.client(
        "s3",
        region_name=os.environ["AWS_REGION"],
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
    )


def _bucket() -> str:
    return os.environ["AWS_BUCKET_NAME"]


def build_object_key(subdir: str, filename: str) -> str:
    return f"{subdir}/{uuid.uuid4().hex}_{filename}"


def generate_upload_post(object_key: str, content_type: str) -> dict:
    return _client().generate_presigned_post(
        Bucket=_bucket(),
        Key=object_key,
        Fields={"Content-Type": content_type},
        Conditions=[
            {"Content-Type": content_type},
            ["content-length-range", 1, MAX_UPLOAD_SIZE_BYTES],
        ],
        ExpiresIn=PRESIGNED_URL_EXPIRY_SECONDS,
    )


def generate_get_url(object_key: str) -> str:
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": _bucket(), "Key": object_key},
        ExpiresIn=PRESIGNED_URL_EXPIRY_SECONDS,
    )


def delete_object(object_key: str) -> None:
    _client().delete_object(Bucket=_bucket(), Key=object_key)


def download_object_bytes(object_key: str) -> bytes:
    response = _client().get_object(Bucket=_bucket(), Key=object_key)
    return response["Body"].read()
