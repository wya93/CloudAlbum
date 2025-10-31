"""上传编排相关工具。"""

from __future__ import annotations

from typing import Iterable, List

from ..models import Album, Photo
from ..tasks import generate_thumbnail, extract_exif_task
from ..tasks_ai import task_clip_vector_and_labels, task_face_embeddings_and_group


def dispatch_post_upload_tasks(photo_id: int) -> None:
    """为照片调度异步处理流水线。"""

    generate_thumbnail.delay(photo_id)
    extract_exif_task.delay(photo_id)
    task_clip_vector_and_labels.delay(photo_id)
    task_face_embeddings_and_group.delay(photo_id)


def create_photos_from_form_upload(owner, album: Album, files: Iterable) -> List[Photo]:
    photos: List[Photo] = []
    for uploaded in files:
        photo = Photo.objects.create(owner=owner, album=album, image=uploaded)
        dispatch_post_upload_tasks(photo.id)
        photos.append(photo)
    return photos
