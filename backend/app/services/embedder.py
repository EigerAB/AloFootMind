"""BAAI/bge-m3 embedding service — Dense + Sparse dual vectors."""
from __future__ import annotations

from typing import Any

from app.core.config import settings

_model: Any = None


def _get_model() -> Any:
    global _model
    if _model is None:
        from FlagEmbedding import BGEM3FlagModel
        _model = BGEM3FlagModel(settings.EMBEDDING_MODEL, use_fp16=True)
    return _model


def embed_texts(texts: list[str], batch_size: int = 32) -> list[dict]:
    """
    Embed a list of texts using bge-m3.

    Returns a list of dicts, each containing:
      - dense_vector: list[float]  (length 1024)
      - sparse_vector: dict[int, float]  (token_id → weight)
    """
    model = _get_model()
    results = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        output = model.encode(
            batch,
            batch_size=batch_size,
            max_length=512,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )
        dense_vecs = output["dense_vecs"]
        lexical_weights = output["lexical_weights"]

        for j in range(len(batch)):
            results.append({
                "dense_vector": dense_vecs[j].tolist(),
                "sparse_vector": {
                    int(k): float(v)
                    for k, v in lexical_weights[j].items()
                    if float(v) > 0.0
                },
            })

    return results


def embed_single(text: str) -> dict:
    """Embed a single query string (used at search time)."""
    return embed_texts([text])[0]
