"""图像域的服务层。

该包提供可复用的服务工具，用于封装各类集成与编排逻辑，供视图、任务、信号处理器共享。
"""

from .storage import get_upload_storage_service, StorageBackendNotConfigured
from .ai import (
    ClipEmbeddingService,
    FaceRecognitionService,
    get_clip_embedding_service,
    get_face_recognition_service,
)
__all__ = [
    "get_upload_storage_service",
    "StorageBackendNotConfigured",
    "ClipEmbeddingService",
    "FaceRecognitionService",
    "get_clip_embedding_service",
    "get_face_recognition_service",
]
