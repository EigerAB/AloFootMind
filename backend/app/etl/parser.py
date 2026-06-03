"""StatsBomb Open Data JSON parser."""
import json
from pathlib import Path
from typing import Any, Generator

from app.core.config import settings


def _data_dir() -> Path:
    return Path(settings.STATSBOMB_DATA_PATH)


def load_competitions(competition_id: int | None = None) -> list[dict]:
    path = _data_dir() / "competitions.json"
    with open(path, encoding="utf-8") as f:
        competitions = json.load(f)
    if competition_id is not None:
        competitions = [c for c in competitions if c["competition_id"] == competition_id]
    return competitions


def load_matches(competition_id: int, season_id: int) -> list[dict]:
    path = _data_dir() / "matches" / str(competition_id) / f"{season_id}.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_events(match_id: int) -> list[dict]:
    path = _data_dir() / "events" / f"{match_id}.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_lineups(match_id: int) -> list[dict]:
    path = _data_dir() / "lineups" / f"{match_id}.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def iter_all_matches(competition_id: int | None = None, season_id: int | None = None) -> Generator[tuple[dict, dict], None, None]:
    """Yields (competition_entry, match) for all matches under the given competition_id and optionally season_id."""
    competitions = load_competitions(competition_id)
    seen_combos: set[tuple[int, int]] = set()
    for comp_entry in competitions:
        cid = comp_entry["competition_id"]
        sid = comp_entry["season_id"]
        if season_id is not None and sid != season_id:
            continue
        if (cid, sid) in seen_combos:
            continue
        seen_combos.add((cid, sid))
        for match in load_matches(cid, sid):
            yield comp_entry, match


def extract_formations(
    events: list[dict],
    home_team_id: int,
    away_team_id: int,
) -> tuple[int | None, int | None]:
    """Extract starting formations from StatsBomb events.

    Formation data lives in "Starting XI" (type.id=35) and
    "Tactical Shift" (type.id=36) events, NOT in the matches JSON.
    Returns (home_formation, away_formation) as integer codes (e.g. 4231).
    """
    home_formation: int | None = None
    away_formation: int | None = None
    for ev in events:
        ev_type_name = (ev.get("type") or {}).get("name", "")
        if ev_type_name not in ("Starting XI", "Tactical Shift", "首发阵容", "战术调整"):
            continue
        formation = (ev.get("tactics") or {}).get("formation")
        if formation is None:
            continue
        team_id = (ev.get("team") or {}).get("id")
        if team_id == home_team_id and home_formation is None:
            home_formation = formation
        elif team_id == away_team_id and away_formation is None:
            away_formation = formation
        if home_formation is not None and away_formation is not None:
            break
    return home_formation, away_formation


def parse_match_record(comp_entry: dict, match: dict, events: list[dict] | None = None) -> dict:
    """Flatten a StatsBomb match JSON into a clean dict.

    Pass *events* (the match event list) to populate home_formation /
    away_formation — StatsBomb stores formation only in events, not in
    the match JSON.
    """
    home = match.get("home_team", {})
    away = match.get("away_team", {})

    def _manager_name(managers: list) -> str | None:
        if managers:
            m = managers[0]
            return m.get("name")
        return None

    home_team_id = home.get("home_team_id")
    away_team_id = away.get("away_team_id")

    if events:
        home_formation, away_formation = extract_formations(events, home_team_id, away_team_id)
    else:
        home_formation, away_formation = None, None

    return {
        "match_id": match["match_id"],
        "match_date": match.get("match_date", ""),
        "kick_off": match.get("kick_off"),
        "competition_id": comp_entry["competition_id"],
        "season_id": comp_entry["season_id"],
        "home_team_id": home_team_id,
        "home_team_name": home.get("home_team_name", ""),
        "away_team_id": away_team_id,
        "away_team_name": away.get("away_team_name", ""),
        "home_score": match.get("home_score", 0),
        "away_score": match.get("away_score", 0),
        "match_week": match.get("match_week"),
        "stadium_name": (match.get("stadium") or {}).get("name"),
        "home_formation": home_formation,
        "away_formation": away_formation,
        "home_manager": _manager_name(match.get("home_team", {}).get("managers", [])),
        "away_manager": _manager_name(match.get("away_team", {}).get("managers", [])),
        "competition_name": comp_entry.get("competition_name", ""),
        "season_name": comp_entry.get("season_name", ""),
        "country_name": comp_entry.get("country_name", ""),
    }


