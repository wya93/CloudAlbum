from datetime import datetime

import numpy as np
from django.db.models.functions import ExtractDay, ExtractMonth
from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from ..models import Photo
from ..serializers import PhotoSerializer


def _bytes_to_np(buffer):
    return np.frombuffer(buffer, dtype="float32")

@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def similar_photos(request, photo_id: int):
    """
    找相似图片：余弦相似度 Top-K
    """
    k = int(request.query_params.get("k", 12))
    cur = Photo.objects.filter(id=photo_id, owner=request.user, clip_vector__isnull=False).first()
    if not cur:
        return Response({"detail": "未找到向量"}, status=404)
    vec = _bytes_to_np(cur.clip_vector)
    vec /= (np.linalg.norm(vec) + 1e-9)

    # 候选集（同用户）
    candidates = Photo.objects.filter(owner=request.user, clip_vector__isnull=False).exclude(id=photo_id)
    scores = []
    for p in candidates:
        v = _bytes_to_np(p.clip_vector)
        v /= (np.linalg.norm(v) + 1e-9)
        s = float(np.dot(vec, v))
        scores.append((s, p.id))
    scores.sort(reverse=True)
    top_ids = [pid for _, pid in scores[:k]]
    items = Photo.objects.filter(id__in=top_ids)
    # 保持排序
    id_idx = {pid: i for i, pid in enumerate(top_ids)}
    items = sorted(items, key=lambda x: id_idx[x.id])

    return Response(PhotoSerializer(items, many=True).data)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def memories_today(request):
    today = datetime.utcnow()
    qs = (Photo.objects
          .filter(owner=request.user, taken_at__isnull=False)
          .annotate(m=ExtractMonth("taken_at"), d=ExtractDay("taken_at"))
          .filter(m=today.month, d=today.day)
          .order_by("-taken_at")[:200])
    return Response(PhotoSerializer(qs, many=True).data)
