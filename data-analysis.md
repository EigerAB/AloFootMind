# new-data 数据结构说明文档

## 目录结构

```
new-data/
├── competitions.json          # 联赛和赛季信息
├── matches/                   # 比赛基本信息
│   └── {competition_id}/
│       └── {season_id}.json
├── events/                    # 比赛事件数据
│   └── {match_id}.json
├── lineups/                   # 阵容数据
│   └── {match_id}.json
└── three-sixty/               # 360度视角数据（当前为空）
```

## 数据流向

```
competitions.json
    ↓ (competition_id + season_id)
matches/{competition_id}/{season_id}.json
    ↓ (match_id)
events/{match_id}.json + lineups/{match_id}.json
```

---

## 1. competitions.json

**文件路径**: `new-data/competitions.json`  
**数据类型**: JSON 数组

### 数据结构

每个元素代表一个联赛的一个赛季，包含以下字段：

| 字段名 | 类型 | 说明 | 访问方式 |
|--------|------|------|----------|
| `competition_id` | integer | 联赛ID | `item["competition_id"]` |
| `season_id` | integer | 赛季ID | `item["season_id"]` |
| `country_name` | string | 国家名称 | `item["country_name"]` |
| `competition_name` | string | 联赛名称 | `item["competition_name"]` |
| `competition_gender` | string | 性别（男子/女子） | `item["competition_gender"]` |
| `competition_youth` | boolean | 是否青年联赛 | `item["competition_youth"]` |
| `competition_international` | boolean | 是否国际赛事 | `item["competition_international"]` |
| `season_name` | string | 赛季名称（如 2023/2024） | `item["season_name"]` |
| `match_updated` | string | 比赛数据最后更新时间 | `item["match_updated"]` |
| `match_updated_360` | string/null | 360数据最后更新时间 | `item["match_updated_360"]` |
| `match_available_360` | string/null | 360数据可用时间 | `item["match_available_360"]` |
| `match_available` | string | 比赛数据可用时间 | `item["match_available"]` |

### 使用示例

```python
import json

# 读取 competitions.json
with open('new-data/competitions.json', 'r', encoding='utf-8') as f:
    competitions = json.load(f)

# 查找特定的 competition_id + season_id
competition_id = 9
season_id = 281
for comp in competitions:
    if comp['competition_id'] == competition_id and comp['season_id'] == season_id:
        print(f"联赛: {comp['competition_name']}")
        print(f"赛季: {comp['season_name']}")
        break
```

---

## 2. matches/{competition_id}/{season_id}.json

**文件路径**: `new-data/matches/{competition_id}/{season_id}.json`  
**数据类型**: JSON 数组

### 数据结构

每个元素代表一场比赛，包含以下字段：

