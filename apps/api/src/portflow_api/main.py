from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .domain import detect_berth_conflicts, score_port_call
from .models import IncidentType, LinkMode
from .simulator import HarborSimulator
from .storage import OperationsStore


store = OperationsStore()
store.init_schema()


def build_simulator() -> HarborSimulator:
    snapshot = store.load_snapshot()
    return HarborSimulator(
        initial=snapshot,
        event_sink=store.append_event,
        incident_sink=store.upsert_incident,
        snapshot_sink=store.save_snapshot,
        spool_sink=store.queue_outbound_event,
        replay_sink=lambda: len(store.replay_outbound_events(lambda event: True)),
        pending_count=store.pending_outbound_count,
    )


sim = build_simulator()


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


app = FastAPI(title="PortFlow API", version="0.3.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConnectivityRequest(BaseModel):
    mode: LinkMode


class IncidentRequest(BaseModel):
    incident_type: IncidentType
    target_port_call_id: str | None = None
    impact_minutes: int | None = Field(default=None, ge=0, le=720)


@app.get("/healthz")
def healthz():
    return {
        "ok": True,
        "service": "portflow-api",
        "version": "0.3.0",
        "persistence": True,
    }


@app.get("/api/v1/harbor")
def harbor():
    return sim.overview()


@app.post("/api/v1/connectivity")
def connectivity(req: ConnectivityRequest):
    sim.set_connectivity(req.mode)
    return sim.connectivity


@app.get("/api/v1/events")
def events(limit: int = 100):
    return store.list_events(limit=limit)


@app.get("/api/v1/incidents")
def incidents(limit: int = 100):
    return store.list_incidents(limit=limit)


@app.post("/api/v1/incidents")
def create_incident(req: IncidentRequest):
    try:
        return sim.inject_incident(
            incident_type=req.incident_type,
            target_port_call_id=req.target_port_call_id,
            impact_minutes=req.impact_minutes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.patch("/api/v1/incidents/{incident_id}/resolve")
def resolve_incident(incident_id: str):
    try:
        return sim.resolve_incident(incident_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/v1/replay/pending")
def replay_pending():
    return {
        "pending": store.pending_outbound_count(),
        "events": store.pending_outbound_events(limit=200),
    }


@app.get("/api/v1/replay/receipts")
def replay_receipts(limit: int = 100):
    return store.list_replay_receipts(limit=limit)


@app.post("/api/v1/replay")
def replay_now():
    receipts = store.replay_outbound_events(lambda event: True)
    sim._refresh_queued_count()
    sim._persist()
    return {
        "replayed": len(receipts),
        "pending": store.pending_outbound_count(),
        "receipts": receipts,
    }


@app.get("/api/v1/port-calls/{call_id}/dependency-graph")
def dependency_graph(call_id: str):
    try:
        return sim.dependency_graph(call_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/v1/berth-conflicts")
def berth_conflicts():
    return [conflict.__dict__ for conflict in detect_berth_conflicts(sim.port_calls)]


@app.get("/api/v1/port-calls/{call_id}/risk")
def port_call_risk(call_id: str):
    call = next((candidate for candidate in sim.port_calls if candidate.id == call_id), None)
    if call is None:
        raise HTTPException(status_code=404, detail=f"Unknown port call: {call_id}")
    conflicts = detect_berth_conflicts(sim.port_calls)
    conflicted_ids = {x.first_call_id for x in conflicts} | {x.second_call_id for x in conflicts}
    level, score, reasons = score_port_call(call, sim.weather, call.id in conflicted_ids)
    return {"found": True, "call_id": call.id, "risk": level, "score": score, "reasons": reasons}


@app.post("/api/v1/demo/reset")
def reset_demo():
    global sim
    store.clear_demo_state()
    sim = HarborSimulator(
        event_sink=store.append_event,
        incident_sink=store.upsert_incident,
        snapshot_sink=store.save_snapshot,
        spool_sink=store.queue_outbound_event,
        replay_sink=lambda: len(store.replay_outbound_events(lambda event: True)),
        pending_count=store.pending_outbound_count,
    )
    return sim.overview()


@app.websocket("/ws/harbor")
async def harbor_ws(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            await ws.send_json(sim.overview().model_dump(mode="json"))
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        return
