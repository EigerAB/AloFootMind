"""Write RAG corpus vectors to Milvus collections."""
from pymilvus import Collection

from app.services.embedder import embed_texts


def _batch_insert(collection: Collection, rows: list[dict], field_names: list[str]) -> None:
    if not rows:
        return
    data = {f: [r[f] for r in rows] for f in field_names}
    collection.insert(list(data.values()))
    collection.flush()


def write_match_summaries(
    entries: list[dict],
) -> None:
    """
    entries: list of dicts with keys:
      match_id, competition_id, season_id, home_team_id, away_team_id, text
    """
    if not entries:
        return
    texts = [e["text"] for e in entries]
    vectors = embed_texts(texts)

    collection = Collection("match_summaries")
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
    texts = [e["text"] for e in entries]
    vectors = embed_texts(texts)

    collection = Collection("tactical_segments")
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
    texts = [e["text"] for e in entries]
    vectors = embed_texts(texts)

    collection = Collection("player_profiles")
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
