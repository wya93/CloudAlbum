"""领域层：封装业务用例，供视图、任务等调用。"""

from .albums import (
    AlbumUseCase,
    AlbumUploadContext,
    MultipartCompleteResult,
    MultipartInitiateResult,
    MultipartSignPartResult,
    PresignUploadResult,
    UploadEnvelope,
)

__all__ = [
    "AlbumUseCase",
    "AlbumUploadContext",
    "MultipartCompleteResult",
    "MultipartInitiateResult",
    "MultipartSignPartResult",
    "PresignUploadResult",
    "UploadEnvelope",
]
