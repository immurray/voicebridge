# VoiceBridge — Main Application
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

import os

# API routes
from app.ws import router as ws_router
from app.session import router as session_router

app = FastAPI(title="VoiceBridge", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ws_router)
app.include_router(session_router)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/version")
async def version():
    return {"version": "0.1.0", "build": os.getenv("BUILD_COMMIT", "dev")}


# Static files — MUST be last to avoid eating API routes
from pathlib import Path
from fastapi.staticfiles import StaticFiles

static_dir = Path(__file__).parent.parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
