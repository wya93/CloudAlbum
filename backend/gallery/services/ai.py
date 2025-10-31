"""AI 服务：提供延迟加载与缓存能力。"""

from __future__ import annotations

import threading
from typing import Any, Dict, Optional, Sequence, Tuple, TYPE_CHECKING

from PIL import Image

if TYPE_CHECKING:  # pragma: no cover - 类型辅助
    import numpy as np

_NUMPY_IMPORT_ERROR: Optional[ModuleNotFoundError] = None
try:  # 精简部署环境可能缺少 numpy
    import numpy as _np  # type: ignore
except ModuleNotFoundError as exc:  # pragma: no cover - 在实际使用时抛出
    _np = None  # type: ignore
    _NUMPY_IMPORT_ERROR = exc
else:
    _NUMPY_IMPORT_ERROR = None


def _require_numpy():
    if _np is None:
        raise RuntimeError("AI dependencies are missing: numpy") from _NUMPY_IMPORT_ERROR
    return _np


_TORCH_IMPORT_ERROR: Optional[ModuleNotFoundError] = None
try:  # 未开启 AI 特性的环境可能缺少 torch/open_clip
    import torch  # type: ignore
    import open_clip  # type: ignore
except ModuleNotFoundError as exc:  # pragma: no cover - 在实际使用时抛出
    torch = None  # type: ignore
    open_clip = None  # type: ignore
    _TORCH_IMPORT_ERROR = exc
else:
    _TORCH_IMPORT_ERROR = None


def _require_clip_modules():
    if torch is None or open_clip is None:
        raise RuntimeError("AI dependencies are missing: torch/open_clip") from _TORCH_IMPORT_ERROR
    return torch, open_clip


class ClipEmbeddingService:
    """提供延迟初始化的 CLIP 图像/文本向量能力。"""

    def __init__(self, model_name: str = "ViT-B-32", pretrained: str = "openai", device: Optional[str] = None):
        self.model_name = model_name
        self.pretrained = pretrained
        if device is not None:
            self.device = device
        elif torch is not None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = "cpu"
        self._model = None
        self._preprocess = None
        self._tokenizer = None
        self._model_lock = threading.Lock()
        self._text_cache: Dict[Tuple[str, ...], Any] = {}

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        with self._model_lock:
            if self._model is not None:
                return
            torch_module, open_clip_module = _require_clip_modules()
            model, preprocess, _ = open_clip_module.create_model_and_transforms(
                self.model_name, pretrained=self.pretrained
            )
            tokenizer = open_clip_module.get_tokenizer(self.model_name)
            self._model = model.eval().to(self.device)
            self._preprocess = preprocess
            self._tokenizer = tokenizer

    def encode_image(self, image: Image.Image) -> np.ndarray:
        np = _require_numpy()
        torch_module, _ = _require_clip_modules()
        self._ensure_model()
        assert self._model is not None and self._preprocess is not None
        with torch_module.no_grad():
            tensor = self._preprocess(image).unsqueeze(0).to(self.device)
            features = self._model.encode_image(tensor)
            features /= features.norm(dim=-1, keepdim=True)
        return features.cpu().numpy()[0].astype("float32")

    def encode_texts(self, texts: Sequence[str]) -> np.ndarray:
        np = _require_numpy()
        key = tuple(texts)
        cached = self._text_cache.get(key)
        if cached is not None:
            return cached

        self._ensure_model()
        assert self._model is not None and self._tokenizer is not None
        torch_module, _ = _require_clip_modules()
        with torch_module.no_grad():
            tokens = self._tokenizer(texts)
            features = self._model.encode_text(tokens.to(self.device))
            features /= features.norm(dim=-1, keepdim=True)
        vectors = features.cpu().numpy().astype("float32")
        self._text_cache[key] = vectors
        return vectors

    @staticmethod
    def vector_to_bytes(arr: np.ndarray) -> bytes:
        np = _require_numpy()
        return np.asarray(arr, dtype="float32").tobytes()

    @staticmethod
    def bytes_to_vector(blob: bytes) -> np.ndarray:
        np = _require_numpy()
        return np.frombuffer(blob, dtype="float32")


class FaceRecognitionService:
    """封装 face_recognition，支持按需导入。"""

    def __init__(self) -> None:
        self._module = None
        self._lock = threading.Lock()

    def _ensure_module(self):
        if self._module is not None:
            return
        with self._lock:
            if self._module is None:
                import face_recognition  # type: ignore

                self._module = face_recognition

    def load_image(self, file_obj) -> np.ndarray:
        self._ensure_module()
        return self._module.load_image_file(file_obj)

    def face_locations(self, image, model: str = "hog"):
        self._ensure_module()
        return self._module.face_locations(image, model=model)

    def face_encodings(self, image, known_face_locations):
        self._ensure_module()
        return self._module.face_encodings(image, known_face_locations)


_clip_service: Optional[ClipEmbeddingService] = None
_clip_lock = threading.Lock()
_face_service: Optional[FaceRecognitionService] = None
_face_lock = threading.Lock()


def get_clip_embedding_service() -> ClipEmbeddingService:
    global _clip_service
    if _clip_service is None:
        with _clip_lock:
            if _clip_service is None:
                _clip_service = ClipEmbeddingService()
    return _clip_service


def get_face_recognition_service() -> FaceRecognitionService:
    global _face_service
    if _face_service is None:
        with _face_lock:
            if _face_service is None:
                _face_service = FaceRecognitionService()
    return _face_service
