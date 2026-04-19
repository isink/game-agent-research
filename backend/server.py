"""FastAPI server — bridges Godot frontend and Python Agent backend.

Endpoints:
  POST /miracle          Inject a miracle (player action)
  POST /tick             Advance simulation one step
  GET  /state            Current village state snapshot
  GET  /research         Research metrics (distortion, beliefs, narratives)
  GET  /export           Download full distortion log as JSON
  WS   /ws               Real-time tick broadcast to Godot
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel

load_dotenv()

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

from agents.village import Village

village = Village()
connected_clients: list[WebSocket] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    await village.initialize()
    logger.info("Village ready.")
    yield


app = FastAPI(title="Remnants of the Divine — Agent Backend", lifespan=lifespan)


# ── Models ─────────────────────────────────────────────────────────────────

class MiracleRequest(BaseModel):
    miracle_type: str          # rain | lightning | harvest | plague | fire | eclipse
    position: list[int] | None = None  # [x, y] grid position


# ── REST Endpoints ─────────────────────────────────────────────────────────

@app.post("/miracle")
async def inject_miracle(req: MiracleRequest):
    pos = tuple(req.position) if req.position else None
    miracle = village.queue_miracle(req.miracle_type, pos)
    return {
        "queued": True,
        "miracle_type": miracle.miracle_type,
        "description": miracle.description,
        "position": list(miracle.position),
        "scheduled_tick": miracle.tick,
    }


@app.post("/tick")
async def advance_tick():
    result = await village.tick()
    payload = {
        "tick": result.tick,
        "conversations": result.conversations,
        "miracle": result.miracle,
        "agent_states": result.agent_states,
        "social_narratives": result.social_narratives,
        "research_metrics": result.research_metrics,
        "reflections": result.reflections or [],
    }
    # Broadcast to all connected WebSocket clients (Godot)
    await _broadcast(payload)
    return payload


@app.get("/state")
async def get_state():
    return {
        "tick": village.tick_count,
        "agents": [a.to_dict() for a in village.agents],
    }


@app.get("/research")
async def get_research():
    return {
        "tick": village.tick_count,
        "distortion_records": village.distortion_engine.export_records(),
        "drift_by_hop": village.distortion_engine.avg_drift_by_hop(),
        "social_narratives": village.social_pool.all_narratives(),
        "agent_beliefs": {
            a.name: {"beliefs": a.beliefs, "drift": a.memory.avg_semantic_drift()}
            for a in village.agents
        },
    }


@app.get("/export")
async def export_data():
    export_dir = Path(os.getenv("EXPORT_DIR", "experiments"))
    export_dir.mkdir(parents=True, exist_ok=True)
    path = export_dir / f"distortion_tick_{village.tick_count}.json"
    village.distortion_engine.records  # trigger any pending flush
    data = {
        "tick": village.tick_count,
        "distortion_records": village.distortion_engine.export_records(),
        "social_narratives": village.social_pool.all_narratives(),
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return {"exported_to": str(path), "records": len(village.distortion_engine.records)}


@app.get("/miracles")
async def list_miracles():
    return {"available": list(village.MIRACLE_DESCRIPTIONS.keys())}


# ── WebSocket ──────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    logger.info(f"WebSocket client connected. Total: {len(connected_clients)}")
    try:
        while True:
            # Keep connection alive; ticks are pushed via /tick endpoint
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        connected_clients.remove(websocket)
        logger.info("WebSocket client disconnected.")


async def _broadcast(payload: dict) -> None:
    if not connected_clients:
        return
    msg = json.dumps(payload, ensure_ascii=False)
    dead: list[WebSocket] = []
    for ws in connected_clients:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        connected_clients.remove(ws)


# ── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8765, reload=False)
