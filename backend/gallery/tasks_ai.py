"""与 AI 相关的异步任务。"""

from __future__ import annotations

import logging
from typing import Iterable, List

from celery import shared_task
from django.db import models, transaction
from PIL import Image

from .ai_presets import get_labels
from .models import AiLabel, FaceGroup, Photo
from .services import get_clip_embedding_service, get_face_recognition_service
from .tasks import TaskResult

logger = logging.getLogger(__name__)


def _get_photo(photo_id: int) -> Photo | None:
    return Photo.objects.filter(id=photo_id).first()


def _ensure_labels(language: str) -> List[AiLabel]:
    """确保标签实体存在，按给定语言返回对象。"""

    labels = get_labels(language)
    existing = {lbl.name: lbl for lbl in AiLabel.objects.filter(name__in=labels, lang=language)}
    to_create = [AiLabel(name=text, lang=language) for text in labels if text not in existing]
    if to_create:
        AiLabel.objects.bulk_create(to_create, ignore_conflicts=True)
        existing.update({lbl.name: lbl for lbl in AiLabel.objects.filter(name__in=labels, lang=language)})
    # 按原始顺序返回
    return [existing[text] for text in labels]


def _select_top_labels(similarities, labels: Iterable[AiLabel], top_k: int) -> List[AiLabel]:
    indexed = list(zip(similarities, labels))
    indexed.sort(key=lambda item: item[0], reverse=True)
    return [label for _, label in indexed[:top_k]]


@shared_task
def task_clip_vector_and_labels(photo_id: int, language: str = "zh", top_k: int = 5) -> str:
    """计算照片的 CLIP 向量并打上语义标签。"""

    photo = _get_photo(photo_id)
    if photo is None:
        return TaskResult.missing("photo").render()
    if not photo.image:
        return TaskResult.skip("no_image").render()

    try:
        clip_service = get_clip_embedding_service()
    except RuntimeError as exc:  # pragma: no cover - 依赖可选库
        logger.exception("CLIP 服务初始化失败", extra={"photo_id": photo_id})
        return TaskResult.error(f"deps:{exc}").render()

    try:
        with Image.open(photo.image) as raw_img:
            rgb_img = raw_img.convert("RGB")
            vector = clip_service.encode_image(rgb_img)
    except Exception as exc:  # pragma: no cover - 依赖外部文件
        logger.exception("CLIP 图像编码失败", extra={"photo_id": photo_id})
        return TaskResult.error(str(exc)).render()

    try:
        label_objs = _ensure_labels(language)
        text_vectors = clip_service.encode_texts([lbl.name for lbl in label_objs])
        similarities = (vector[None, :] @ text_vectors.T)[0]
        top_labels = _select_top_labels(similarities, label_objs, top_k)
    except Exception as exc:  # pragma: no cover - numpy/CLIP 初始化失败时触发
        logger.exception("CLIP 文本标签计算失败", extra={"photo_id": photo_id})
        return TaskResult.error(str(exc)).render()

    with transaction.atomic():
        photo.clip_vector = clip_service.vector_to_bytes(vector)
        photo.vector_done = True
        photo.save(update_fields=["clip_vector", "vector_done"])
        if top_labels:
            photo.ai_label_ids.add(*[label.id for label in top_labels])
            photo.ai_done = True
            photo.save(update_fields=["ai_done"])

    return TaskResult.ok().render()


@shared_task
def task_face_embeddings_and_group(photo_id: int, tol: float = 0.48) -> str:
    """提取人脸特征并创建分组。"""

    photo = _get_photo(photo_id)
    if photo is None:
        return TaskResult.missing("photo").render()
    if not photo.image:
        return TaskResult.skip("no_image").render()

    try:
        face_service = get_face_recognition_service()
    except RuntimeError as exc:  # pragma: no cover - 依赖可选库
        logger.exception("人脸服务初始化失败", extra={"photo_id": photo_id})
        return TaskResult.error(f"deps:{exc}").render()

    try:
        image_array = face_service.load_image(photo.image)
        locations = face_service.face_locations(image_array, model="hog")
    except Exception as exc:  # pragma: no cover - face_recognition 内部异常
        logger.exception("人脸检测失败", extra={"photo_id": photo_id})
        return TaskResult.error(str(exc)).render()

    if not locations:
        photo.face_group_ids = []
        photo.face_done = True
        photo.save(update_fields=["face_group_ids", "face_done"])
        return TaskResult.skip("no_face").render()

    try:
        encodings = face_service.face_encodings(image_array, locations)
    except Exception as exc:  # pragma: no cover
        logger.exception("人脸向量提取失败", extra={"photo_id": photo_id})
        return TaskResult.error(str(exc)).render()

    # 当前策略：每张人脸单独创建分组，后续可接入向量检索做合并
    with transaction.atomic():
        new_groups = [FaceGroup(owner=photo.owner, name="") for _ in encodings]
        FaceGroup.objects.bulk_create(new_groups)
        group_ids = [group.id for group in new_groups if group.id is not None]
        if group_ids:
            FaceGroup.objects.filter(id__in=group_ids).update(count=models.F("count") + 1)
            photo.face_group_ids = group_ids
        else:
            photo.face_group_ids = []
        photo.face_done = True
        photo.save(update_fields=["face_group_ids", "face_done"])

    return TaskResult.ok().render()
