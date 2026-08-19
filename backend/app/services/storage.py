import io
import mimetypes
import uuid
from pathlib import Path
from typing import Protocol

import boto3

from ..config import Settings


class BlobStorage(Protocol):
    def save(self, data: bytes, suffix: str) -> str: ...

    def read(self, key: str) -> bytes: ...

    def content_type(self, key: str) -> str: ...

    def delete(self, key: str) -> None: ...


class LocalBlobStorage:
    def __init__(self, root: str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, data: bytes, suffix: str) -> str:
        key = f"{uuid.uuid4()}{suffix.lower()}"
        (self.root / key).write_bytes(data)
        return key

    def read(self, key: str) -> bytes:
        # 只接受文件名，避免通过 ../ 读取上传目录之外的内容。
        safe_key = Path(key).name
        return (self.root / safe_key).read_bytes()

    def content_type(self, key: str) -> str:
        return mimetypes.guess_type(key)[0] or "application/octet-stream"

    def delete(self, key: str) -> None:
        safe_key = Path(key).name
        (self.root / safe_key).unlink(missing_ok=True)


class S3BlobStorage:
    def __init__(self, settings: Settings) -> None:
        self.bucket = settings.resolved_s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.resolved_s3_endpoint,
            aws_access_key_id=settings.resolved_s3_access_key,
            aws_secret_access_key=settings.resolved_s3_secret_key,
            region_name=settings.s3_region,
        )
        # Supabase 上先在控制台建私有 bucket；本地 MinIO 可自动创建。
        if settings.storage_backend.lower() == "minio" or settings.s3_auto_create_bucket:
            self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except Exception:
            self.client.create_bucket(Bucket=self.bucket)

    def save(self, data: bytes, suffix: str) -> str:
        key = f"{uuid.uuid4()}{suffix.lower()}"
        content_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
        self.client.upload_fileobj(
            io.BytesIO(data), self.bucket, key, ExtraArgs={"ContentType": content_type}
        )
        return key

    def read(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=Path(key).name)
        return response["Body"].read()

    def content_type(self, key: str) -> str:
        return mimetypes.guess_type(key)[0] or "application/octet-stream"

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=Path(key).name)


def build_storage(settings: Settings) -> BlobStorage:
    if settings.storage_backend.lower() in {"minio", "s3"}:
        return S3BlobStorage(settings)
    return LocalBlobStorage(settings.local_storage_dir)
