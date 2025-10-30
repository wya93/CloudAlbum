from rest_framework.decorators import api_view, permission_classes
from .models import Photo
from .serializers import PhotoSerializer
from django.db.models import Q
from rest_framework.response import Response
from rest_framework import status, permissions

@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def auto_by_label(request):
    """
    根据特征查找照片
    """
    label = request.query_params.get('label')
    label_id = request.query_params.get('label_id')
    if not label or not label_id:
        return Response({'message': '缺少label参数'}, status=status.HTTP_400_BAD_REQUEST)
    qs=Photo.objects.filter(owner=request.user).filter(Q(ai_label_ids__name=label) | Q(ai_label_ids__id=label_id))
    return Response(PhotoSerializer(qs, many=True).data)

@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def auto_by_face(request):
    """
    根据特征查找照片
    """
    face = request.query_params.get('face')
    qs=Photo.objects.filter(face_group_ids__contains=[face])
    return Response(PhotoSerializer(qs, many=True).data)