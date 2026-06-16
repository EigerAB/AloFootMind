"""
Three-layer RAG corpus text generation.
  Layer 1 (match_summaries)   — LLM (DeepSeek)
  Layer 2 (tactical_segments) — Rule templates
  Layer 3 (player_profiles)   — LLM (DeepSeek)
"""
import json
from collections import defaultdict
from typing import Any

from app.core.config import settings
from app.services.llm_client import get_deepseek_client


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
            "进球": "resulting in a GOAL",
            "Saved": "shot saved by goalkeeper",
            "扑救": "shot saved by goalkeeper",
            "Saved To Post": "shot saved onto the post",
            "扑救到柱": "shot saved onto the post",
            "Off T": "shot off target",
            "偏离目标": "shot off target",
            "Blocked": "shot blocked",
            "被阻挡": "shot blocked",
            "Wayward": "shot wide",
            "Post": "struck the post",
            "门柱": "struck the post",
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
            "Foul Won": "won a foul",
            "被犯规": "won a foul",
            "Clearance": "cleared by defense",
            "解围": "cleared by defense",
            "Interception": "ended with an interception",
            "拦截": "ended with an interception",
            "Dribbled Past": "dribbled past by opponent",
            "被过人": "dribbled past by opponent",
            "Dispossessed": "possession dispossessed",
            "控球失误": "possession dispossessed",
            "Tackle": "dispossessed by tackle",
            "被断球": "dispossessed by tackle",
            "Miscontrol": "possession lost via miscontrol",
            "失控": "possession lost via miscontrol",
            "Error": "ended with an error",
            "错误": "ended with an error",
            "Goal Keeper": "dealt with by goalkeeper",
            "门将": "dealt with by goalkeeper",
            "Block": "blocked",
            "封堵": "blocked",
            "Offside": "flagged offside",
            "越位": "flagged offside",
            "Duel": "ended with a duel",
            "对抗": "ended with a duel",
            "Substitution": "ended with a substitution",
            "换人": "ended with a substitution",
            "Injury Stoppage": "interrupted by injury",
            "伤停": "interrupted by injury",
            "Tactical Shift": "ended with tactical shift",
            "战术调整": "ended with tactical shift",
            "Referee Drop": "ended with referee drop ball",
            "裁判坠球": "ended with referee drop ball",
            "Half Start": "half started",
            "半场开始": "half started",
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

    client = get_deepseek_client()
    response = await client.chat.completions.create(
        model=settings.DEEPSEEK_MODEL,
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

    client = get_deepseek_client()
    response = await client.chat.completions.create(
        model=settings.DEEPSEEK_MODEL,
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
                if outcome in ("Goal", "进球"):
                    goals += 1
                if outcome in ("Goal", "Saved", "Saved To Post", "进球", "扑救", "扑救到柱"):
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


# ─────────────────────────────────────────────
# Layer 4 — Team season tactical profile
# ─────────────────────────────────────────────

def aggregate_team_tactical_stats(
    team_id: int,
    matches_events: list[tuple[int, list[dict]]],
) -> dict:
    """Aggregate possession-level tactical stats for a team across a season."""
    from collections import defaultdict

    zone_counts: dict[str, int] = defaultdict(int)
    zone_passes: dict[str, list[int]] = defaultdict(list)
    zone_pressure_passes: dict[str, list[int]] = defaultdict(list)
    counters = {"total": 0, "shots": 0, "carries": 0, "passes_prog": 0, "long": 0}

    _ZONE_RANGES = [((0, 40), "后场"), ((40, 80), "中场"), ((80, 120), "前场")]

    def _zone(location):
        if not location or len(location) < 1:
            return None
        x = location[0]
        for (x0, x1), label in _ZONE_RANGES:
            if x0 <= x < x1:
                return label
        return "前场"

    for _match_id, events in matches_events:
        current_seq: list[dict] = []
        current_team_id: int | None = None

        for ev in events:
            ev_team_id = (ev.get("team") or {}).get("id")
            if ev_team_id != current_team_id:
                if current_team_id == team_id and current_seq:
                    _process_seq(current_seq, zone_counts, zone_passes,
                                 zone_pressure_passes, counters, _zone)
                current_seq = [ev]
                current_team_id = ev_team_id
            else:
                current_seq.append(ev)
        if current_team_id == team_id and current_seq:
            _process_seq(current_seq, zone_counts, zone_passes,
                         zone_pressure_passes, counters, _zone)

    total = counters["total"]
    zone_avg_passes = {
        z: (sum(v) / len(v)) if v else 0.0
        for z, v in zone_passes.items()
    }
    zone_pressure_ratio = {
        z: (sum(zone_pressure_passes.get(z, [])) / sum(zone_passes[z]) * 100)
        if sum(zone_passes[z]) > 0 else 0.0
        for z in zone_passes
    }

    shot_rate = (counters["shots"] / total * 100) if total > 0 else 0.0
    long_poss_rate = (counters["long"] / total * 100) if total > 0 else 0.0
    total_prog = counters["carries"] + counters["passes_prog"]
    carry_ratio = (counters["carries"] / total_prog * 100) if total_prog > 0 else 0.0
    pass_ratio = (counters["passes_prog"] / total_prog * 100) if total_prog > 0 else 0.0

    return {
        "total_possessions": total,
        "zone_counts": dict(zone_counts),
        "zone_avg_passes": zone_avg_passes,
        "zone_pressure_ratio": zone_pressure_ratio,
        "shot_rate": shot_rate,
        "long_possession_rate": long_poss_rate,
        "carry_progression_ratio": carry_ratio,
        "pass_progression_ratio": pass_ratio,
    }


def _process_seq(seq, zone_counts, zone_passes, zone_pressure_passes, counters, _zone_fn):
    """Extract stats from one possession sequence; mutates all container args."""
    if not seq:
        return

    counters["total"] += 1
    event_types = [(ev.get("type") or {}).get("name", "") for ev in seq]
    first_loc = next((ev.get("location") for ev in seq if ev.get("location")), None)
    start_zone = _zone_fn(first_loc)
    last_loc = next((ev.get("location") for ev in reversed(seq) if ev.get("location")), None)
    end_zone = _zone_fn(last_loc)

    if start_zone:
        zone_counts[start_zone] += 1

    pass_count = sum(1 for t in event_types if t in ("Pass", "传球"))
    pressure_count = sum(1 for ev in seq if ev.get("under_pressure"))

    if start_zone:
        zone_passes[start_zone].append(pass_count)
        zone_pressure_passes[start_zone].append(pressure_count)

    if any(t in event_types for t in ("Shot", "射门")):
        counters["shots"] += 1

    if pass_count >= 10:
        counters["long"] += 1

    has_carry = any(t in event_types for t in ("Carry", "带球"))
    has_dribble = any(t in event_types for t in ("Dribble", "盘带"))
    if start_zone and end_zone and start_zone != end_zone:
        if has_carry or has_dribble:
            counters["carries"] += 1
        else:
            counters["passes_prog"] += 1


async def generate_team_tactical_profile(
    team_name: str,
    team_id: int,
    competition_name: str,
    season_name: str,
    stats: dict,
) -> str:
    """Call DeepSeek to generate a Chinese team tactical profile from aggregated stats."""
    total = stats.get("total_possessions", 0)
    zone_counts = stats.get("zone_counts", {})
    zone_avg = stats.get("zone_avg_passes", {})
    zone_pressure = stats.get("zone_pressure_ratio", {})
    shot_rate = stats.get("shot_rate", 0.0)
    long_rate = stats.get("long_possession_rate", 0.0)
    carry_ratio = stats.get("carry_progression_ratio", 0.0)
    pass_ratio = stats.get("pass_progression_ratio", 0.0)

    def fmt_zone(z):
        cnt = zone_counts.get(z, 0)
        pct = (cnt / total * 100) if total > 0 else 0.0
        avg_p = zone_avg.get(z, 0.0)
        pressure_r = zone_pressure.get(z, 0.0)
        return f"{z}（{pct:.1f}%持球，平均{avg_p:.1f}次传球，承压传球率{pressure_r:.1f}%）"

    zone_lines = "\n".join(fmt_zone(z) for z in ["后场", "中场", "前场"] if z in zone_counts)

    prompt = f"""你是一位专业的足球战术分析师。请根据以下赛季统计数据，用中文撰写一篇关于{team_name}的战术风格分析摘要（400-600字）。

球队：{team_name}
赛季：{competition_name} {season_name}
总持球次数：{total}

各区域持球分布：
{zone_lines}

其他统计：
- 持球转化射门率：{shot_rate:.1f}%
- 长时间控球（≥10次传球）占比：{long_rate:.1f}%
- 进攻推进方式：带球推进占{carry_ratio:.1f}%，传球推进占{pass_ratio:.1f}%

请分析：
1. 该队的控球区域偏好（重心在哪个区域，为什么）
2. 传球风格（短传渗透还是长传直塞，传球节奏）
3. 承压能力（在压力下的传球表现）
4. 进攻套路（持球推进 vs 快速反击的偏向）
5. 整体战术标签（如：控球型、反击型、高位逼抢、低位防守等）

要求：用自然流畅的中文分析语言，不要列表，写成段落形式，包含具体数据引用。"""

    client = get_deepseek_client()
    response = await client.chat.completions.create(
        model=settings.DEEPSEEK_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=900,
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()