| 字段名 | 类型 | 说明 | 访问方式 |
|--------|------|------|----------|
| `match_id` | integer | 比赛ID（唯一标识） | `match["match_id"]` |
| `match_date` | string | 比赛日期（YYYY-MM-DD） | `match["match_date"]` |
| `kick_off` | string | 开球时间（HH:MM:SS.fff） | `match["kick_off"]` |
| `competition` | object | 联赛信息 | `match["competition"]` |
| `competition.competition_id` | integer | 联赛ID | `match["competition"]["competition_id"]` |
| `competition.country_name` | string | 国家名称 | `match["competition"]["country_name"]` |
| `competition.competition_name` | string | 联赛名称 | `match["competition"]["competition_name"]` |
| `season` | object | 赛季信息 | `match["season"]` |
| `season.season_id` | integer | 赛季ID | `match["season"]["season_id"]` |
| `season.season_name` | string | 赛季名称 | `match["season"]["season_name"]` |
| `home_team` | object | 主队信息 | `match["home_team"]` |
| `home_team.home_team_id` | integer | 主队ID | `match["home_team"]["home_team_id"]` |
| `home_team.home_team_name` | string | 主队名称 | `match["home_team"]["home_team_name"]` |
| `home_team.home_team_gender` | string | 性别 | `match["home_team"]["home_team_gender"]` |
| `home_team.home_team_group` | string/null | 分组 | `match["home_team"]["home_team_group"]` |
| `home_team.country` | object | 国家信息 | `match["home_team"]["country"]` |
| `home_team.country.id` | integer | 国家ID | `match["home_team"]["country"]["id"]` |
| `home_team.country.name` | string | 国家名称 | `match["home_team"]["country"]["name"]` |
| `home_team.managers` | array | 教练列表 | `match["home_team"]["managers"]` |
| `home_team.managers[].id` | integer | 教练ID | `match["home_team"]["managers"][0]["id"]` |
| `home_team.managers[].name` | string | 教练姓名 | `match["home_team"]["managers"][0]["name"]` |
| `home_team.managers[].nickname` | string/null | 教练昵称 | `match["home_team"]["managers"][0]["nickname"]` |
| `home_team.managers[].dob` | string | 出生日期 | `match["home_team"]["managers"][0]["dob"]` |
| `home_team.managers[].country` | object | 教练国籍 | `match["home_team"]["managers"][0]["country"]` |
| `away_team` | object | 客队信息 | `match["away_team"]` |
| `away_team.away_team_id` | integer | 客队ID | `match["away_team"]["away_team_id"]` |
| `away_team.away_team_name` | string | 客队名称 | `match["away_team"]["away_team_name"]` |
| `away_team.away_team_gender` | string | 性别 | `match["away_team"]["away_team_gender"]` |
| `away_team.away_team_group` | string/null | 分组 | `match["away_team"]["away_team_group"]` |
| `away_team.country` | object | 国家信息 | `match["away_team"]["country"]` |
| `away_team.country.id` | integer | 国家ID | `match["away_team"]["country"]["id"]` |
| `away_team.country.name` | string | 国家名称 | `match["away_team"]["country"]["name"]` |
| `away_team.managers` | array | 教练列表 | `match["away_team"]["managers"]` |
| `away_team.managers[].id` | integer | 教练ID | `match["away_team"]["managers"][0]["id"]` |
| `away_team.managers[].name` | string | 教练姓名 | `match["away_team"]["managers"][0]["name"]` |
| `away_team.managers[].nickname` | string/null | 教练昵称 | `match["away_team"]["managers"][0]["nickname"]` |
| `away_team.managers[].dob` | string | 出生日期 | `match["away_team"]["managers"][0]["dob"]` |
| `away_team.managers[].country` | object | 教练国籍 | `match["away_team"]["managers"][0]["country"]` |
| `home_score` | integer | 主队得分 | `match["home_score"]` |
| `away_score` | integer | 客队得分 | `match["away_score"]` |
| `match_status` | string | 比赛状态 | `match["match_status"]` |
| `match_status_360` | string | 360数据状态 | `match["match_status_360"]` |
| `last_updated` | string | 最后更新时间 | `match["last_updated"]` |
| `last_updated_360` | string | 360数据更新时间 | `match["last_updated_360"]` |
| `metadata` | object | 元数据 | `match["metadata"]` |
| `metadata.data_version` | string | 数据版本 | `match["metadata"]["data_version"]` |
| `metadata.shot_fidelity_version` | string | 射门数据版本 | `match["metadata"]["shot_fidelity_version"]` |
| `metadata.xy_fidelity_version` | string | 坐标数据版本 | `match["metadata"]["xy_fidelity_version"]` |
| `match_week` | integer | 比赛轮次 | `match["match_week"]` |
| `competition_stage` | object | 比赛阶段 | `match["competition_stage"]` |
| `competition_stage.id` | integer | 阶段ID | `match["competition_stage"]["id"]` |
| `competition_stage.name` | string | 阶段名称 | `match["competition_stage"]["name"]` |
| `stadium` | object | 体育场信息 | `match["stadium"]` |
| `stadium.id` | integer | 体育场ID | `match["stadium"]["id"]` |
| `stadium.name` | string | 体育场名称 | `match["stadium"]["name"]` |
| `stadium.country` | object | 体育场国家 | `match["stadium"]["country"]` |
| `stadium.country.id` | integer | 国家ID | `match["stadium"]["country"]["id"]` |
| `stadium.country.name` | string | 国家名称 | `match["stadium"]["country"]["name"]` |
| `referee` | object | 裁判信息 | `match["referee"]` |
| `referee.id` | integer | 裁判ID | `match["referee"]["id"]` |
| `referee.name` | string | 裁判姓名 | `match["referee"]["name"]` |
| `referee.country` | object | 裁判国籍 | `match["referee"]["country"]` |
| `referee.country.id` | integer | 国家ID | `match["referee"]["country"]["id"]` |
| `referee.country.name` | string | 国家名称 | `match["referee"]["country"]["name"]` |

