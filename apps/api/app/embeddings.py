"""本地 sentence-transformer embedding（M3）。

模型选型：
- 默认 `paraphrase-multilingual-MiniLM-L12-v2`：384 维，~120 MB，中英双语
- 首次加载会从 HuggingFace 下载，之后本地 cache
- 所有 embedding 在本进程内做（无外部 API）

API：
    embedder = get_embedder()
    vec = embedder.encode("上周销量")  # → np.ndarray(384,)
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.environ.get(
    "SIDEKICK_EMBED_MODEL", "paraphrase-multilingual-MiniLM-L12-v2"
)


class _Embedder:
    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self.model_name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]

            logger.info("加载 sentence-transformer：%s（首次会下载）", self.model_name)
            self._model = SentenceTransformer(self.model_name)
            logger.info("模型就绪")
        return self._model

    def encode(self, text: str) -> np.ndarray:
        m = self._load()
        vec = m.encode(text, normalize_embeddings=True)  # 归一化便于 cos sim = 内积
        return np.asarray(vec, dtype=np.float32)

    def encode_batch(self, texts: list[str]) -> np.ndarray:
        m = self._load()
        vecs = m.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(vecs, dtype=np.float32)

    @property
    def dim(self) -> int:
        # MiniLM-L12 是 384，bge-small-zh 是 512；首次 encode 后才能定
        if self._model is None:
            return 384
        return int(self._model.get_sentence_embedding_dimension())


@lru_cache(maxsize=1)
def get_embedder() -> _Embedder:
    return _Embedder()


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """已归一化向量的余弦相似度 = 内积。"""
    if a.shape != b.shape:
        return 0.0
    return float(np.dot(a, b))
