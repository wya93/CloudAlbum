from celery import shared_task
from PIL import Image
from io import BytesIO
from django.core.files.base import ContentFile
from pathlib import Path

from .models import Photo
from .services.metadata import extract_exif_metadata


def _generate_thumbnail_file(photo: Photo) -> ContentFile:
    img = Image.open(photo.image)
    try:
        img.thumbnail((300, 300))
        buffer = BytesIO()
        img.save(buffer, format="JPEG")
        return ContentFile(buffer.getvalue())
    finally:
        img.close()


@shared_task
def generate_thumbnail(photo_id):
    """异步生成缩略图"""
    try:
        photo = Photo.objects.get(id=photo_id)
    except Photo.DoesNotExist:
        return "missing"

    if not photo.image or photo.thumbnail:
        return "skip"

    try:
        thumb_content = _generate_thumbnail_file(photo)
        thumb_name = Path(photo.image.name).stem + "_thumb.jpg"
        photo.thumbnail.save(thumb_name, thumb_content, save=True)
        return "ok"
    except Exception as exc:
        return f"err:{exc}"


@shared_task
def extract_exif_task(photo_id):
    try:
        photo = Photo.objects.get(id=photo_id)
    except Photo.DoesNotExist:
        return "missing"

    try:
        updates = extract_exif_metadata(photo)
    except Exception as exc:
        return f"err:{exc}"

    if not updates:
        return "skip"

    for field, value in updates.items():
        setattr(photo, field, value)

    photo.save(update_fields=list(updates.keys()))
    return "ok"