### 使用示例

```python
import json
import os

# 根据 competition_id + season_id 读取比赛数据
competition_id = 9
season_id = 281
file_path = f'new-data/matches/{competition_id}/{season_id}.json'

with open(file_path, 'r', encoding='utf-8') as f:
    matches = json.load(f)

# 遍历所有比赛
for match in matches:
    match_id = match['match_id']
    print(f"比赛ID: {match_id}")
    print(f"{match['home_team']['home_team_name']} vs {match['away_team']['away_team_name']}")
    print(f"比分: {match['home_score']} - {match['away_score']}")
    print(f"日期: {match['match_date']}")
```

---

## 3. events/{match_id}.json

**文件路径**: `new-data/events/{match_id}.json`  
**数据类型**: JSON 数组

### 数据结构

每个元素代表一个比赛事件，包含以下字段：

| 字段名 | 类型 | 说明 | 访问方式 |
|--------|------|------|----------|
| `id` | string | 事件UUID | `event["id"]` |
| `index` | integer | 事件序号 | `event["index"]` |
| `period` | integer | 上/下半场（1/2） | `event["period"]` |
| `timestamp` | string | 时间戳（HH:MM:SS.fff） | `event["timestamp"]` |
| `minute` | integer | 比赛分钟 | `event["minute"]` |
| `second` | integer | 比赛秒数 | `event["second"]` |
| `type` | object | 事件类型 | `event["type"]` |
| `type.id` | integer | 类型ID | `event["type"]["id"]` |
| `type.name` | string | 类型名称 | `event["type"]["name"]` |
| `possession` | integer | 控球序号 | `event["possession"]` |
| `possession_team` | object | 控球方 | `event["possession_team"]` |
| `possession_team.id` | integer | 球队ID | `event["possession_team"]["id"]` |
| `possession_team.name` | string | 球队名称 | `event["possession_team"]["name"]` |
| `play_pattern` | object | 进攻模式 | `event["play_pattern"]` |
| `play_pattern.id` | integer | 模式ID | `event["play_pattern"]["id"]` |
| `play_pattern.name` | string | 模式名称 | `event["play_pattern"]["name"]` |
| `team` | object | 执行球队 | `event["team"]` |
| `team.id` | integer | 球队ID | `event["team"]["id"]` |
| `team.name` | string | 球队名称 | `event["team"]["name"]` |
| `player` | object | 执行球员（可选） | `event["player"]` |
| `player.id` | integer | 球员ID | `event["player"]["id"]` |
| `player.name` | string | 球员姓名 | `event["player"]["name"]` |
| `position` | object | 位置（可选） | `event["position"]` |
| `position.id` | integer | 位置ID | `event["position"]["id"]` |
| `position.name` | string | 位置名称 | `event["position"]["name"]` |
| `location` | array | 事件位置 [x, y] | `event["location"]` |
| `duration` | float | 持续时长（秒） | `event["duration"]` |
| `related_events` | array | 关联事件UUID列表 | `event["related_events"]` |
| `under_pressure` | boolean | 是否在压迫下 | `event["under_pressure"]` |
| `pass` | object | 传球详情（仅传球事件） | `event["pass"]` |
| `shot` | object | 射门详情（仅射门事件） | `event["shot"]` |
| `carry` | object | 带球详情（仅带球事件） | `event["carry"]` |
| `dribble` | object | 盘带详情（仅盘带事件） | `event["dribble"]` |
| `tactics` | object | 阵容阵型（仅首发/战术调整） | `event["tactics"]` |
| `substitution` | object | 换人详情（仅换人事件） | `event["substitution"]` |

