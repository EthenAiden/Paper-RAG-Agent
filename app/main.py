"""FastAPI 应用入口"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.core.config import get_settings
from app.db.mysql import init_db
from app.db.milvus_client import ensure_collection
from app.db.minio_client import ensure_bucket
from app.api import api_router

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化
    logger.info("应用启动中...")
    await init_db()
    logger.info("数据库初始化完成")
    ensure_collection()
    logger.info("Milvus集合初始化完成")
    ensure_bucket()
    logger.info("MinIO存储桶初始化完成")
    logger.info("应用启动完成")
    yield
    # 关闭时清理
    logger.info("应用关闭中...")
    from app.db.redis_client import close_redis
    await close_redis()
    logger.info("应用已关闭")


app = FastAPI(
    title="RAG 问答机器人",
    description="基于 LangChain + LangGraph + Advanced RAG 的问答服务",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health", tags=["健康检查"])
async def health():
    return {"status": "ok"}
