"""
Three-layer RAG corpus text generation.
  Layer 1 (match_summaries)   — LLM (DeepSeek)
  Layer 2 (tactical_segments) — Rule templates
  Layer 3 (player_profiles)   — LLM (DeepSeek)
"""
import json
from collections import defaultdict
from typing import Any

from openai import AsyncOpenAI

from app.core.config import settings

_deepseek_client: AsyncOpenAI | None = None


def _get_deepseek() -> AsyncOpenAI:
    global _deepseek_client
    if _deepseek_client is None:
        _deepseek_client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com/v1",
        )
    return _deepseek_client


# ─────────────────────────────────────────────
# Layer 2 — Rule-template tactical segments
# ─────────────────────────────────────────────

_ZONE_MAP = {
    (0, 40): "defensive third",
    (40, 80): "middle third",
    (80, 120): "attacking third",
}


def _location_zone(location: list | None) -> str:
    if not location or len(location) < 1:
        return "unknown zone"
    x = location[0]
    for (x0, x1), label in _ZONE_MAP.items():
        if x0 <= x < x1:
            return label
    return "attacking third"


def generate_tactical_segment_text(
    possession_events: list[dict],
    home_team_name: str,
    away_team_name: str,
    home_team_id: int,
) -> str | None:
    """Generate a natural-language description of a single possession sequence."""
    if not possession_events:
        return None

    team_id = (possession_events[0].get("team") or {}).get("id", 0)
    team_name = home_team_name if team_id == home_team_id else away_team_name
    opponent_name = away_team_name if team_id == home_team_id else home_team_name

    event_types = [(ev.get("type") or {}).get("name", "") for ev in possession_events]
    period = possession_events[0].get("period", 1)
    minute_start = possession_events[0].get("minute", 0)
    minute_end = possession_events[-1].get("minute", minute_start)

    has_shot = any(t in event_types for t in ("Shot", "射门"))
    has_dribble = any(t in event_types for t in ("Dribble", "盘带"))
    has_carry = any(t in event_types for t in ("Carry", "带球"))
    under_pressure_count = sum(1 for ev in possession_events if ev.get("under_pressure"))

    first_loc = next(
        (ev.get("location") for ev in possession_events if ev.get("location")), None
    )
    last_loc = next(
        (ev.get("location") for ev in reversed(possession_events) if ev.get("location")), None
    )
    start_zone = _location_zone(first_loc)
    end_zone = _location_zone(last_loc)

    pass_count = sum(1 for t in event_types if t in ("Pass", "传球"))
    shot_outcome = None
    if has_shot:
        for ev in possession_events:
            if (ev.get("type") or {}).get("name") in ("Shot", "射门"):
                shot_outcome = (ev.get("shot") or {}).get("outcome", {}).get("name", "")
                break

    period_label = f"{'1st' if period == 1 else '2nd' if period == 2 else f'{period}th'} half"
    time_label = f"{minute_start}'" if minute_start == minute_end else f"{minute_start}'-{minute_end}'"

    parts = [f"[{time_label} {period_label}] {team_name} possession in the {start_zone}."]

    if pass_count > 0:
        pressure_note = f" ({under_pressure_count} passes under pressure)" if under_pressure_count > 0 else ""
        parts.append(f"Built up with {pass_count} passes{pressure_note}.")

    if has_dribble or has_carry:
        parts.append(f"Progressed to the {end_zone} via {'dribbling' if has_dribble else 'carries'}.")
    elif start_zone != end_zone:
        parts.append(f"Advanced to the {end_zone}.")

    if has_shot:
        outcome_desc = {
            "Goal": "resulting in a GOAL",
            "Saved": "shot saved by goalkeeper",
            "Off T": "shot off target",
            "Blocked": "shot blocked",
            "Wayward": "shot wide",
            "Post": "struck the post",
        }.get(shot_outcome or "", f"shot outcome: {shot_outcome}")
        parts.append(f"Ended with a shot attempt, {outcome_desc}.")
    else:
        last_type = event_types[-1] if event_types else "unknown"
        _CN_EN_MAP = {
            "Ball Receipt*": "possession lost",
            "接球*": "possession lost",
            "Pressure": "disrupted by opponent pressure",
            "施压": "disrupted by opponent pressure",
            "Foul Committed": "ended with a foul",
            "犯规": "ended with a foul",
            "Clearance": "cleared by defense",
            "解围": "cleared by defense",
        }
        last_label = _CN_EN_MAP.get(last_type, f"ended with {last_type.lower()}")
        parts.append(f"Possession {last_label}.")

    return " ".join(parts)


# ─────────────────────────────────────────────
# Layer 1 — LLM match summary
# ─────────────────────────────────────────────

