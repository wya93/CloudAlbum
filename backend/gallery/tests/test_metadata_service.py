from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone

from ..models import Album, Photo
from ..services.metadata import extract_exif_metadata


class ExtractExifMetadataTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="tester", password="pass")
        self.album = Album.objects.create(name="Test", description="", owner=self.user)

    def _build_photo(self) -> Photo:
        photo = Photo(owner=self.user, album=self.album)
        photo.image = SimpleUploadedFile("img.jpg", b"file", content_type="image/jpeg")
        return photo

    def test_taken_at_uses_current_timezone(self):
        photo = self._build_photo()
        exif_payload = {36867: "2023:10:01 12:34:56"}  # DateTimeOriginal
        for zone in ["UTC", "Asia/Shanghai"]:
            with self.subTest(zone=zone), timezone.override(zone):
                with patch("gallery.services.metadata.Image.open") as mock_open:
                    image_mock = MagicMock()
                    image_mock.__enter__.return_value = image_mock
                    image_mock.__exit__ = MagicMock()
                    image_mock.size = (400, 300)
                    image_mock._getexif.return_value = exif_payload
                    mock_open.return_value = image_mock

                    updates = extract_exif_metadata(photo)

                    taken_at = updates["taken_at"]
                    self.assertEqual(taken_at.tzinfo, timezone.get_current_timezone())
                    self.assertEqual((updates["width"], updates["height"]), (400, 300))

    def test_invalid_gps_values_are_ignored(self):
        photo = self._build_photo()
        gps_payload = {
            1: "N",
            2: "invalid-latitude",
            3: "E",
            4: "invalid-longitude",
        }
        exif_payload = {34853: gps_payload}

        with patch("gallery.services.metadata.Image.open") as mock_open:
            image_mock = MagicMock()
            image_mock.__enter__.return_value = image_mock
            image_mock.__exit__ = MagicMock()
            image_mock.size = (200, 100)
            image_mock._getexif.return_value = exif_payload
            mock_open.return_value = image_mock

            updates = extract_exif_metadata(photo)

        self.assertNotIn("gps_lat", updates)
        self.assertNotIn("gps_lng", updates)
        self.assertEqual((updates["width"], updates["height"]), (200, 100))
