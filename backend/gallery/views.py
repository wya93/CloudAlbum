from rest_framework import viewsets, status, permissions, filters
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from drf_spectacular.utils import extend_schema
import boto3
from botocore.client import Config
from django.conf import settings
from django.shortcuts import get_object_or_404

from .models import Album, Photo, Tag
from .serializers import AlbumSerializer, PhotoSerializer, TagSerializer
from gallery.tasks import generate_thumbnail, extract_exif_task
from django.core.cache import cache
from core.settings import CACHE_TTL
from .models import AlbumShare
from django.utils import timezone
from datetime import timedelta
from .utils_uploads import build_object_key, validate_upload_meta
from .tasks_ai import task_clip_vector_and_labels, task_face_embeddings_and_group

def _s3_client():
    return boto3.client(
        "s3",
        endpoint_url=getattr(settings, "AWS_S3_ENDPOINT_URL", None),
        region_name=getattr(settings, "AWS_S3_REGION_NAME", None),
        aws_access_key_id=getattr(settings, "AWS_ACCESS_KEY_ID", None),
        aws_secret_access_key=getattr(settings, "AWS_SECRET_ACCESS_KEY", None),
        config=Config(signature_version=getattr(settings, "AWS_S3_SIGNATURE_VERSION", "s3v4")),
    )

