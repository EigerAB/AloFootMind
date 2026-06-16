"""Write RAG corpus vectors to Milvus collections."""
from pymilvus import Collection, connections

from app.services.embedder import embed_texts


def _ensure_connected() -> None:
    if not connections.has_connection("default"):
        from app.db.milvus_client import connect_milvus
        connect_milvus()


def _batch_insert(collection: Collection, rows: list[dict], field_names: list[str]) -> None:
    if not rows:
        return
    data = {f: [r[f] for r in rows] for f in field_names}
    collection.insert(list(data.values()))
    collection.flush()


def _delete_by_expr(collection: Collection, expr: str) -> None:
    """Delete existing docs matching expr before re-inserting (idempotency)."""
    try:
        collection.delete(expr)
        collection.flush()
    except Exception:
        pass


def write_match_summaries(
    entries: list[dict],
) -> None:
    """
    entries: list of dicts with keys:
      match_id, competition_id, season_id, home_team_id, away_team_id, text
    """
    if not entries:
        return
    _ensure_connected()
    texts = [e["text"] for e in entries]
    vectors = embed_texts(texts)

    collection = Collection("match_summaries")
    # Idempotency: delete existing docs for these match_ids first
    ids = list({e["match_id"] for e in entries})
    _delete_by_expr(collection, f"match_id in {ids}")
    rows = []
    for i, entry in enumerate(entries):
        rows.append({
            "match_id": entry["match_id"],
            "competition_id": entry["competition_id"],
            "season_id": entry["season_id"],
            "home_team_id": entry["home_team_id"],
            "away_team_id": entry["away_team_id"],
            "text": entry["text"][:4090],
            "dense_vector": vectors[i]["dense_vector"],
            "sparse_vector": vectors[i]["sparse_vector"],
        })

    _batch_insert(
        collection,
        rows,
        ["match_id", "competition_id", "season_id", "home_team_id", "away_team_id",
         "text", "dense_vector", "sparse_vector"],
    )


def write_tactical_segments(
    entries: list[dict],
) -> None:
    """
    entries: list of dicts with keys:
      match_id, competition_id, season_id, team_id, possession_index, text
    """
    if not entries:
        return
    _ensure_connected()
    texts = [e["text"] for e in entries]
    vectors = embed_texts(texts)

    collection = Collection("tactical_segments")
    # Idempotency: delete existing segments for these match_ids first
    ids = list({e["match_id"] for e in entries})
    _delete_by_expr(collection, f"match_id in {ids}")
    rows = []
    for i, entry in enumerate(entries):
        rows.append({
            "match_id": entry["match_id"],
            "competition_id": entry["competition_id"],
            "season_id": entry["season_id"],
            "team_id": entry["team_id"],
            "possession_index": entry["possession_index"],
            "text": entry["text"][:2040],
            "dense_vector": vectors[i]["dense_vector"],
            "sparse_vector": vectors[i]["sparse_vector"],
        })

    _batch_insert(
        collection,
        rows,
        ["match_id", "competition_id", "season_id", "team_id", "possession_index",
         "text", "dense_vector", "sparse_vector"],
    )


def write_player_profiles(
    entries: list[dict],
) -> None:
    """
    entries: list of dicts with keys:
      player_id, competition_id, season_id, team_id, text
    """
    if not entries:
        return
    _ensure_connected()
    texts = [e["text"] for e in entries]
    vectors = embed_texts(texts)

    collection = Collection("player_profiles")
    # Idempotency: delete existing profiles for these (player_id, season_id) first
    for e in entries:
        _delete_by_expr(
            collection,
            f"player_id == {e['player_id']} && season_id == {e['season_id']}",
        )
    rows = []
    for i, entry in enumerate(entries):
        rows.append({
            "player_id": entry["player_id"],
            "competition_id": entry["competition_id"],
            "season_id": entry["season_id"],
            "team_id": entry["team_id"],
            "text": entry["text"][:4090],
            "dense_vector": vectors[i]["dense_vector"],
            "sparse_vector": vectors[i]["sparse_vector"],
        })

    _batch_insert(
        collection,
        rows,
        ["player_id", "competition_id", "season_id", "team_id",
         "text", "dense_vector", "sparse_vector"],
    )


def write_team_tactical_profiles(
    entries: list[dict],
) -> None:
    """
    entries: list of dicts with keys:
      team_id, competition_id, season_id, text
    """
    if not entries:
        return
    _ensure_connected()
    texts = [e["text"] for e in entries]
    vectors = embed_texts(texts)

    collection = Collection("team_tactical_profiles")
    # Idempotency: delete existing profiles for these (team_id, season_id) first
    for e in entries:
        _delete_by_expr(
            collection,
            f"team_id == {e['team_id']} && season_id == {e['season_id']}",
        )
    rows = []
    for i, entry in enumerate(entries):
        rows.append({
            "team_id": entry["team_id"],
            "competition_id": entry["competition_id"],
            "season_id": entry["season_id"],
            "text": entry["text"][:4090],
            "dense_vector": vectors[i]["dense_vector"],
            "sparse_vector": vectors[i]["sparse_vector"],
        })

    _batch_insert(
        collection,
        rows,
        ["team_id", "competition_id", "season_id",
         "text", "dense_vector", "sparse_vector"],
    )
