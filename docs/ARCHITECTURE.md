# PortFlow architecture

## v0.1
```text
synthetic harbor simulator
        |
        v
typed operations state
        |
        +--> REST snapshot
        |
        +--> WebSocket stream
        |
        v
React operations console
        |
        +--> MapLibre live harbor
        +--> berth board
        +--> port-call critical path
        +--> event feed
        +--> connectivity degradation controls
```

## Canonical domain primitives
- Vessel
- Berth
- PortCall
- PortCallStage
- WeatherState
- ConnectivityState
- OperationsEvent

The next increment persists these through PostgreSQL and moves simulation events into an append-only event ledger.