class AlbumViewSet(viewsets.ModelViewSet):
    """相册管理"""
    serializer_class = AlbumSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Album.objects.filter(owner=self.request.user).order_by("-created_at")

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @extend_schema(summary="上传图片", request=AlbumSerializer)
    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def upload(self, request, pk=None):
        """上传图片"""
        album = self.get_object()
        files = request.FILES.getlist("images")
        if not files:
            return Response({"error": "未选择文件"}, status=status.HTTP_400_BAD_REQUEST)

        photos = []
        for f in files:
            photo = Photo.objects.create(owner=request.user, album=album, image=f)
            generate_thumbnail.delay(photo.id)  # 异步生成缩略图
            extract_exif_task.delay(photo.id)  # 异步生成exif信息
            task_clip_vector_and_labels.delay(photo.id)
            task_face_embeddings_and_group.delay(photo.id)
            photos.append(photo)

        return Response(PhotoSerializer(photos, many=True).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def photos(self, request, pk=None):
        """获取相册内的照片"""
        cache_key = f"album_photos_{pk}_{request.user.id}"
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)
        album = self.get_object()
        photos = album.photos.all().order_by("-uploaded_at")
        serializer = PhotoSerializer(photos, many=True)
        cache.set(cache_key, serializer.data, CACHE_TTL)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def share(self, request, pk=None):
        """创建临时分享链接"""
        album = self.get_object()
        expires_in = int(request.data.get("expires_in", 60 * 60 * 24))  # 默认24小时
        share = AlbumShare.objects.create(
            album=album,
            expires_at=timezone.now() + timedelta(seconds=expires_in),
        )
        url = f"{request.build_absolute_uri('/api/gallery/share/')}{share.token}/"
        return Response({"share_url": url, "expires_at": share.expires_at})

    @action(methods=['post'], detail=False, url_path='presign_upload')
    def persion_upload(self, request):
        if getattr(settings, 'STORAGE_BACKEND', 'local') != 's3':
            return Response({'message': '当前为本地存储，请用表单上传接口'}, status=status.HTTP_400_BAD_REQUEST)
        album_id = int(request.data.get("album_id", 0))
        filename = request.data.get("filename") or "image.jpg"
        content_type = request.data.get("content_type") or "image/jpeg"
        size = int(request.data.get("size", 0))
        album = get_object_or_404(Album, id=album_id, owner=request.user)

        try:
            validate_upload_meta(content_type, size)
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)

        object_key = build_object_key(request.user.id, album.id, filename)
        s3 = _s3_client()
        url = s3.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": BUCKET,
                "Key": object_key,
                "ContentType": content_type,
                "ACL": "private",
            },
            ExpiresIn=60 * 5,
        )
        return Response({"object_key": object_key, "url": url, "method": "PUT", "headers": {"Content-Type": content_type}})

    @action(methods=['post'], detail=False, url_path='finalize_upload')
    def finalize_upload(self, request):
        """
        客户端直传完成后回调
        body: {album_id, object_key, title?, tag_ids?[]}
        """
        album_id = int(request.data.get("album_id", 0))
        object_key = request.data.get("object_key")
        title = request.data.get("title", "")
        tag_ids = request.data.get("tag_ids", [])

        album = get_object_or_404(Album, id=album_id, owner=request.user)
        if not object_key or not object_key.startswith(f"photos/{request.user.id}/{album.id}/"):
            return Response({"detail": "object_key 非法"}, status=400)

        photo = Photo.objects.create(owner=request.user, album=album, image=object_key, title=title)
        # 设置标签（可选）
        if tag_ids:
            photo.tags.set(tag_ids)

        # 异步：缩略图 + EXIF
        generate_thumbnail.delay(photo.id)
        extract_exif_task.delay(photo.id)
        task_clip_vector_and_labels.delay(photo.id)
        task_face_embeddings_and_group.delay(photo.id)

        return Response(PhotoSerializer(photo).data, status=201)

    # ---------- Multipart ----------

    @action(methods=['post'], detail=False, url_path='multipart_initiate')
    def multipart_initiate(self, request):
        """
        初始化分片上传
        body: {album_id, filename, content_type, size}
        """
        if getattr(settings, "STORAGE_BACKEND", "local") != "s3":
            return Response({"detail": "当前为本地存储，请使用表单上传接口"}, status=400)

        album_id = int(request.data.get("album_id", 0))
        filename = request.data.get("filename") or "image.jpg"
        content_type = request.data.get("content_type") or "image/jpeg"
        size = int(request.data.get("size", 0))

        album = get_object_or_404(Album, id=album_id, owner=request.user)

        try:
            validate_upload_meta(content_type, size)
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)

        object_key = build_object_key(request.user.id, album.id, filename)
        s3 = _s3_client()
        init = s3.create_multipart_upload(Bucket=BUCKET, Key=object_key, ContentType=content_type, ACL="private")
        upload_id = init["UploadId"]
        return Response({"object_key": object_key, "upload_id": upload_id})

    @action(methods=['post'], detail=False, url_path='multipart_sign_part')
    def multipart_sign_part(self, request):
        """
        对单个分片签名
        body: {object_key, upload_id, part_number(int)}
        """
        object_key = request.data.get("object_key")
        upload_id = request.data.get("upload_id")
        part_number = int(request.data.get("part_number", 0))

        # 基本校验：object_key 应在当前用户/相册路径下（可选更严格：解析 path 校验）
        if not object_key or f"/{request.user.id}/" not in object_key:
            return Response({"detail": "object_key 非法"}, status=400)

        s3 = _s3_client()
        url = s3.generate_presigned_url(
            ClientMethod="upload_part",
            Params={"Bucket": BUCKET, "Key": object_key, "UploadId": upload_id, "PartNumber": part_number},
            ExpiresIn=60 * 10,
        )
        return Response({"url": url})

    @action(methods=['post'], detail=False, url_path='multipart_complete')
    def multipart_complete(self, request):
        """
        合并所有分片
        body: {object_key, upload_id, parts: [{ETag, PartNumber}]}
        """
        object_key = request.data.get("object_key")
        upload_id = request.data.get("upload_id")
        tag_ids = request.data.get("upload_id")
        parts = request.data.get("parts", [])
        title = request.data.get("title", "")
        album_id = int(request.data.get("album_id", 0))
        album = get_object_or_404(Album, id=album_id, owner=request.user)
        s3 = _s3_client()
        s3.complete_multipart_upload(
            Bucket=BUCKET,
            Key=object_key,
            UploadId=upload_id,
            MultipartUpload={"Parts": sorted(parts, key=lambda x: x["PartNumber"])},
        )
        photo = Photo.objects.create(owner=request.user, album=album, image=object_key, title=title)
        # 设置标签（可选）
        if tag_ids:
            photo.tags.set(tag_ids)

        # 异步：缩略图 + EXIF
        generate_thumbnail.delay(photo.id)
        extract_exif_task.delay(photo.id)
        task_clip_vector_and_labels.delay(photo.id)
        task_face_embeddings_and_group.delay(photo.id)

        return Response({"status": "completed"})


class PhotoViewSet(viewsets.ModelViewSet):
    """图片管理"""
    serializer_class = PhotoSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["title", "tags__name"]
    ordering_fields = ["uploaded_at", "title"]

    def get_queryset(self):
        return Photo.objects.filter(owner=self.request.user).order_by("-uploaded_at")

    def perform_destroy(self, instance):
        """删除时同时删除文件"""
        instance.image.delete(save=False)
        if instance.thumbnail:
            instance.thumbnail.delete(save=False)
        instance.delete()


class TagViewSet(viewsets.ModelViewSet):
    """标签管理"""
    serializer_class = TagSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Tag.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

@api_view(["GET"])
def public_share_view(request, token):
    """访问分享链接"""
    try:
        share = AlbumShare.objects.select_related("album").get(token=token)
        if not share.is_valid():
            return Response({"error": "分享已过期"}, status=status.HTTP_410_GONE)
        photos = share.album.photos.all().order_by("-uploaded_at")
        serializer = PhotoSerializer(photos, many=True)
        return Response({
            "album": share.album.name,
            "photos": serializer.data
        })
    except AlbumShare.DoesNotExist:
        return Response({"error": "无效的分享链接"}, status=status.HTTP_404_NOT_FOUND)