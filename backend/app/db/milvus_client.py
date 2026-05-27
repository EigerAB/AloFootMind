from pymilvus import Collection, connections
from app.core.config import settings


def connect_milvus() -> None:
    connections.connect(
        alias="default",
        host=settings.MILVUS_HOST,
        port=settings.MILVUS_PORT,
    )


def disconnect_milvus() -> None:
    connections.disconnect("default")


def get_collection(name: str) -> Collection:
    return Collection(name=name)
