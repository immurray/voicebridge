# VoiceBridge v2 — Solo Translation App
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.ws import router as ws_router

app = FastAPI(title="VoiceBridge", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ws_router)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.2.0"}


@app.get("/version")
async def version():
    return {"version": "0.2.0", "build": os.getenv("BUILD_COMMIT", "dev")}


# Static files — MUST be last to avoid eating API routes
static_dir = Path(__file__).parent.parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
