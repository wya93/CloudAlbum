import io
import numpy as np
from celery import shared_task
from django.conf import settings
from django.db import transaction
from PIL import Image
from .models import Photo, AiLabel, FaceGroup
from .ai_presets import LST_LABEL_ZH

# ---------- CLIP ----------
import torch
import open_clip

_device = "cpu"
_model, _preprocess, _tokenizer = None, None, None

def _load_clip():
    global _model, _preprocess, _tokenizer
    if _model is None:
        _model, _, _ = open_clip.create_model_and_transforms('ViT-B-32', pretrained='openai')
        _tokenizer = open_clip.get_tokenizer('ViT-B-32')
        _model = _model.eval().to(_device)
        _preprocess = _
    return _model, _preprocess, _tokenizer

def _img_to_tensor(img: Image.Image):
    _, preprocess, _ = _load_clip()
    return preprocess(img).unsqueeze(0).to(_device)

def _encode_texts(texts):
    model, _, tokenizer = _load_clip()
    with torch.no_grad():
        tok = tokenizer(texts)
        txt_feat = model.encode_text(tok.to(_device))
        txt_feat /= txt_feat.norm(dim=-1, keepdim=True)
    return txt_feat.cpu().numpy()

def _encode_image(img: Image.Image):
    model, preprocess, _ = _load_clip()
    with torch.no_grad():
        img_tensor = preprocess(img).unsqueeze(0).to(_device)
        img_feat = model.encode_image(img_tensor)
        img_feat /= img_feat.norm(dim=-1, keepdim=True)
    return img_feat.cpu().numpy()[0].astype("float32")

def _np_to_bytes(arr: np.ndarray) -> bytes:
    return arr.astype("float32").tobytes()

def _bytes_to_np(b: bytes) -> np.ndarray:
    return np.frombuffer(b, dtype="float32")

@shared_task
def task_clip_vector_and_labels(photo_id: int):
    """
    1) 生成 CLIP 向量
    2) 计算与标签集相似度，写入 ai_label_ids
    """
    try:
        photo = Photo.objects.get(id=photo_id)
        img = Image.open(photo.image).convert("RGB")

        # 1. 向量
        vec = _encode_image(img)  # (512,)
        photo.clip_vector = _np_to_bytes(vec)
        photo.vector_done = True

        # 2. 语义标签
        # 向量化标签文本（可缓存）
        txt_vecs = _encode_texts(LST_LABEL_ZH)  # (N,512)
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

# ---------- Face ----------
# 简单人脸方案：face_recognition（CPU可用）
import face_recognition

@shared_task
def task_face_embeddings_and_group(photo_id: int, tol: float = 0.48):
    """
    提取照片中的人脸特征，对每张人脸匹配/归并到 FaceGroup
    tol 越小越严格（0.4~0.6 之间调优）
    """
    try:
        photo = Photo.objects.get(id=photo_id)
        img = face_recognition.load_image_file(photo.image)
        locations = face_recognition.face_locations(img, model="hog")  # "cnn" 更准但慢
        if not locations:
            photo.face_group_ids = []
            photo.face_done = True
            photo.save(update_fields=["face_group_ids", "face_done"])
            return "no_face"

        encs = face_recognition.face_encodings(img, locations)  # 128-d

        # 将每张人脸与现有组做最近邻匹配（简化方案：均值向量/首次成员向量）
        group_ids = []
        for enc in encs:
            enc_np = np.array(enc)
            # 取该用户下的所有组尝试匹配（小数据量可行；大量数据需维护缓存索引）
            groups = FaceGroup.objects.filter(owner=photo.owner)
            best_gid, best_dist = None, 9e9
            for g in groups:
                # 暂不存组向量，走样本抽样匹配（生产中建议建表保存/采样）
                # 这里简化：遍历该组内若干代表照片的人脸向量（略），用 tol 阈值判断
                pass

            # 简化：没有历史索引则新建组
            if best_gid is None or best_dist > tol:
                g = FaceGroup.objects.create(owner=photo.owner, name="")
                best_gid = g.id
            group_ids.append(best_gid)
            # 更新计数
            FaceGroup.objects.filter(id=best_gid).update(count=models.F("count") + 1)

        photo.face_group_ids = list(set(group_ids))
        photo.face_done = True
        photo.save(update_fields=["face_group_ids", "face_done"])
        return "ok"
    except Exception as e:
        return f"err:{e}"
