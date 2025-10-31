"""存储集成相关工具。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import boto3
from botocore.client import Config
from django.conf import settings


class StorageBackendNotConfigured(RuntimeError):
    """当目标存储后端不可用时抛出。"""


@dataclass(frozen=True)
class S3Config:
    bucket_name: str
    endpoint_url: Optional[str]
    region_name: Optional[str]
    access_key: Optional[str]
    secret_key: Optional[str]
    signature_version: str


class S3UploadService:
    """封装上传接口使用到的 S3 操作。"""

    def __init__(self, config: S3Config) -> None:
        self.config = config
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = boto3.client(
                "s3",
                endpoint_url=self.config.endpoint_url,
                region_name=self.config.region_name,
                aws_access_key_id=self.config.access_key,
                aws_secret_access_key=self.config.secret_key,
                config=Config(signature_version=self.config.signature_version),
            )
        return self._client

    def generate_presigned_put(self, object_key: str, content_type: str, expires: int = 300) -> str:
        return self.client.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": self.config.bucket_name,
                "Key": object_key,
                "ContentType": content_type,
                "ACL": "private",
            },
            ExpiresIn=expires,
        )

    def initiate_multipart(self, object_key: str, content_type: str) -> Dict[str, Any]:
        return self.client.create_multipart_upload(
            Bucket=self.config.bucket_name,
            Key=object_key,
            ContentType=content_type,
            ACL="private",
        )

    def generate_presigned_part_url(self, object_key: str, upload_id: str, part_number: int, expires: int = 600) -> str:
        return self.client.generate_presigned_url(
            ClientMethod="upload_part",
            Params={
                "Bucket": self.config.bucket_name,
                "Key": object_key,
                "UploadId": upload_id,
                "PartNumber": part_number,
            },
            ExpiresIn=expires,
        )

    def complete_multipart(self, object_key: str, upload_id: str, parts: list[dict[str, Any]]) -> Dict[str, Any]:
        return self.client.complete_multipart_upload(
            Bucket=self.config.bucket_name,
            Key=object_key,
            UploadId=upload_id,
            MultipartUpload={"Parts": sorted(parts, key=lambda item: item["PartNumber"])},
        )


def _load_s3_config() -> S3Config:
    bucket_name = getattr(settings, "AWS_STORAGE_BUCKET_NAME", None)
    if not bucket_name:
        raise StorageBackendNotConfigured("AWS_STORAGE_BUCKET_NAME 未配置，无法使用 S3 直传能力")

    return S3Config(
        bucket_name=bucket_name,
        endpoint_url=getattr(settings, "AWS_S3_ENDPOINT_URL", None),
        region_name=getattr(settings, "AWS_S3_REGION_NAME", None),
        access_key=getattr(settings, "AWS_ACCESS_KEY_ID", None),
        secret_key=getattr(settings, "AWS_SECRET_ACCESS_KEY", None),
        signature_version=getattr(settings, "AWS_S3_SIGNATURE_VERSION", "s3v4"),
    )


def get_upload_storage_service() -> S3UploadService:
    storage_backend = getattr(settings, "STORAGE_BACKEND", "local")
    if storage_backend != "s3":
        raise StorageBackendNotConfigured("当前存储后端非 S3，无法使用直传接口")

    return S3UploadService(_load_s3_config())
