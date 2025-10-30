import re
import uuid
import mimetypes
from datetime import datetime

SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")

ALLOWED_CONTENT_TYPES = {
    "image/jpeg", "image/png", "image/webp", "image/gif", "image/heic", "image/heif"
}
MAX_SIZE_MB = 50

def sanitize_filename(filename: str) -> str:
    filename = filename.strip().replace(" ", "_")
    filename = SAFE_NAME_RE.sub("_", filename)
    return filename or f"file_{uuid.uuid4().hex}"

def build_object_key(user_id: int, album_id: int, filename: str) -> str:
    dt = datetime.utcnow().strftime("%Y%m%d")
    return f"photos/{user_id}/{album_id}/{dt}/{uuid.uuid4().hex}_{sanitize_filename(filename)}"

def validate_upload_meta(content_type: str, size: int):
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ValueError("不支持的文件类型")
    if size > MAX_SIZE_MB * 1024 * 1024:
        raise ValueError(f"文件过大，最大{MAX_SIZE_MB}MB")
    # 额外：可根据 content_type 限制扩展名
