from pymilvus import (
    CollectionSchema,
    DataType,
    FieldSchema,
    MilvusClient,
    connections,
)

BGE_M3_DIM = 1024

COLLECTIONS = {
    "match_summaries": {
        "description": "Layer 1 - Match-level summaries for high-level queries",
        "fields": [
            FieldSchema("id", DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema("match_id", DataType.INT64),
            FieldSchema("competition_id", DataType.INT64),
            FieldSchema("season_id", DataType.INT64),
            FieldSchema("home_team_id", DataType.INT64),
            FieldSchema("away_team_id", DataType.INT64),
            FieldSchema("text", DataType.VARCHAR, max_length=4096),
            FieldSchema(
                "dense_vector", DataType.FLOAT_VECTOR, dim=BGE_M3_DIM
            ),
            FieldSchema("sparse_vector", DataType.SPARSE_FLOAT_VECTOR),
        ],
    },
    "tactical_segments": {
        "description": "Layer 2 - Possession-level tactical segments",
        "fields": [
            FieldSchema("id", DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema("match_id", DataType.INT64),
            FieldSchema("competition_id", DataType.INT64),
            FieldSchema("season_id", DataType.INT64),
            FieldSchema("team_id", DataType.INT64),
            FieldSchema("possession_index", DataType.INT64),
            FieldSchema("text", DataType.VARCHAR, max_length=2048),
            FieldSchema(
                "dense_vector", DataType.FLOAT_VECTOR, dim=BGE_M3_DIM
            ),
            FieldSchema("sparse_vector", DataType.SPARSE_FLOAT_VECTOR),
        ],
    },
    "player_profiles": {
        "description": "Layer 3 - Player season profiles",
        "fields": [
            FieldSchema("id", DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema("player_id", DataType.INT64),
            FieldSchema("competition_id", DataType.INT64),
            FieldSchema("season_id", DataType.INT64),
            FieldSchema("team_id", DataType.INT64),
            FieldSchema("text", DataType.VARCHAR, max_length=4096),
            FieldSchema(
                "dense_vector", DataType.FLOAT_VECTOR, dim=BGE_M3_DIM
            ),
            FieldSchema("sparse_vector", DataType.SPARSE_FLOAT_VECTOR),
        ],
    },
}

INDEX_PARAMS = {
    "dense_vector": {
        "index_type": "HNSW",
        "metric_type": "COSINE",
        "params": {"M": 16, "efConstruction": 200},
    },
    "sparse_vector": {
        "index_type": "SPARSE_INVERTED_INDEX",
        "metric_type": "IP",
        "params": {"drop_ratio_build": 0.2},
    },
}


def init_milvus_collections(host: str = "localhost", port: int = 19530) -> None:
    connections.connect(host=host, port=port)

    from pymilvus import Collection, utility

    for name, config in COLLECTIONS.items():
        if utility.has_collection(name):
            print(f"[milvus] Collection '{name}' already exists, skipping.")
            continue

        schema = CollectionSchema(
            fields=config["fields"],
            description=config["description"],
            enable_dynamic_field=False,
        )
        collection = Collection(name=name, schema=schema)

        for field_name, idx_params in INDEX_PARAMS.items():
            collection.create_index(field_name=field_name, index_params=idx_params)

        collection.load()
        print(f"[milvus] Created and loaded collection '{name}'.")

    connections.disconnect("default")
