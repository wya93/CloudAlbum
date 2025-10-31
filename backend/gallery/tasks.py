"""与照片处理相关的 Celery 任务。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Dict, Optional

from celery import shared_task
from PIL import Image, ImageOps
from django.core.files.base import ContentFile

from .models import Photo
from .services.metadata import extract_exif_metadata

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TaskResult:
    """统一封装任务返回值，兼容字符串序列化。"""

    status: str
    detail: Optional[str] = None

    def render(self) -> str:
        if not self.detail:
            return self.status
        return f"{self.status}:{self.detail}"

    @classmethod
    def ok(cls) -> "TaskResult":
        return cls(status="ok")

    @classmethod
    def skip(cls, reason: str) -> "TaskResult":
        return cls(status="skip", detail=reason)

    @classmethod
    def missing(cls, entity: str) -> "TaskResult":
        return cls(status="missing", detail=entity)

    @classmethod
    def error(cls, message: str) -> "TaskResult":
        return cls(status="err", detail=message)


def _generate_thumbnail_file(photo: Photo) -> ContentFile:
    """生成缩略图文件对象，并自动处理方向。"""

    with Image.open(photo.image) as raw_img:
        img = ImageOps.exif_transpose(raw_img)
        img.thumbnail((300, 300))
        buffer = BytesIO()
        img.save(buffer, format="JPEG")
    return ContentFile(buffer.getvalue())


def _get_photo(photo_id: int) -> Optional[Photo]:
    return Photo.objects.filter(id=photo_id).first()


@shared_task
def generate_thumbnail(photo_id: int) -> str:
    """异步生成缩略图。"""

    photo = _get_photo(photo_id)
    if photo is None:
        return TaskResult.missing("photo").render()

    if not photo.image:
        return TaskResult.skip("no_image").render()
    if photo.thumbnail:
        return TaskResult.skip("has_thumbnail").render()

    try:
        thumb_content = _generate_thumbnail_file(photo)
        thumb_name = Path(photo.image.name).stem + "_thumb.jpg"
        photo.thumbnail.save(thumb_name, thumb_content, save=True)
    except Exception as exc:  # pragma: no cover - 依赖外部文件系统
        logger.exception("生成缩略图失败", extra={"photo_id": photo_id})
        return TaskResult.error(str(exc)).render()

    return TaskResult.ok().render()


@shared_task
def extract_exif_task(photo_id: int) -> str:
    """提取 EXIF 信息并保存。"""

    photo = _get_photo(photo_id)
    if photo is None:
        return TaskResult.missing("photo").render()

    try:
        updates: Dict[str, Optional[str]] = extract_exif_metadata(photo)
    except Exception as exc:  # pragma: no cover - 依赖 PIL/Exif 外部实现
        logger.exception("EXIF 提取失败", extra={"photo_id": photo_id})
        return TaskResult.error(str(exc)).render()

    if not updates:
        return TaskResult.skip("no_updates").render()

    for field, value in updates.items():
        setattr(photo, field, value)

    photo.save(update_fields=list(updates.keys()))
    return TaskResult.ok().render()