### 事件专属字段

#### pass（传球事件）
| 字段名 | 类型 | 说明 | 访问方式 |
|--------|------|------|----------|
| `recipient` | object | 接球球员 | `event["pass"]["recipient"]` |
| `recipient.id` | integer | 球员ID | `event["pass"]["recipient"]["id"]` |
| `recipient.name` | string | 球员姓名 | `event["pass"]["recipient"]["name"]` |
| `length` | float | 传球距离 | `event["pass"]["length"]` |
| `angle` | float | 传球角度 | `event["pass"]["angle"]` |
| `height` | object | 传球高度 | `event["pass"]["height"]` |
| `height.id` | integer | 高度ID | `event["pass"]["height"]["id"]` |
| `height.name` | string | 高度名称 | `event["pass"]["height"]["name"]` |
| `end_location` | array | 传球终点 [x, y] | `event["pass"]["end_location"]` |
| `body_part` | object | 身体部位 | `event["pass"]["body_part"]` |
| `body_part.id` | integer | 部位ID | `event["pass"]["body_part"]["id"]` |
| `body_part.name` | string | 部位名称 | `event["pass"]["body_part"]["name"]` |
| `type` | object | 传球类型 | `event["pass"]["type"]` |
| `type.id` | integer | 类型ID | `event["pass"]["type"]["id"]` |
| `type.name` | string | 类型名称 | `event["pass"]["type"]["name"]` |

#### shot（射门事件）
| 字段名 | 类型 | 说明 | 访问方式 |
|--------|------|------|----------|
| `statsbomb_xg` | float | 期望进球值 | `event["shot"]["statsbomb_xg"]` |
| `end_location` | array | 射门终点 [x, y, z] | `event["shot"]["end_location"]` |
| `key_pass_id` | string/null | 关键传球UUID | `event["shot"]["key_pass_id"]` |
| `type` | object | 射门类型 | `event["shot"]["type"]` |
| `outcome` | object | 射门结果 | `event["shot"]["outcome"]` |
| `first_time` | boolean | 是否一脚射门 | `event["shot"]["first_time"]` |
| `technique` | object | 射门技术 | `event["shot"]["technique"]` |
| `body_part` | object | 身体部位 | `event["shot"]["body_part"]` |
| `freeze_frame` | array | 冰冻帧（球员位置） | `event["shot"]["freeze_frame"]` |

#### tactics（阵容阵型）
| 字段名 | 类型 | 说明 | 访问方式 |
|--------|------|------|----------|
| `formation` | integer | 阵型编码（如 3421） | `event["tactics"]["formation"]` |
| `lineup` | array | 阵容列表 | `event["tactics"]["lineup"]` |
| `lineup[].player` | object | 球员信息 | `event["tactics"]["lineup"][0]["player"]` |
| `lineup[].player.id` | integer | 球员ID | `event["tactics"]["lineup"][0]["player"]["id"]` |
| `lineup[].player.name` | string | 球员姓名 | `event["tactics"]["lineup"][0]["player"]["name"]` |
| `lineup[].position` | object | 位置信息 | `event["tactics"]["lineup"][0]["position"]` |
| `lineup[].position.id` | integer | 位置ID | `event["tactics"]["lineup"][0]["position"]["id"]` |
| `lineup[].position.name` | string | 位置名称 | `event["tactics"]["lineup"][0]["position"]["name"]` |
| `lineup[].jersey_number` | integer | 球衣号 | `event["tactics"]["lineup"][0]["jersey_number"]` |

