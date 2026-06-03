# ETL 全量重新生成 Embedding 讨论摘要

## 背景

demo-data 中的事件 JSON 使用中文事件类型名称（如射门、传球），但 ETL 代码中硬编码的是英文事件名称（如 Shot、Pass）。这导致：

1. events_aggregated 表中大量比赛的统计数据为 0（射门、传球、犯规等）
2. player_profiles 中球员统计为 0（0 passes, 0% pass completion 等）
3. tactical_segments 中战术片段描述异常（缺少事件映射）

## 已修复的代码

### 1. backend/app/etl/parser.py
- parse_events_aggregated(): 同时支持中英文事件类型匹配
- extract_formations(): 同时支持 Starting XI / 首发阵容、Tactical Shift / 战术调整

### 2. backend/app/etl/text_generator.py
- generate_tactical_segment_text(): 中英文事件类型映射
- aggregate_player_season_stats(): 中英文事件类型匹配

## PostgreSQL 数据修复

使用 backend/scripts/update_events_aggregated.py 对已入库数据重新解析并更新统计列。

## Milvus Embedding 数据状态

三个 collection 都需要重新生成，现有数据基于未修复的代码。

## 全量重新生成方案

1. 清空 Milvus 三个 collection
2. 重置 ingestion_log.step_embed 为 pending
3. 运行 ingest.py 全量重新导入
4. 单独运行 ingest_player_profiles()

## 与 RAG 检索改进的关系

RAG 检索改进依赖 Milvus 三个 collection 的数据完整性，建议先完成全量 ETL re-run 再上线。
