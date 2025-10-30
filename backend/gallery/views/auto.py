from rest_framework.decorators import api_view, permission_classes
from django.db.models import Q
from rest_framework import status, permissions
from rest_framework.response import Response

from ..models import Photo
from ..serializers import PhotoSerializer

@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def auto_by_label(request):
    """
    根据特征查找照片
    """
    label = request.query_params.get("label")
    label_id = request.query_params.get("label_id")
    if not label and not label_id:
        return Response({"message": "缺少 label 参数"}, status=status.HTTP_400_BAD_REQUEST)

    qs = Photo.objects.filter(owner=request.user)
    if label:
        qs = qs.filter(ai_label_ids__name=label)
    if label_id:
        qs = qs.filter(ai_label_ids__id=label_id)

    return Response(PhotoSerializer(qs.distinct(), many=True).data)

@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def auto_by_face(request):
    """
    根据特征查找照片
    """
    face = request.query_params.get("face")
    if not face:
        return Response({"message": "缺少 face 参数"}, status=status.HTTP_400_BAD_REQUEST)

    qs = Photo.objects.filter(owner=request.user, face_group_ids__contains=[face])
    return Response(PhotoSerializer(qs, many=True).data)
