# VoiceBridge Session Management
import uuid
import time
from fastapi import APIRouter
from pydantic import BaseModel
from app.config import settings

router = APIRouter(prefix="/api/session", tags=["session"])

# In-memory session store
sessions: dict[str, dict] = {}


class CreateSessionRequest(BaseModel):
    language: str = "zh"  # "zh" or "en"


class JoinSessionRequest(BaseModel):
    language: str = "en"


@router.post("/create")
async def create_session(req: CreateSessionRequest):
    """Create a new session, return session_id and share link."""
    session_id = uuid.uuid4().hex[:12]
    sessions[session_id] = {
        "id": session_id,
        "created_at": time.time(),
        "peers": {},
    }
    return {
        "session_id": session_id,
        "share_link": f"/session.html?sid={session_id}",
        "language": req.language,
    }


@router.post("/join/{session_id}")
async def join_session(session_id: str, req: JoinSessionRequest):
    """Join an existing session."""
    if session_id not in sessions:
        return {"error": "Session not found or expired", "code": 404}

    peer_id = uuid.uuid4().hex[:8]
    sessions[session_id]["peers"][peer_id] = {
        "id": peer_id,
        "language": req.language,
        "joined_at": time.time(),
    }

    return {
        "session_id": session_id,
        "peer_id": peer_id,
        "language": req.language,
    }


@router.get("/{session_id}")
async def get_session(session_id: str):
    """Get session info."""
    if session_id not in sessions:
        return {"error": "Session not found", "code": 404}

    session = sessions[session_id]
    return {
        "session_id": session["id"],
        "peer_count": len(session["peers"]),
        "peers": session["peers"],
    }
