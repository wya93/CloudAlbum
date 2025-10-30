from rest_framework import serializers
from .models import Album, Photo, Tag

class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ["id", "name"]

class AlbumSerializer(serializers.ModelSerializer):
    photo_count = serializers.IntegerField(source='photos.count', read_only=True)

    class Meta:
        model = Album
        fields = ['id', 'name', 'description', 'photo_count', 'created_at']

class PhotoSerializer(serializers.ModelSerializer):
    tags = TagSerializer(many=True, read_only=True)
    tag_ids = serializers.PrimaryKeyRelatedField(
        queryset=Tag.objects.all(), many=True, write_only=True, required=False
    )

    class Meta:
        model = Photo
        fields = ["id", "title", "image", "thumbnail", "uploaded_at", "tags", "tag_ids"]

    def create(self, validated_data):
        tag_ids = validated_data.pop("tag_ids", [])
        photo = Photo.objects.create(**validated_data)
        photo.tags.set(tag_ids)
        return photo