"""
RAG retrieval service.
Classify query → build metadata filter → Hybrid Search (Dense+Sparse) → Redis cache.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from pymilvus import (
    AnnSearchRequest,
    Collection,
    RRFRanker,
    WeightedRanker,
)

from app.db.redis_client import get_redis
from app.services.embedder import embed_single

QUERY_LEVELS = ("match_level", "tactical_level", "player_level")
COLLECTION_MAP = {
    "match_level": "match_summaries",
    "tactical_level": "tactical_segments",
    "player_level": "player_profiles",
}
RAG_CACHE_TTL = 600


# ─────────────────────────────────────────────
# 4.1  Query Classifier (rule-based + LLM fallback)
# ─────────────────────────────────────────────

_MATCH_KEYWORDS = re.compile(
    r"\b(match|game|result|score|fixture|final|win|lose|draw|season performance|contest)\b",
    re.IGNORECASE,
)
_TACTICAL_KEYWORDS = re.compile(
    r"\b(tactic|formation|press|pressing|attack|defend|build[- ]up|possession|pass|dribble|shape|system|xg|expected goals|counter|line)\b",
    re.IGNORECASE,
)
_PLAYER_KEYWORDS = re.compile(
    r"\b(player|squad|striker|midfielder|defender|goalkeeper|forward|winger|assist|goal scorer|card)\b",
    re.IGNORECASE,
)


def classify_query(query: str) -> list[str]:
    """
    Return one or more collection targets for a query.
    Rules-first; returns multiple if query spans multiple levels.
    """
    levels: list[str] = []
    if _PLAYER_KEYWORDS.search(query):
        levels.append("player_level")
    if _TACTICAL_KEYWORDS.search(query):
        levels.append("tactical_level")
    if _MATCH_KEYWORDS.search(query):
        levels.append("match_level")
    if not levels:
        levels = ["tactical_level"]
    return levels


# ─────────────────────────────────────────────
# 4.2  Metadata Filter Builder
# ─────────────────────────────────────────────

def build_milvus_filter(
    competition_id: int | None = None,
    season_id: int | None = None,
    team_id: int | None = None,
    match_id: int | None = None,
) -> str | None:
    parts: list[str] = []
    if competition_id is not None:
        parts.append(f"competition_id == {competition_id}")
    if season_id is not None:
        parts.append(f"season_id == {season_id}")
    if team_id is not None:
        parts.append(f"team_id == {team_id}")
    if match_id is not None:
        parts.append(f"match_id == {match_id}")
    return " && ".join(parts) if parts else None


# ─────────────────────────────────────────────
# 4.3  Milvus Hybrid Search (Dense + Sparse)
# ─────────────────────────────────────────────

def _hybrid_search(
    collection_name: str,
    query: str,
    top_k: int = 5,
    milvus_filter: str | None = None,
) -> list[dict]:
    from app.db.milvus_client import connect_milvus
    from pymilvus import connections
    if not connections.has_connection("default"):
        connect_milvus()

    vectors = embed_single(query)
    dense_vec = vectors["dense_vector"]
    sparse_vec = vectors["sparse_vector"]

    collection = Collection(collection_name)
    collection.load()

    search_params_dense = {"metric_type": "COSINE", "params": {"ef": 64}}
    search_params_sparse = {"metric_type": "IP", "params": {"drop_ratio_search": 0.2}}

    dense_req = AnnSearchRequest(
        data=[dense_vec],
        anns_field="dense_vector",
        param=search_params_dense,
        limit=top_k,
        expr=milvus_filter,
    )
    sparse_req = AnnSearchRequest(
        data=[sparse_vec],
        anns_field="sparse_vector",
        param=search_params_sparse,
        limit=top_k,
        expr=milvus_filter,
    )

    results = collection.hybrid_search(
        reqs=[dense_req, sparse_req],
        rerank=RRFRanker(),
        limit=top_k,
        output_fields=["text", "match_id", "competition_id", "season_id"],
    )

    hits = []
    for hit in results[0]:
        entity = hit.fields if hasattr(hit, "fields") else hit.entity
        hits.append({
            "score": hit.score,
            "text": entity.get("text", ""),
            "match_id": entity.get("match_id"),
            "competition_id": entity.get("competition_id"),
            "season_id": entity.get("season_id"),
            "collection": collection_name,
        })
    return hits


# ─────────────────────────────────────────────
# 4.4  Redis RAG Cache
# ─────────────────────────────────────────────

def _cache_key(query: str, collection_name: str, milvus_filter: str | None, top_k: int) -> str:
    raw = f"{query}|{collection_name}|{milvus_filter}|{top_k}"
    digest = hashlib.md5(raw.encode()).hexdigest()
    return f"rag:{collection_name}:{digest}"


async def _get_cached(key: str) -> list[dict] | None:
    redis = await get_redis()
    val = await redis.get(key)
    if val:
        return json.loads(val)
    return None


async def _set_cached(key: str, results: list[dict]) -> None:
    redis = await get_redis()
    await redis.set(key, json.dumps(results, ensure_ascii=False), ex=RAG_CACHE_TTL)


# ─────────────────────────────────────────────
# 4.5  RAG Service (full pipeline)
# ─────────────────────────────────────────────

async def retrieve(
    query: str,
    top_k: int = 5,
    competition_id: int | None = None,
    season_id: int | None = None,
    team_id: int | None = None,
    match_id: int | None = None,
    force_levels: list[str] | None = None,
) -> list[dict]:
    """
    Full RAG retrieval pipeline:
      classify → filter → hybrid_search → Redis cache
    Returns merged results from all relevant collections.
    """
    levels = force_levels if force_levels else classify_query(query)
    milvus_filter = build_milvus_filter(competition_id, season_id, team_id, match_id)

    all_results: list[dict] = []
    for level in levels:
        collection_name = COLLECTION_MAP[level]
        cache_key = _cache_key(query, collection_name, milvus_filter, top_k)

        cached = await _get_cached(cache_key)
        if cached is not None:
            all_results.extend(cached)
            continue

        try:
            hits = _hybrid_search(collection_name, query, top_k, milvus_filter)
        except Exception as e:
            import logging as _logging
            _logging.getLogger(__name__).warning(
                "[RAG] hybrid_search failed for %s (filter=%s): %s",
                collection_name, milvus_filter, e
            )
            hits = []

        await _set_cached(cache_key, hits)
        all_results.extend(hits)

    all_results.sort(key=lambda x: x["score"], reverse=True)
    return all_results[:top_k * len(levels)]