async def generate_match_summary(match_record: dict, key_events: list[dict]) -> str:
    """Call DeepSeek to generate a 300-500 word match summary."""
    home = match_record["home_team_name"]
    away = match_record["away_team_name"]
    score = f"{match_record['home_score']}-{match_record['away_score']}"
    date = match_record["match_date"]
    competition = match_record.get("competition_name", "")
    season = match_record.get("season_name", "")

    goals = [e for e in key_events if e["type"] == "Goal"]
    cards = [e for e in key_events if e["type"] in ("Yellow Card", "Red Card", "Second Yellow")]

    goals_text = "\n".join(
        f"  - {g['minute']}' {g['player']} ({g['type']})" for g in goals
    ) or "  No goals recorded."
    cards_text = "\n".join(
        f"  - {c['minute']}' {c['player']} ({c['type']})" for c in cards
    ) or "  No cards recorded."

    prompt = f"""You are a football match analyst. Write a concise 300-500 word match summary in English.

Match: {home} vs {away}
Score: {score}
Date: {date}
Competition: {competition} ({season})

Goals:
{goals_text}

Disciplinary events:
{cards_text}

Write a natural language summary covering: match overview, key moments, tactical observations. 
Do NOT fabricate statistics not provided. Be factual and analytical."""

    client = _get_deepseek()
    response = await client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=800,
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


# ─────────────────────────────────────────────
# Layer 3 — LLM player season profile
# ─────────────────────────────────────────────

async def generate_player_profile(
    player_name: str,
    player_id: int,
    team_name: str,
    competition_name: str,
    season_name: str,
    stats: dict,
) -> str:
    """Call DeepSeek to generate a player season profile text."""
    prompt = f"""You are a football scout analyst. Write a concise player season profile (200-350 words) in English.

Player: {player_name}
Team: {team_name}
Competition: {competition_name} ({season_name})

Season statistics (derived from match events):
- Appearances: {stats.get('appearances', 0)}
- Goals: {stats.get('goals', 0)}
- Assists: {stats.get('assists', 0)}
- Total passes: {stats.get('total_passes', 0)}
- Pass completion rate: {stats.get('pass_completion_pct', 0):.1f}%
- Shots: {stats.get('shots', 0)} (on target: {stats.get('shots_on_target', 0)})
- Dribbles attempted: {stats.get('dribbles_attempted', 0)}
- Fouls drawn: {stats.get('fouls_drawn', 0)}
- Primary positions: {stats.get('positions', 'Unknown')}

Write a profile describing the player's style, strengths, and season performance. 
Be analytical. Do NOT fabricate information beyond what is provided."""

    client = _get_deepseek()
    response = await client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=600,
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


def aggregate_player_season_stats(
    player_id: int, matches_events: list[tuple[int, list[dict]]]
) -> dict:
    """Aggregate per-player statistics across multiple match event lists."""
    appearances = 0
    goals = 0
    assists = 0
    total_passes = 0
    completed_passes = 0
    shots = 0
    shots_on_target = 0
    dribbles_attempted = 0
    fouls_drawn = 0
    positions: set[str] = set()

    for match_id, events in matches_events:
        player_in_match = False
        for ev in events:
            player = ev.get("player") or {}
            if player.get("id") != player_id:
                continue
            player_in_match = True

            ev_type = (ev.get("type") or {}).get("name", "")
            pos_name = (ev.get("position") or {}).get("name")
            if pos_name:
                positions.add(pos_name)

            if ev_type in ("Shot", "射门"):
                shots += 1
                outcome = (ev.get("shot") or {}).get("outcome", {}).get("name", "")
                if outcome == "Goal":
                    goals += 1
                if outcome in ("Goal", "Saved", "Saved To Post"):
                    shots_on_target += 1

            elif ev_type in ("Pass", "传球"):
                total_passes += 1
                outcome = (ev.get("pass") or {}).get("outcome", {}).get("name")
                if outcome is None:
                    completed_passes += 1
                goal_assist = (ev.get("pass") or {}).get("goal_assist")
                if goal_assist:
                    assists += 1

            elif ev_type in ("Dribble", "盘带"):
                dribbles_attempted += 1

            elif ev_type in ("Foul Won", "被犯规"):
                fouls_drawn += 1

        if player_in_match:
            appearances += 1

    pass_completion_pct = (
        (completed_passes / total_passes * 100) if total_passes > 0 else 0.0
    )

    return {
        "player_id": player_id,
        "appearances": appearances,
        "goals": goals,
        "assists": assists,
        "total_passes": total_passes,
        "pass_completion_pct": pass_completion_pct,
        "shots": shots,
        "shots_on_target": shots_on_target,
        "dribbles_attempted": dribbles_attempted,
        "fouls_drawn": fouls_drawn,
        "positions": ", ".join(sorted(positions)) if positions else "Unknown",
    }
