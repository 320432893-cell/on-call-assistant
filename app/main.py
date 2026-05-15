# On-Call Assistant FastAPI 入口

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import os

from app.config import get_settings
from app.routers import v1_router, v2_router, v3_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时检查目录结构
    for path in ["./data/raw", "./data/processed", "./indexes/tantivy", "./indexes/qdrant"]:
        os.makedirs(path, exist_ok=True)

    # 启动时清理 Tantivy 残留 lock 文件（防 uvicorn --reload 异常退出残留）
    # 此刻 app 还没起来，不可能有任何活跃 writer，删锁安全。
    from pathlib import Path
    tantivy_dir = Path(settings.TANTIVY_INDEX_PATH)
    for lock_name in (".tantivy-writer.lock", ".tantivy-meta.lock"):
        stale = tantivy_dir / lock_name
        if stale.exists():
            try:
                stale.unlink()
                print(f"[startup] 清理残留锁: {stale}")
            except OSError as e:
                print(f"[startup] 清理锁失败 {stale}: {e}")

    yield
    # 关闭时清理资源
    from app.services import close_indexer
    close_indexer()


app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

# 模板
app.templates = Jinja2Templates(directory="app/templates")

# 挂载路由
app.include_router(v1_router)
app.include_router(v2_router)
app.include_router(v3_router)


@app.get("/")
async def root():
    return {"message": "On-Call Assistant API", "docs": "/docs"}


@app.get("/health")
async def health():
    return {"status": "ok"}
