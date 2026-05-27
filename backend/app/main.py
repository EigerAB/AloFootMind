from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes.analysis import router as analysis_router
from app.api.routes.competitions import router as competitions_router
from app.api.routes.matches import router as matches_router
from app.core.config import settings
from app.db.milvus_client import connect_milvus, disconnect_milvus
from app.db.postgres import init_db
from app.db.redis_client import close_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    connect_milvus()
    yield
    await close_redis()
    disconnect_milvus()


app = FastAPI(
    title="AloFootMind API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
    )


app.include_router(competitions_router)
app.include_router(matches_router)
app.include_router(analysis_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
