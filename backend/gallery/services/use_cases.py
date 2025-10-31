"""Domain use-case objects built on top of gallery services."""

from __future__ import annotations

"""Domain use-case objects built on top of gallery services."""

from dataclasses import asdict, dataclass, field
from datetime import timedelta
from typing import Any, Dict, Iterable, List, Sequence

from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from ..models import Album, AlbumShare, Photo
from ..utils_uploads import build_object_key, validate_upload_meta
from .storage import get_upload_storage_service
from .uploads import create_photos_from_form_upload, dispatch_post_upload_tasks


@dataclass(frozen=True)
class UploadEnvelope:
    """统一的用例返回值封装，保证视图层输出结构稳定"""

    payload: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {"data": self.payload}


@dataclass(frozen=True)
class PresignUploadResult:
    object_key: str
    url: str
    method: str = "PUT"
    headers: Dict[str, str] = field(default_factory=dict)

    def as_envelope(self) -> UploadEnvelope:
        return UploadEnvelope(payload=asdict(self))


@dataclass(frozen=True)
class MultipartInitiateResult:
    object_key: str
    upload_id: str

    def as_envelope(self) -> UploadEnvelope:
        return UploadEnvelope(payload=asdict(self))


@dataclass(frozen=True)
class MultipartSignPartResult:
    url: str
    method: str = "PUT"

    def as_envelope(self) -> UploadEnvelope:
        return UploadEnvelope(payload=asdict(self))


@dataclass(frozen=True)
class MultipartCompleteResult:
    status: str = "completed"

    def as_envelope(self) -> UploadEnvelope:
        return UploadEnvelope(payload=asdict(self))


@dataclass
class AlbumUploadContext:
    user: Any

    def require_album(self, album_id: int) -> Album:
        try:
            return Album.objects.get(id=album_id, owner=self.user)
        except Album.DoesNotExist as exc:  # pragma: no cover - defensive, validated in tests
            raise PermissionDenied("相册不存在或无权访问") from exc


class AlbumUseCase:
    """Coordinate album-level operations for the current user."""

    def __init__(self, user):
        self.context = AlbumUploadContext(user=user)

    @property
    def user(self):
        return self.context.user

    def albums(self):
        return Album.objects.filter(owner=self.user).order_by("-created_at")

    def get_album(self, album_id: int) -> Album:
        return self.context.require_album(album_id)

    def create_album(self, serializer):
        serializer.save(owner=self.user)

    def list_album_photos(self, album: Album):
        return album.photos.all().order_by("-uploaded_at")

    def create_share(self, album: Album, expires_in: int) -> AlbumShare:
        expires_at = timezone.now() + timedelta(seconds=expires_in)
        return AlbumShare.objects.create(album=album, expires_at=expires_at)

    def upload_from_form(self, album: Album, files: Iterable) -> List[Photo]:
        return create_photos_from_form_upload(self.user, album, files)

    def _resolve_tags(self, photo: Photo, tag_ids: Sequence[int]):
        if tag_ids:
            photo.tags.set(tag_ids)

    def _create_photo(self, album: Album, object_key: str, title: str, tag_ids: Sequence[int]) -> Photo:
        photo = Photo.objects.create(owner=self.user, album=album, image=object_key, title=title)
        self._resolve_tags(photo, tag_ids)
        dispatch_post_upload_tasks(photo.id)
        return photo

    def presign_upload(
        self, album_id: int, filename: str, content_type: str, size: int
    ) -> UploadEnvelope:
        album = self.context.require_album(album_id)
        try:
            validate_upload_meta(content_type, size)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        storage = get_upload_storage_service()
        object_key = build_object_key(self.user.id, album.id, filename)
        url = storage.generate_presigned_put(object_key, content_type)
        result = PresignUploadResult(
            object_key=object_key,
            url=url,
            headers={"Content-Type": content_type},
        )
        return result.as_envelope()

    def finalize_upload(self, album_id: int, object_key: str, title: str, tag_ids: Sequence[int]) -> Photo:
        if not object_key:
            raise ValidationError("object_key 非法")
        album = self.context.require_album(album_id)
        if not object_key.startswith(f"photos/{self.user.id}/{album.id}/"):
            raise ValidationError("object_key 非法")
        return self._create_photo(album, object_key, title, tag_ids)

    def initiate_multipart(
        self, album_id: int, filename: str, content_type: str, size: int
    ) -> UploadEnvelope:
        album = self.context.require_album(album_id)
        try:
            validate_upload_meta(content_type, size)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

        storage = get_upload_storage_service()
        object_key = build_object_key(self.user.id, album.id, filename)
        init = storage.initiate_multipart(object_key, content_type)
        result = MultipartInitiateResult(object_key=object_key, upload_id=init["UploadId"])
        return result.as_envelope()

    def sign_multipart_part(
        self, object_key: str, upload_id: str, part_number: int
    ) -> UploadEnvelope:
        if not object_key or f"/{self.user.id}/" not in object_key:
            raise ValidationError("object_key 非法")
        if part_number <= 0:
            raise ValidationError("part_number 非法")
        storage = get_upload_storage_service()
        url = storage.generate_presigned_part_url(object_key, upload_id, part_number)
        result = MultipartSignPartResult(url=url)
        return result.as_envelope()

    def complete_multipart(
        self,
        album_id: int,
        object_key: str,
        upload_id: str,
        parts,
        title: str,
        tag_ids: Sequence[int],
    ) -> UploadEnvelope:
        if not object_key:
            raise ValidationError("object_key 非法")
        if not upload_id:
            raise ValidationError("upload_id 非法")
        album = self.context.require_album(album_id)
        storage = get_upload_storage_service()
        storage.complete_multipart(object_key, upload_id, parts)
        self._create_photo(album, object_key, title, tag_ids)
        return MultipartCompleteResult().as_envelope()
