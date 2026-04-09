"""MinIO 客户端 - 用于原始文档的对象存储"""
import io
from datetime import timedelta
from minio import Minio
from minio.error import S3Error
from app.core.config import get_settings

settings = get_settings()

_client: Minio | None = None


def get_minio() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
    return _client


def ensure_bucket() -> None:
    client = get_minio()
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)


def upload_file(object_path: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    client = get_minio()
    client.put_object(
        bucket_name=settings.minio_bucket,
        object_name=object_path,
        data=io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )


def delete_file(object_path: str) -> None:
    client = get_minio()
    try:
        client.remove_object(settings.minio_bucket, object_path)
    except S3Error:
        pass


def get_presigned_url(object_path: str, expires_seconds: int = 3600) -> str:
    client = get_minio()
    return client.presigned_get_object(
        bucket_name=settings.minio_bucket,
        object_name=object_path,
        expires=timedelta(seconds=expires_seconds),
    )


def download_file(object_path: str) -> bytes:
    client = get_minio()
    response = client.get_object(settings.minio_bucket, object_path)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()