### 使用示例

```python
import json

# 根据 match_id 读取事件数据
match_id = 3895292
file_path = f'new-data/events/{match_id}.json'

with open(file_path, 'r', encoding='utf-8') as f:
    events = json.load(f)

# 获取首发阵容
for event in events:
    if event['type']['name'] == '首发阵容':
        formation = event['tactics']['formation']
        print(f"阵型: {formation}")
        for player in event['tactics']['lineup']:
            print(f"  {player['jersey_number']}号 {player['player']['name']} - {player['position']['name']}")
        break

# 统计射门次数
shots = [e for e in events if '射门' in e['type']['name']]
print(f"射门次数: {len(shots)}")

# 统计传球次数
passes = [e for e in events if e['type']['name'] == '传球']
print(f"传球次数: {len(passes)}")
```

---

## 4. lineups/{match_id}.json

**文件路径**: `new-data/lineups/{match_id}.json`  
**数据类型**: JSON 数组

### 数据结构

每个元素代表一支球队，包含以下字段：

| 字段名 | 类型 | 说明 | 访问方式 |
|--------|------|------|----------|
| `team_id` | integer | 球队ID | `team["team_id"]` |
| `team_name` | string | 球队名称 | `team["team_name"]` |
| `lineup` | array | 球员阵容列表 | `team["lineup"]` |
| `lineup[].player_id` | integer | 球员ID | `team["lineup"][0]["player_id"]` |
| `lineup[].player_name` | string | 球员姓名 | `team["lineup"][0]["player_name"]` |
| `lineup[].player_nickname` | string/null | 球员昵称 | `team["lineup"][0]["player_nickname"]` |
| `lineup[].jersey_number` | integer | 球衣号 | `team["lineup"][0]["jersey_number"]` |
| `lineup[].country` | object | 国籍信息 | `team["lineup"][0]["country"]` |
| `lineup[].country.id` | integer | 国家ID | `team["lineup"][0]["country"]["id"]` |
| `lineup[].country.name` | string | 国家名称 | `team["lineup"][0]["country"]["name"]` |
| `lineup[].cards` | array | 牌记录列表 | `team["lineup"][0]["cards"]` |
| `lineup[].cards[].time` | string | 时间（MM:SS） | `team["lineup"][0]["cards"][0]["time"]` |
| `lineup[].cards[].card_type` | string | 牌类型 | `team["lineup"][0]["cards"][0]["card_type"]` |
| `lineup[].cards[].reason` | string | 原因 | `team["lineup"][0]["cards"][0]["reason"]` |
| `lineup[].cards[].period` | integer | 半场 | `team["lineup"][0]["cards"][0]["period"]` |
| `lineup[].positions` | array | 位置记录列表 | `team["lineup"][0]["positions"]` |
| `lineup[].positions[].position_id` | integer | 位置ID | `team["lineup"][0]["positions"][0]["position_id"]` |
| `lineup[].positions[].position` | string | 位置名称 | `team["lineup"][0]["positions"][0]["position"]` |
| `lineup[].positions[].from` | string | 开始时间（MM:SS） | `team["lineup"][0]["positions"][0]["from"]` |
| `lineup[].positions[].to` | string/null | 结束时间（MM:SS） | `team["lineup"][0]["positions"][0]["to"]` |
| `lineup[].positions[].from_period` | integer | 开始半场 | `team["lineup"][0]["positions"][0]["from_period"]` |
| `lineup[].positions[].to_period` | integer/null | 结束半场 | `team["lineup"][0]["positions"][0]["to_period"]` |
| `lineup[].positions[].start_reason` | string | 开始原因 | `team["lineup"][0]["positions"][0]["start_reason"]` |
| `lineup[].positions[].end_reason` | string | 结束原因 | `team["lineup"][0]["positions"][0]["end_reason"]` |

