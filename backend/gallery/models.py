from django.db import models
from django.contrib.auth.models import User
from PIL import Image
from pathlib import Path
import secrets
from datetime import timedelta
from django.utils import timezone

class AiLabel(models.Model):
    """语义标签集合（可扩展/多语言）"""
    name = models.CharField(max_length=64, db_index=True)
    lang = models.CharField(max_length=8, default="zh")  # 标签语言

    def __str__(self): 
        return self.name

class FaceGroup(models.Model):
    """人脸分组（同一人的聚类），可被用户重命名"""
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="face_groups")
    name = models.CharField(max_length=64, blank=True, default="")  # 用户可命名
    count = models.IntegerField(default=0)  # 该组内照片计数
    created_at = models.DateTimeField(auto_now_add=True)

class Tag(models.Model):
    """照片标签"""
    name = models.CharField(max_length=50)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tags")

    def __str__(self):
        return self.name

class Album(models.Model):
    # 相册
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='album')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

def photo_upload_path(instance, filename):
    """上传路径：media/photos/<user_id>/<album_id>/<filename>"""
    return f"photos/{instance.owner.id}/{instance.album.id}/{filename}"

class Photo(models.Model):
    class Meta:
        indexes = [
            models.Index(fields=["owner", "album", "uploaded_at"]),
            models.Index(fields=["taken_at"]),
        ]

    # 照片信息
    title = models.CharField(max_length=100, blank=True)
    image = models.ImageField(upload_to=photo_upload_path)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='photos')
    album = models.ForeignKey(Album, on_delete=models.CASCADE, related_name='photos')
    thumbnail = models.ImageField(upload_to=photo_upload_path, blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    tags = models.ManyToManyField(Tag, blank=True, related_name="photos")

    # EXIF / 元数据
    taken_at = models.DateTimeField(null=True, blank=True)
    camera_make = models.CharField(max_length=64, blank=True)
    camera_model = models.CharField(max_length=64, blank=True)
    focal_length = models.CharField(max_length=32, blank=True)
    exposure_time = models.CharField(max_length=32, blank=True)
    f_number = models.CharField(max_length=16, blank=True)
    iso = models.IntegerField(null=True, blank=True)
    gps_lat = models.FloatField(null=True, blank=True)
    gps_lng = models.FloatField(null=True, blank=True)
    width = models.IntegerField(null=True, blank=True)
    height = models.IntegerField(null=True, blank=True)

    # AI相关字段
    clip_vector = models.BinaryField(null=True, blank=True)  # 存 float32 向量的 bytes
    face_group_ids = models.JSONField(default=list, blank=True)  # 该照片包含的人脸组 id 列表
    ai_label_ids = models.ManyToManyField(AiLabel, blank=True, related_name="photos")

    # 标注状态
    ai_done = models.BooleanField(default=False)         # CLIP/标签是否完成
    face_done = models.BooleanField(default=False)       # 人脸是否完成
    vector_done = models.BooleanField(default=False)     # 向量是否完成

    def save(self, *args, **kwargs):
        # 自动生成缩略图
        super().save(*args, **kwargs)

        if self.image and not self.thumbnail:
            from io import BytesIO
            from django.core.files.base import ContentFile

            img = Image.open(self.image)
            img.thumbnail((300, 300))

            buffer = BytesIO()
            img.save(buffer, format="JPEG")

            thumb_name = Path(self.image.name).stem + "_thumb.jpg"
            self.thumbnail.save(thumb_name, ContentFile(buffer.getvalue()), save=False)
            super().save(update_fields=["thumbnail"])

    def __str__(self):
        return self.title or Path(self.image.name).name

class AlbumShare(models.Model):
    album = models.ForeignKey(Album, on_delete=models.CASCADE, related_name="shares")
    token = models.CharField(max_length=100, unique=True, default=secrets.token_urlsafe)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def is_valid(self):
        return timezone.now() < self.expires_at