def parse_lineup_records(match_id: int, lineups_data: list[dict]) -> list[dict]:
    """Extract player lineup entries from StatsBomb lineups JSON."""
    records = []
    for team_lineup in lineups_data:
        team_id = team_lineup["team_id"]
        for player in team_lineup.get("lineup", []):
            pos_list = player.get("positions", [])
            position_name = pos_list[0]["position"] if pos_list else None
            records.append({
                "match_id": match_id,
                "team_id": team_id,
                "player_id": player["player_id"],
                "player_name": player["player_name"],
                "jersey_number": player.get("jersey_number"),
                "position_name": position_name,
                "country_name": (player.get("country") or {}).get("name"),
            })
    return records


def parse_events_aggregated(match_id: int, home_team_id: int, away_team_id: int, events: list[dict]) -> dict:
    """Aggregate key statistics from a match event stream."""
    home_shots = away_shots = 0
    home_shots_on_target = away_shots_on_target = 0
    home_passes = away_passes = 0
    home_fouls = away_fouls = 0
    key_events: list[dict] = []
    possessions: set[int] = set()

    for ev in events:
        ev_type = (ev.get("type") or {}).get("name", "")
        team_id = (ev.get("team") or {}).get("id", 0)
        possession = ev.get("possession", 0)
        possessions.add(possession)

        is_home = team_id == home_team_id

        if ev_type in ("Shot", "射门"):
            outcome = (ev.get("shot") or {}).get("outcome", {}).get("name", "")
            if is_home:
                home_shots += 1
                if outcome in ("Goal", "Saved", "Saved To Post"):
                    home_shots_on_target += 1
            else:
                away_shots += 1
                if outcome in ("Goal", "Saved", "Saved To Post"):
                    away_shots_on_target += 1

            if outcome == "Goal":
                key_events.append({
                    "type": "Goal",
                    "team_id": team_id,
                    "player_id": (ev.get("player") or {}).get("id"),
                    "player": (ev.get("player") or {}).get("name", ""),
                    "minute": ev.get("minute", 0),
                    "period": ev.get("period", 1),
                })

        elif ev_type in ("Pass", "传球"):
            outcome = (ev.get("pass") or {}).get("outcome", {}).get("name", "")
            if is_home:
                home_passes += 1
            else:
                away_passes += 1

        elif ev_type in ("Foul Committed", "犯规"):
            if is_home:
                home_fouls += 1
            else:
                away_fouls += 1

        elif ev_type in ("Yellow Card", "Red Card", "Second Yellow", "Bad Behaviour", "不良行为"):
            if ev_type in ("Bad Behaviour", "不良行为"):
                card_name = (ev.get("bad_behaviour") or {}).get("card", {}).get("name", "")
            else:
                card_name = ev_type
            if card_name in ("Yellow Card", "Red Card", "Second Yellow"):
                key_events.append({
                    "type": card_name,
                    "team_id": team_id,
                    "player_id": (ev.get("player") or {}).get("id"),
                    "player": (ev.get("player") or {}).get("name", ""),
                    "minute": ev.get("minute", 0),
                    "period": ev.get("period", 1),
                })

    import json as _json
    return {
        "match_id": match_id,
        "total_events": len(events),
        "total_possessions": len(possessions),
        "home_shots": home_shots,
        "away_shots": away_shots,
        "home_shots_on_target": home_shots_on_target,
        "away_shots_on_target": away_shots_on_target,
        "home_passes": home_passes,
        "away_passes": away_passes,
        "home_fouls": home_fouls,
        "away_fouls": away_fouls,
        "key_events_json": _json.dumps(key_events, ensure_ascii=False),
    }


def slice_possession_sequences(events: list[dict]) -> list[list[dict]]:
    """Group events by possession sequence index."""
    from collections import defaultdict
    seqs: dict[int, list[dict]] = defaultdict(list)
    for ev in events:
        p = ev.get("possession", 0)
        seqs[p].append(ev)
    return [seqs[k] for k in sorted(seqs.keys())]
