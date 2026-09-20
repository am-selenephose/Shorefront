# PortFlow

PortFlow is a port-call operations control tower for live vessel, berth, service, weather, delay, and connectivity state.

## Status
Private portfolio build, v0.1 foundation.

## Product principles
- Operational software first, AI/ML as bounded capabilities.
- Real-time state must remain inspectable and attributable.
- Synthetic demo data must never be presented as real port operations.
- Degraded connectivity is a first-class operating mode.
- Port-call dependencies are modeled explicitly, not hidden behind chat.

## Monorepo
- `apps/api`: FastAPI service and deterministic harbor simulator
- `apps/web`: React + TypeScript operations console

## Demo domain
The initial demo uses a fictionalized Rotterdam-like port topology and fully synthetic operations data.
