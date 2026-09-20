from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from .models import LinkMode
from .domain import detect_berth_conflicts, score_port_call
from .simulator import HarborSimulator

sim = HarborSimulator()

@asynccontextmanager
async def lifespan(app: FastAPI):
    stop = asyncio.Event()
    async def runner():
        while not stop.is_set():
            sim.tick()
            await asyncio.sleep(2)
    task = asyncio.create_task(runner())
    yield
    stop.set()
    task.cancel()

app = FastAPI(title="PortFlow API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173","http://127.0.0.1:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class ConnectivityRequest(BaseModel):
    mode: LinkMode

@app.get("/healthz")
def healthz():
    return {"ok": True, "service": "portflow-api"}

@app.get("/api/v1/harbor")
def harbor():
    return sim.overview()

@app.post("/api/v1/connectivity")
def connectivity(req: ConnectivityRequest):
    sim.set_connectivity(req.mode)
    return sim.connectivity

@app.websocket("/ws/harbor")
async def harbor_ws(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            await ws.send_json(sim.overview().model_dump(mode="json"))
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        return
