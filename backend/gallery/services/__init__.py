"""Gallery domain service layer.

This package contains reusable service helpers that encapsulate integrations
and orchestration logic shared across views, tasks and signal handlers.
"""

from .storage import get_upload_storage_service, StorageBackendNotConfigured
from .ai import (
    ClipEmbeddingService,
    FaceRecognitionService,
    get_clip_embedding_service,
    get_face_recognition_service,
)
from .use_cases import AlbumUseCase

__all__ = [
    "get_upload_storage_service",
    "StorageBackendNotConfigured",
    "ClipEmbeddingService",
    "FaceRecognitionService",
    "get_clip_embedding_service",
    "get_face_recognition_service",
    "AlbumUseCase",
]
