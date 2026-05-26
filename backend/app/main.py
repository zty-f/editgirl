"""FastAPI 应用入口。"""
from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.store import init_db
from .api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="校对女孩 Backend", version="0.1.0", lifespan=lifespan)

# 前端跨域(Vite dev 在 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(router, prefix="/api")


@app.get("/")
async def root():
    return {"ok": True, "service": "editgirl-backend", "version": "0.1.0"}


def main():
    import uvicorn
    print("校对女孩 Backend · http://localhost:8000")
    print("  API docs: http://localhost:8000/docs")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    main()
