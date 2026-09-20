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

@app.get("/api/v1/berth-conflicts")
def berth_conflicts():
    return [c.__dict__ for c in detect_berth_conflicts(sim.port_calls)]


@app.get("/api/v1/port-calls/{call_id}/risk")
def port_call_risk(call_id: str):
    call = next((c for c in sim.port_calls if c.id == call_id), None)
    if call is None:
        return {"found": False}
    conflicts = detect_berth_conflicts(sim.port_calls)
    conflicted_ids = {x.first_call_id for x in conflicts} | {x.second_call_id for x in conflicts}
    level, score, reasons = score_port_call(call, sim.weather, call.id in conflicted_ids)
    return {"found": True, "call_id": call.id, "risk": level, "score": score, "reasons": reasons}


@app.websocket("/ws/harbor")
async def harbor_ws(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            await ws.send_json(sim.overview().model_dump(mode="json"))
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        return
