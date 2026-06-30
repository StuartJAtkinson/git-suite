import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from routers import (auth, scan, hubs, config, reconcile,
                     plan, execute, migration, cluster, stars,
                     order, promote)

_LOG_DIR = Path(__file__).parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)-28s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(_LOG_DIR / "app.log", encoding="utf-8"),
    ],
)
# These libraries dump huge DEBUG payloads (full SQL, HTTP bodies) — keep quiet.
for _noisy in ("aiosqlite", "httpcore", "httpx", "watchfiles"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)
log = logging.getLogger("git-suite.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("startup — initialising database")
    await init_db()
    log.info("database ready")
    yield
    log.info("shutdown")


app = FastAPI(title="git-suite API", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    t0 = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - t0) * 1000
    log.info("%s %s -> %d  %.0fms", request.method, request.url.path, response.status_code, ms)
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:2173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,       prefix="/auth",  tags=["auth"])
app.include_router(scan.router,       prefix="/api",   tags=["scan"])
app.include_router(hubs.router,       prefix="/api",   tags=["hubs"])
app.include_router(config.router,     prefix="/api",   tags=["config"])
app.include_router(reconcile.router,  prefix="/api",   tags=["reconcile"])
app.include_router(plan.router,       prefix="/api",   tags=["plan"])
app.include_router(execute.router,    prefix="/api",   tags=["execute"])
app.include_router(migration.router,  prefix="/api",   tags=["migration"])
app.include_router(cluster.router,    prefix="/api",   tags=["cluster"])
app.include_router(stars.router,      prefix="/api",   tags=["stars"])
app.include_router(order.router,      prefix="/api",   tags=["order"])
app.include_router(promote.router,    prefix="/api",   tags=["promote"])


@app.get("/health")
async def health():
    return {"status": "ok"}
