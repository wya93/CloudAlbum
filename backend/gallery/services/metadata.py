"""相册照片的元数据提取工具。"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from PIL import ExifTags, Image
from django.utils import timezone

from ..models import Photo


EXIF_DATETIME_FORMATS = [
    "%Y:%m:%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
]


def _dms_to_deg(dms, ref):
    try:
        deg = dms[0][0] / dms[0][1]
        minute = dms[1][0] / dms[1][1]
        sec = dms[2][0] / dms[2][1]
        val = deg + minute / 60 + sec / 3600
        if ref in ["S", "W"]:
            val = -val
        return val
    except Exception:
        return None


def _parse_taken_at(value: str) -> Optional[datetime]:
    if not value:
        return None
    for fmt in EXIF_DATETIME_FORMATS:
        try:
            dt = datetime.strptime(value, fmt)
            if timezone.is_naive(dt):
                return timezone.make_aware(dt, timezone=timezone.get_current_timezone())
            return dt
        except ValueError:
            continue
    return None


def extract_exif_metadata(photo: Photo) -> Dict[str, Optional[object]]:
    """返回从 EXIF 信息中解析出的字段更新。"""

    if not photo.image:
        return {}

    with Image.open(photo.image) as img:
        width, height = img.size
        exif_raw = getattr(img, "_getexif", lambda: None)() or {}

    exif_dict = {ExifTags.TAGS.get(k, k): v for (k, v) in exif_raw.items()}

    updates: Dict[str, Optional[object]] = {
        "width": width,
        "height": height,
        "camera_make": str(exif_dict.get("Make", "")).strip() or None,
        "camera_model": str(exif_dict.get("Model", "")).strip() or None,
        "focal_length": str(exif_dict.get("FocalLength", "")).strip() or None,
        "exposure_time": str(exif_dict.get("ExposureTime", "")).strip() or None,
        "f_number": str(exif_dict.get("FNumber", "")).strip() or None,
    }

    iso = exif_dict.get("ISOSpeedRatings") or exif_dict.get("PhotographicSensitivity")
    try:
        updates["iso"] = int(iso) if iso is not None else None
    except (ValueError, TypeError):
        updates["iso"] = None

    taken_at = _parse_taken_at(
        exif_dict.get("DateTimeOriginal") or exif_dict.get("DateTime") or ""
    )
    if taken_at:
        updates["taken_at"] = taken_at

    gps = exif_dict.get("GPSInfo")
    if gps:
        gps_parsed = {ExifTags.GPSTAGS.get(k, k): v for k, v in gps.items()}
        lat = gps_parsed.get("GPSLatitude")
        lat_ref = gps_parsed.get("GPSLatitudeRef")
        lng = gps_parsed.get("GPSLongitude")
        lng_ref = gps_parsed.get("GPSLongitudeRef")
        if lat and lat_ref and lng and lng_ref:
            updates["gps_lat"] = _dms_to_deg(lat, lat_ref)
            updates["gps_lng"] = _dms_to_deg(lng, lng_ref)

    # 过滤掉 None，保持 update_fields 紧凑
    return {key: value for key, value in updates.items() if value is not None}
