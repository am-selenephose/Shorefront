import { useEffect, useMemo, useState } from 'react'
import { BerthTimeline } from './BerthTimeline'
import { HarborMap } from './HarborMap'
import { IncidentControls } from './IncidentControls'
import type { HarborState, IncidentType, LinkMode, PortCall } from './types'
import './styles.css'


const fmtTime = (value: string) =>
  new Intl.DateTimeFormat('en', { hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value))

const usd = (value: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value)


function Metric({ label, value, detail }: { label: string; value: string | number; detail?: string }) {
  return (
    <div className="metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
      {detail && <small>{detail}</small>}
    </div>
  )
}


function RiskPill({ risk }: { risk: string }) {
  return <span className={'risk ' + risk}>{risk.toUpperCase()}</span>
}


function PortCallCard({ call, state }: { call: PortCall; state: HarborState }) {
  const vessel = state.vessels.find(v => v.id === call.vessel_id)
  const berth = state.berths.find(b => b.id === call.berth_id)

  return (
    <div className="call-card">
      <div className="call-head">
        <div>
          <strong>{vessel?.name}</strong>
          <span>{vessel?.vessel_type} · {berth?.name}</span>
        </div>
        <RiskPill risk={call.risk} />
      </div>

      <div className="call-stats">
        <span>ETA <b>{fmtTime(call.arrival_eta)}</b></span>
        <span>Delay <b>{call.delay_minutes}m</b></span>
        <span>Exposure <b>{usd(call.estimated_cost_exposure_usd)}</b></span>
      </div>

      <div className="stage-strip">
        {call.stages.map(stage => {
          const completed = Boolean(stage.actual_at) || stage.state === 'completed'
          return (
            <div className="stage" key={stage.code}>
              <i className={completed ? 'done' : ''} />
              <span>{stage.label}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}


export default function App() {
  const [state, setState] = useState<HarborState | null>(null)
  const [online, setOnline] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let ws: WebSocket | undefined
    let dead = false

    const connect = () => {
      const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(protocol + '://' + location.host + '/ws/harbor')
      ws.onopen = () => setOnline(true)
      ws.onmessage = event => setState(JSON.parse(event.data))
      ws.onclose = () => {
        setOnline(false)
        if (!dead) setTimeout(connect, 1500)
      }
    }

    fetch('/api/v1/harbor')
      .then(response => response.json())
      .then(setState)
      .catch(() => {})

    connect()

    return () => {
      dead = true
      ws?.close()
    }
  }, [])

  const exposure = useMemo(
    () => state?.port_calls.reduce((sum, call) => sum + call.estimated_cost_exposure_usd, 0) ?? 0,
    [state],
  )

  async function refresh() {
    const response = await fetch('/api/v1/harbor')
    if (response.ok) setState(await response.json())
  }

  async function setMode(mode: LinkMode) {
    setBusy(true)
    try {
      await fetch('/api/v1/connectivity', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ mode }),
      })
      await refresh()
    } finally {
      setBusy(false)
    }
  }

  async function injectIncident(
    incidentType: IncidentType,
    targetPortCallId?: string,
    impactMinutes?: number,
  ) {
    setBusy(true)
    try {
      const response = await fetch('/api/v1/incidents', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          incident_type: incidentType,
          target_port_call_id: targetPortCallId,
          impact_minutes: impactMinutes,
        }),
      })
      if (!response.ok) throw new Error(await response.text())
      await refresh()
    } finally {
      setBusy(false)
    }
  }

  async function resetDemo() {
    setBusy(true)
    try {
      const response = await fetch('/api/v1/demo/reset', { method: 'POST' })
      if (!response.ok) throw new Error(await response.text())
      setState(await response.json())
    } finally {
      setBusy(false)
    }
  }

  if (!state) {
    return (
      <div className="boot">
        PORTFLOW
        <span>Loading operations picture...</span>
      </div>
    )
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brandmark">PF</div>
          <div>
            <b>PORTFLOW</b>
            <span>OPERATIONS</span>
          </div>
        </div>

        <nav>
          <a className="active" href="#overview">Harbor Overview</a>
          <a href="#berth-schedule">Berth Schedule</a>
          <a href="#port-calls">Port Calls</a>
          <a href="#incidents">Incidents</a>
          <a href="#ledger">Operations Ledger</a>
        </nav>

        <div className="side-foot">
          <span className={online ? 'live-dot' : 'offline-dot'} />
          {online ? 'LIVE STREAM' : 'RECONNECTING'}
          <small>Persistent synthetic operations</small>
        </div>
      </aside>

      <main>
        <header>
          <div>
            <p className="eyebrow">PORT OPERATIONS CONTROL TOWER</p>
            <h1>{state.port_name}</h1>
          </div>
          <div className="header-right">
            <span>{new Date(state.generated_at).toLocaleString()}</span>
            <div className={'system-state ' + (state.weather.restriction_active ? 'restricted' : 'normal')}>
              {state.weather.restriction_active ? 'MOVEMENT RESTRICTED' : 'OPERATIONS NORMAL'}
            </div>
          </div>
        </header>

        <section className="metrics metrics-six" id="overview">
          <Metric label="VESSELS IN PICTURE" value={state.metrics.vessels_in_port_picture} />
          <Metric label="BERTHS OCCUPIED" value={String(state.metrics.berths_occupied) + '/' + String(state.metrics.berths_total)} />
          <Metric label="PORT CALLS AT RISK" value={state.metrics.port_calls_at_risk} />
          <Metric label="ACTIVE INCIDENTS" value={state.metrics.active_incidents || 0} />
          <Metric label="BERTH CONFLICTS" value={state.metrics.berth_conflicts || 0} />
          <Metric label="MODELED EXPOSURE" value={usd(exposure)} />
        </section>

        <section className="grid">
          <div className="panel map-panel">
            <div className="panel-title">
              <div>
                <span>LIVE HARBOR</span>
                <b>Operational picture</b>
              </div>
              <small>vessels · berths · movement</small>
            </div>

            <HarborMap state={state} />

            <div className="map-overlay">
              <div><span>WIND</span><b>{state.weather.wind_knots} kt</b></div>
              <div><span>GUST</span><b>{state.weather.gust_knots} kt</b></div>
              <div><span>WAVE</span><b>{state.weather.wave_height_m} m</b></div>
              <div><span>TIDE</span><b>{state.weather.tide_m} m</b></div>
            </div>
          </div>

          <div className="panel right-stack">
            <div className="panel-title">
              <div>
                <span>BERTH BOARD</span>
                <b>Current allocation</b>
              </div>
            </div>

            <div className="berths">
              {state.berths.map(berth => (
                <div className="berth-row" key={berth.id}>
                  <div>
                    <b>{berth.name}</b>
                    <span>{berth.terminal}</span>
                  </div>
                  <span className={'berth-state ' + berth.status}>{berth.status}</span>
                </div>
              ))}
            </div>

            <div className="divider" />

            <div className="panel-title compact">
              <div>
                <span>LINK STATE</span>
                <b>{state.connectivity.primary_link}</b>
              </div>
              <RiskPill
                risk={
                  state.connectivity.mode === 'full'
                    ? 'low'
                    : state.connectivity.mode === 'offline_edge'
                      ? 'critical'
                      : 'high'
                }
              />
            </div>

            <div className="link-meta">
              <span>{state.connectivity.bandwidth_kbps.toLocaleString()} kbps</span>
              <span>{state.connectivity.queued_events} queued</span>
            </div>

            <div className="mode-buttons">
              {(['full', 'degraded', 'critical', 'offline_edge'] as LinkMode[]).map(mode => (
                <button
                  className={state.connectivity.mode === mode ? 'selected' : ''}
                  disabled={busy}
                  onClick={() => setMode(mode)}
                  key={mode}
                >
                  {mode.replace('_', ' ')}
                </button>
              ))}
            </div>
          </div>
        </section>

        <section className="panel timeline-panel" id="berth-schedule">
          <div className="panel-title">
            <div>
              <span>BERTH SCHEDULE</span>
              <b>16-hour allocation and conflict horizon</b>
            </div>
            <small>{state.metrics.berth_conflicts || 0} mechanical conflict(s)</small>
          </div>
          <BerthTimeline state={state} />
        </section>

        <section className="operations-grid" id="port-calls">
          <div className="panel">
            <div className="panel-title">
              <div>
                <span>PORT CALLS</span>
                <b>Critical path and cost exposure</b>
              </div>
              <small>dependency-aware</small>
            </div>
            <div className="calls">
              {state.port_calls.map(call => (
                <PortCallCard call={call} state={state} key={call.id} />
              ))}
            </div>
          </div>

          <div className="panel" id="incidents">
            <IncidentControls
              state={state}
              busy={busy}
              onInject={injectIncident}
              onReset={resetDemo}
            />
          </div>
        </section>

        <section className="panel feed-panel" id="ledger">
          <div className="panel-title">
            <div>
              <span>DURABLE OPERATIONS LEDGER</span>
              <b>Events and exceptions</b>
            </div>
            <small>append-only backend ledger</small>
          </div>
          <div className="event-feed event-feed-wide">
            {state.events.slice(0, 12).map(event => (
              <div className="event" key={event.id}>
                <i className={event.severity} />
                <div>
                  <b>{event.title}</b>
                  <span>{event.message}</span>
                </div>
                <time>{fmtTime(event.occurred_at)}</time>
              </div>
            ))}
          </div>
        </section>

        <footer>{state.data_disclaimer}</footer>
      </main>
    </div>
  )
}