### 使用示例

```python
import json

# 根据 match_id 读取阵容数据
match_id = 3895292
file_path = f'new-data/lineups/{match_id}.json'

with open(file_path, 'r', encoding='utf-8') as f:
    lineups = json.load(f)

# 遍历两支球队
for team in lineups:
    print(f"球队: {team['team_name']}")
    print(f"球员数: {len(team['lineup'])}")
    
    # 遍历球员
    for player in team['lineup']:
        print(f"  {player['jersey_number']}号 {player['player_name']} ({player['country']['name']})")
        
        # 显示位置变化
        for pos in player['positions']:
            print(f"    位置: {pos['position']} | {pos['from']} - {pos['to'] or '结束'} | {pos['start_reason']} -> {pos['end_reason']}")
        
        # 显示牌记录
        if player['cards']:
            for card in player['cards']:
                print(f"    牌: {card['card_type']} at {card['time']} ({card['reason']})")
```

---

## 完整数据访问流程

### 示例：从联赛到比赛事件

```python
import json
import os

# 1. 读取 competitions.json，获取 competition_id + season_id
with open('new-data/competitions.json', 'r', encoding='utf-8') as f:
    competitions = json.load(f)

# 选择德甲 2023/2024 赛季
target = next(c for c in competitions 
              if c['competition_id'] == 9 and c['season_id'] == 281)

print(f"联赛: {target['competition_name']}")
print(f"赛季: {target['season_name']}")

# 2. 根据 competition_id + season_id 读取比赛列表
matches_file = f"new-data/matches/{target['competition_id']}/{target['season_id']}.json"
with open(matches_file, 'r', encoding='utf-8') as f:
    matches = json.load(f)

print(f"比赛数量: {len(matches)}")

# 3. 选择一场比赛，获取 match_id
first_match = matches[0]
match_id = first_match['match_id']
print(f"比赛ID: {match_id}")
print(f"{first_match['home_team']['home_team_name']} vs {first_match['away_team']['away_team_name']}")

# 4. 根据 match_id 读取事件数据
events_file = f"new-data/events/{match_id}.json"
with open(events_file, 'r', encoding='utf-8') as f:
    events = json.load(f)

print(f"事件数量: {len(events)}")

# 5. 根据 match_id 读取阵容数据
lineups_file = f"new-data/lineups/{match_id}.json"
with open(lineups_file, 'r', encoding='utf-8') as f:
    lineups = json.load(f)

print(f"球队数量: {len(lineups)}")
```

---

## 数据字段总结

### competitions.json → matches
- **关联键**: `competition_id` + `season_id`
- **获取内容**: 该联赛该赛季的所有比赛基本信息

### matches → events/lineups
- **关联键**: `match_id`
- **获取内容**: 
  - `events/{match_id}.json`: 该比赛的所有事件（传球、射门、换人、阵型等）
  - `lineups/{match_id}.json`: 该比赛两队的详细阵容、位置变化、牌记录等

### 文件命名规则
- `matches/{competition_id}/{season_id}.json`: 联赛ID/赛季ID
- `events/{match_id}.json`: 比赛ID
- `lineups/{match_id}.json`: 比赛ID

### 数据特点
- **阵型数据**: 存储在 events 文件的 `type.name == "首发阵容"` 或 `type.name == "战术调整"` 事件的 `tactics.formation` 字段中
- **位置追踪**: lineups 文件的 `positions[]` 字段记录每名球员的出场时段和位置变化
- **事件坐标**: events 文件中大部分事件包含 `location` 字段（[x, y] 坐标）
- **射门xG**: events 文件的 `shot.statsbomb_xg` 字段提供期望进球值

## 注意
当你读完这个文件中的内容后，需要单独一行向我回复：`我明白了！教练！！！`