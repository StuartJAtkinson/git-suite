from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from routers import auth, scan, hubs, commercial, readme


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="git-suite API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,       prefix="/auth",  tags=["auth"])
app.include_router(scan.router,       prefix="/api",   tags=["scan"])
app.include_router(hubs.router,       prefix="/api",   tags=["hubs"])
app.include_router(commercial.router, prefix="/api",   tags=["commercial"])
app.include_router(readme.router,     prefix="/api",   tags=["readme"])


@app.get("/health")
async def health():
    return {"status": "ok"}
