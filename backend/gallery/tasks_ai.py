from celery import shared_task
from django.db import models, transaction
from PIL import Image

from .ai_presets import LST_LABEL_ZH
from .models import AiLabel, FaceGroup, Photo
from .services import (
    get_clip_embedding_service,
    get_face_recognition_service,
)

@shared_task
def task_clip_vector_and_labels(photo_id: int):
    """
    1) 生成 CLIP 向量
    2) 计算与标签集相似度，写入 ai_label_ids
    """
    try:
        photo = Photo.objects.get(id=photo_id)
        clip_service = get_clip_embedding_service()
        with Image.open(photo.image) as raw_img:
            img = raw_img.convert("RGB")
            try:
                vec = clip_service.encode_image(img)  # (512,)
            finally:
                img.close()

        photo.clip_vector = clip_service.vector_to_bytes(vec)
        photo.vector_done = True

        # 2. 语义标签
        # 向量化标签文本（可缓存）
        txt_vecs = clip_service.encode_texts(LST_LABEL_ZH)  # (N,512)
        sim = (vec[None, :] @ txt_vecs.T)[0]     # 余弦相似：CLIP 已归一化
        top_idx = sim.argsort()[::-1][:5]        # 取 Top-5 标签
        with transaction.atomic():
            photo.save(update_fields=["clip_vector", "vector_done"])
            for idx in top_idx:
                lbl, _ = AiLabel.objects.get_or_create(name=LST_LABEL_ZH[idx], lang="zh")
                photo.ai_label_ids.add(lbl.id)
            photo.ai_done = True
            photo.save(update_fields=["ai_done"])
        return "ok"
    except Exception as e:
        return f"err:{e}"

@shared_task
def task_face_embeddings_and_group(photo_id: int, tol: float = 0.48):
    """
    提取照片中的人脸特征，对每张人脸匹配/归并到 FaceGroup
    tol 越小越严格（0.4~0.6 之间调优）
    """
    face_service = get_face_recognition_service()
    try:
        photo = Photo.objects.get(id=photo_id)
        img = face_service.load_image(photo.image)
        locations = face_service.face_locations(img, model="hog")  # "cnn" 更准但慢
        if not locations:
            photo.face_group_ids = []
            photo.face_done = True
            photo.save(update_fields=["face_group_ids", "face_done"])
            return "no_face"

        encs = face_service.face_encodings(img, locations)  # 128-d

        # 暂缺持久化的人脸向量索引，当前策略：为每个新检测到的人脸创建分组
        group_ids = []
        for _ in encs:
            group = FaceGroup.objects.create(owner=photo.owner, name="")
            group_ids.append(group.id)
            FaceGroup.objects.filter(id=group.id).update(count=models.F("count") + 1)

        photo.face_group_ids = list(set(group_ids))
        photo.face_done = True
        photo.save(update_fields=["face_group_ids", "face_done"])
        return "ok"
    except Exception as e:
        return f"err:{e}"
