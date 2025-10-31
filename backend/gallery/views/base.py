from rest_framework import viewsets, status, permissions, filters
from rest_framework.decorators import action, api_view
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema
from django.core.cache import cache
from django.core.exceptions import ValidationError
from core.settings import CACHE_TTL

from ..models import Photo, Tag, AlbumShare
from ..serializers import AlbumSerializer, PhotoSerializer, TagSerializer
from ..services import StorageBackendNotConfigured
from ..services.use_cases import AlbumUseCase

class AlbumViewSet(viewsets.ModelViewSet):
    """相册管理"""
    serializer_class = AlbumSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_use_case(self) -> AlbumUseCase:
        if not hasattr(self, "_album_use_case"):
            self._album_use_case = AlbumUseCase(self.request.user)
        return self._album_use_case

    @staticmethod
    def _parse_tag_ids(raw):
        if isinstance(raw, str):
            raw = [raw]
        return [int(tag_id) for tag_id in raw if str(tag_id).strip()]

    def get_queryset(self):
        return self.get_use_case().albums()

    def perform_create(self, serializer):
        self.get_use_case().create_album(serializer)

    @extend_schema(summary="上传图片", request=AlbumSerializer)
    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def upload(self, request, pk=None):
        """上传图片"""
        album = self.get_use_case().get_album(int(pk))
        files = request.FILES.getlist("images")
        if not files:
            return Response({"error": "未选择文件"}, status=status.HTTP_400_BAD_REQUEST)

        photos = self.get_use_case().upload_from_form(album, files)

        return Response(PhotoSerializer(photos, many=True).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def photos(self, request, pk=None):
        """获取相册内的照片"""
        cache_key = f"album_photos_{pk}_{request.user.id}"
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)
        album = self.get_use_case().get_album(int(pk))
        photos = self.get_use_case().list_album_photos(album)
        serializer = PhotoSerializer(photos, many=True)
        cache.set(cache_key, serializer.data, CACHE_TTL)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def share(self, request, pk=None):
        """创建临时分享链接"""
        album = self.get_use_case().get_album(int(pk))
        expires_in = int(request.data.get("expires_in", 60 * 60 * 24))  # 默认24小时
        share = self.get_use_case().create_share(album, expires_in)
        url = f"{request.build_absolute_uri('/api/gallery/share/')}{share.token}/"
        return Response({"share_url": url, "expires_at": share.expires_at})

    @action(methods=['post'], detail=False, url_path='presign_upload')
    def presign_upload(self, request):
        album_id = int(request.data.get("album_id", 0))
        filename = request.data.get("filename") or "image.jpg"
        content_type = request.data.get("content_type") or "image/jpeg"
        size = int(request.data.get("size", 0))
        use_case = self.get_use_case()
        try:
            envelope = use_case.presign_upload(album_id, filename, content_type, size)
        except StorageBackendNotConfigured as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except ValidationError as exc:
            raise DRFValidationError(exc.messages)
        return Response(envelope.to_dict())

    @action(methods=['post'], detail=False, url_path='finalize_upload')
    def finalize_upload(self, request):
        """
        客户端直传完成后回调
        body: {album_id, object_key, title?, tag_ids?[]}
        """
        album_id = int(request.data.get("album_id", 0))
        object_key = request.data.get("object_key")
        title = request.data.get("title", "")
        try:
            tag_ids = self._parse_tag_ids(request.data.get("tag_ids", []))
        except ValueError:
            raise DRFValidationError(["tag_ids 非法"])

        use_case = self.get_use_case()
        try:
            photo = use_case.finalize_upload(album_id, object_key, title, tag_ids)
        except ValidationError as exc:
            raise DRFValidationError(exc.messages)
        except StorageBackendNotConfigured as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(PhotoSerializer(photo).data, status=201)

    # ---------- Multipart ----------

    @action(methods=['post'], detail=False, url_path='multipart_initiate')
    def multipart_initiate(self, request):
        """
        初始化分片上传
        body: {album_id, filename, content_type, size}
        """
        album_id = int(request.data.get("album_id", 0))
        filename = request.data.get("filename") or "image.jpg"
        content_type = request.data.get("content_type") or "image/jpeg"
        size = int(request.data.get("size", 0))
        use_case = self.get_use_case()
        try:
            envelope = use_case.initiate_multipart(album_id, filename, content_type, size)
        except StorageBackendNotConfigured as exc:
            return Response({"detail": str(exc)}, status=400)
        except ValidationError as exc:
            raise DRFValidationError(exc.messages)

        return Response(envelope.to_dict())

    @action(methods=['post'], detail=False, url_path='multipart_sign_part')
    def multipart_sign_part(self, request):
        """
        对单个分片签名
        body: {object_key, upload_id, part_number(int)}
        """
        object_key = request.data.get("object_key")
        upload_id = request.data.get("upload_id")
        part_number = int(request.data.get("part_number", 0))

        use_case = self.get_use_case()
        try:
            envelope = use_case.sign_multipart_part(object_key, upload_id, part_number)
        except StorageBackendNotConfigured as exc:
            return Response({"detail": str(exc)}, status=400)
        except ValidationError as exc:
            raise DRFValidationError(exc.messages)

        return Response(envelope.to_dict())

    @action(methods=['post'], detail=False, url_path='multipart_complete')
    def multipart_complete(self, request):
        """
        合并所有分片
        body: {object_key, upload_id, parts: [{ETag, PartNumber}]}
        """
        object_key = request.data.get("object_key")
        upload_id = request.data.get("upload_id")
        try:
            tag_ids = self._parse_tag_ids(request.data.get("tag_ids", []))
        except ValueError:
            raise DRFValidationError(["tag_ids 非法"])
        parts = request.data.get("parts", [])
        title = request.data.get("title", "")
        album_id = int(request.data.get("album_id", 0))
        use_case = self.get_use_case()
        try:
            envelope = use_case.complete_multipart(
                album_id, object_key, upload_id, parts, title, tag_ids
            )
        except StorageBackendNotConfigured as exc:
            return Response({"detail": str(exc)}, status=400)
        except ValidationError as exc:
            raise DRFValidationError(exc.messages)

        return Response(envelope.to_dict())


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
