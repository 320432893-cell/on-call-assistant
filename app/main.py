# 职责：组装 FastAPI 应用、生命周期、路由、模板和横切中间件。
# 不做什么：不承载具体业务规则、索引算法、RAG 检索流程或测试夹具。
# 允许依赖层：app.core、app.config、app.routers、app.services 的关闭入口。
# 谁不应该 import：app.services、app.models、app.config、测试夹具不应 import 本入口执行业务逻辑。
"""On-Call Assistant FastAPI entrypoint."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.core.observability import (
    configure_logging,
    http_exception_handler,
    request_context_middleware,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.routers import v1_router, v2_router, v3_router, v4_router
from app.services import close_indexer, get_vectorstore

settings = get_settings()
configure_logging()
logger = logging.getLogger("app.startup")


def prepare_runtime_paths() -> None:
    # 启动时检查目录结构
    for path in ["./data/raw", "./data/processed", "./indexes/tantivy", "./indexes/qdrant"]:
        Path(path).mkdir(parents=True, exist_ok=True)

    # 启动时清理 Tantivy 残留 lock 文件（防 uvicorn --reload 异常退出残留）
    # 此刻 app 还没起来，不可能有任何活跃 writer，删锁安全。
    tantivy_dir = Path(settings.TANTIVY_INDEX_PATH)
    for lock_name in (".tantivy-writer.lock", ".tantivy-meta.lock"):
        stale = tantivy_dir / lock_name
        if stale.exists():
            try:
                stale.unlink()
                logger.info("cleaned_stale_lock path=%s", stale)
            except OSError as e:
                logger.warning("clean_stale_lock_failed path=%s error=%s", stale, e)


def dependency_status() -> dict[str, bool]:
    checks = {
        "embedding_configured": lambda: bool(settings.EMBEDDING_MODEL),
        "qdrant": lambda: get_vectorstore().health_check(),
    }
    status: dict[str, bool] = {}
    for name, check in checks.items():
        try:
            status[name] = bool(check())
        except Exception:
            logger.exception("health_dependency_check_failed dependency=%s", name)
            status[name] = False
    return status


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    prepare_runtime_paths()
    yield
    # 关闭时清理资源
    close_indexer()


app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
    lifespan=lifespan,
)
app.middleware("http")(request_context_middleware)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# 模板
app.templates = Jinja2Templates(directory="app/templates")

# 挂载路由
app.include_router(v1_router)
app.include_router(v2_router)
app.include_router(v3_router)
app.include_router(v4_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "On-Call Assistant API", "docs": "/docs"}


@app.get("/health")
async def health() -> dict[str, Any]:
    paths = {
        "raw_data": Path("./data/raw"),
        "processed_data": Path("./data/processed"),
        "tantivy_index": Path(settings.TANTIVY_INDEX_PATH),
        "qdrant_index": Path(settings.QDRANT_PATH),
    }
    path_status = {name: path.exists() for name, path in paths.items()}
    dependencies = dependency_status()
    status = "ok" if all(path_status.values()) and all(dependencies.values()) else "degraded"
    return {
        "status": status,
        "app": settings.APP_NAME,
        "debug": settings.DEBUG,
        "paths": path_status,
        "dependencies": dependencies,
    }
