import { lazy, Suspense, useEffect, useMemo, useState } from 'react'
import { BerthTimeline } from './BerthTimeline'
import { DataSourcesPanel } from './DataSourcesPanel'
import { IncidentControls } from './IncidentControls'
import { RecoveryPanel } from './RecoveryPanel'
import { VesselExceptionsPanel } from './VesselExceptionsPanel'
import { ResourceBoard, ServiceChain } from './ServiceChain'
import type {
  AdapterSnapshot,
  HarborState,
  LinkMode,
  OperatorIdentity,
  PortCall,
  RecoveryContingency,
  RecoveryProposal,
  RecoveryReceipt,
  VesselOperationalException,
  ScenarioFixture,
} from './types'
import './styles.css'

const HarborMap = lazy(() =>
  import('./HarborMap').then(module => ({ default: module.HarborMap })),
)


function storedOperatorToken() {
  try {
    return sessionStorage.getItem('portflow.operator_token') || ''
  } catch {
    return ''
  }
}


const fmtTime = (value: string) =>
  new Intl.DateTimeFormat('en', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(value))

const usd = (value: number) =>
  new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(value)


function Metric({
  label,
  value,
  detail,
}: {
  label: string
  value: string | number
  detail?: string
}) {
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

      <ServiceChain call={call} state={state} />
    </div>
  )
}


export default function App() {
  const [state, setState] = useState<HarborState | null>(null)
  const [online, setOnline] = useState(false)
  const [busy, setBusy] = useState(false)
  const [authBusy, setAuthBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [operatorToken, setOperatorToken] = useState(storedOperatorToken)
  const [operatorIdentity, setOperatorIdentity] = useState<OperatorIdentity | null>(null)
  const [scenarios, setScenarios] = useState<ScenarioFixture[]>([])
  const [adapters, setAdapters] = useState<AdapterSnapshot[]>([])
  const [recoveryProposals, setRecoveryProposals] = useState<RecoveryProposal[]>([])
  const [recoveryReceipts, setRecoveryReceipts] = useState<RecoveryReceipt[]>([])
  const [vesselExceptions, setVesselExceptions] = useState<VesselOperationalException[]>([])
  const [contingencyNotice, setContingencyNotice] = useState<string | null>(null)

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

    fetch('/api/v1/scenarios')
      .then(response => response.json())
      .then(setScenarios)
      .catch(() => setScenarios([]))

    fetch('/api/v1/adapters')
      .then(response => response.json())
      .then(setAdapters)
      .catch(() => setAdapters([]))

    connect()

    return () => {
      dead = true
      ws?.close()
    }
  }, [])

  useEffect(() => {
    if (operatorToken) {
      void connectOperator(operatorToken)
    }
  }, [])

  useEffect(() => {
    if (!state) return
    const controller = new AbortController()

    fetch('/api/v1/recovery/proposals', { signal: controller.signal })
      .then(response => {
        if (!response.ok) throw new Error('Recovery query failed')
        return response.json()
      })
      .then(payload => setRecoveryProposals(payload.proposals || []))
      .catch(error => {
        if (error?.name !== 'AbortError') setRecoveryProposals([])
      })

    return () => controller.abort()
  }, [
    state?.metrics.active_incidents,
    state?.metrics.berth_conflicts,
    state?.metrics.blocked_services,
    state?.metrics.delayed_services,
  ])

  const exposure = useMemo(
    () => state?.port_calls.reduce(
      (sum, call) => sum + call.estimated_cost_exposure_usd,
      0,
    ) ?? 0,
    [state],
  )

  async function refreshHarbor() {
    const response = await fetch('/api/v1/harbor')
    if (response.ok) setState(await response.json())
  }

  async function loadRecovery(token = operatorToken) {
    setContingencyNotice(null)
    const proposalResponse = await fetch('/api/v1/recovery/proposals')
    if (proposalResponse.ok) {
      const payload = await proposalResponse.json()
      setRecoveryProposals(payload.proposals || [])
    }

    if (!token) {
      setRecoveryReceipts([])
      return
    }

    const receiptResponse = await fetch('/api/v1/recovery/receipts?limit=20', {
      headers: { Authorization: 'Bearer ' + token },
    })

    if (receiptResponse.ok) {
      setRecoveryReceipts(await receiptResponse.json())
    } else if (receiptResponse.status === 401) {
      setRecoveryReceipts([])
    }
  }

  async function loadVesselExceptions(token = operatorToken) {
    if (!token) {
      setVesselExceptions([])
      return
    }

    const response = await fetch('/api/v1/operations/vessel-exceptions?limit=100', {
      headers: { Authorization: 'Bearer ' + token },
    })

    if (response.ok) {
      const payload = await response.json()
      setVesselExceptions(payload.exceptions || [])
      return
    }

    if (response.status === 401) {
      setVesselExceptions([])
      return
    }

    throw new Error('Vessel exception query failed')
  }

  async function connectOperator(token: string): Promise<boolean> {
    setAuthBusy(true)
    setActionError(null)
    try {
      const response = await fetch('/api/v1/auth/me', {
        headers: { Authorization: 'Bearer ' + token },
      })
      if (!response.ok) {
        throw new Error(
          response.status === 401
            ? 'Operator credential was not accepted.'
            : await response.text(),
        )
      }

      const identity = await response.json() as OperatorIdentity
      setOperatorToken(token)
      setOperatorIdentity(identity)
      try {
        sessionStorage.setItem('portflow.operator_token', token)
      } catch {
        // Session still works even if browser storage is unavailable.
      }
      await Promise.all([
        loadRecovery(token),
        loadVesselExceptions(token),
      ])
      return true
    } catch (error) {
      setOperatorIdentity(null)
      setOperatorToken('')
      setRecoveryReceipts([])
      setVesselExceptions([])
      try {
        sessionStorage.removeItem('portflow.operator_token')
      } catch {
        // Ignore unavailable browser storage.
      }
      setActionError(error instanceof Error ? error.message : 'Operator verification failed')
      return false
    } finally {
      setAuthBusy(false)
    }
  }

  function disconnectOperator() {
    setOperatorIdentity(null)
    setOperatorToken('')
    setRecoveryReceipts([])
    setVesselExceptions([])
    setActionError(null)
    try {
      sessionStorage.removeItem('portflow.operator_token')
    } catch {
      // Ignore unavailable browser storage.
    }
  }

  async function runAction(action: () => Promise<void>) {
    setBusy(true)
    setActionError(null)
    try {
      await action()
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'Operation failed')
    } finally {
      setBusy(false)
    }
  }

  async function setMode(mode: LinkMode) {
    await runAction(async () => {
      const response = await fetch('/api/v1/connectivity', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ mode }),
      })
      if (!response.ok) throw new Error(await response.text())
      await refreshHarbor()
      await loadRecovery()
    })
  }

  async function runScenario(scenarioId: string) {
    await runAction(async () => {
      const response = await fetch('/api/v1/scenarios/' + scenarioId + '/run', {
        method: 'POST',
      })
      if (!response.ok) throw new Error(await response.text())

      const payload = await response.json()
      setState(payload.harbor)
      setRecoveryProposals(payload.recovery_proposals || [])
      setRecoveryReceipts([])
      setContingencyNotice(null)
    })
  }

  async function refreshAdapters() {
    const response = await fetch('/api/v1/adapters')
    if (response.ok) setAdapters(await response.json())
  }

  async function ingestAdapter(adapterId: string) {
    await runAction(async () => {
      if (!operatorToken || !operatorIdentity) {
        throw new Error('Authenticate an operator or supervisor before ingesting a recorded feed.')
      }
      if (!['operator', 'supervisor'].includes(operatorIdentity.role)) {
        throw new Error('Current session is read-only and cannot ingest operational data.')
      }

      const response = await fetch('/api/v1/adapters/' + adapterId + '/ingest', {
        method: 'POST',
        headers: { Authorization: 'Bearer ' + operatorToken },
      })
      if (!response.ok) {
        if (response.status === 401) disconnectOperator()
        throw new Error(await response.text())
      }

      const payload = await response.json()
      setState(payload.harbor)
      await refreshAdapters()
      await loadRecovery(operatorToken)
    })
  }

  async function applyRecovery(proposalId: string) {
    await runAction(async () => {
      if (!operatorToken || !operatorIdentity) {
        throw new Error('Authenticate an operator or supervisor before applying a recovery plan.')
      }
      if (!['operator', 'supervisor'].includes(operatorIdentity.role)) {
        throw new Error('Current session is read-only and cannot approve recovery actions.')
      }

      const response = await fetch(
        '/api/v1/recovery/proposals/' + proposalId + '/apply',
        {
          method: 'POST',
          headers: { Authorization: 'Bearer ' + operatorToken },
        },
      )
      if (!response.ok) {
        if (response.status === 401) {
          disconnectOperator()
          throw new Error(await response.text())
        }

        if (response.status === 409) {
          const payload = await response.json()
          const detail = payload?.detail as (
            (RecoveryContingency & { code?: string }) | undefined
          )
          if (detail?.code === 'recovery_proposal_stale') {
            setRecoveryProposals(detail.replacement_proposals || [])
            const unavailable = detail.unavailable_resource_ids.length > 0
              ? ' Unavailable: ' + detail.unavailable_resource_ids.join(', ') + '.'
              : ''
            setContingencyNotice(
              'CONTINGENCY · Previous recovery plan is stale.' +
              unavailable +
              ' Ranked replacements loaded; a new explicit approval is required.',
            )
            await refreshHarbor()
            return
          }
        }

        throw new Error(await response.text())
      }
      setContingencyNotice(null)
      await refreshHarbor()
      await loadRecovery(operatorToken)
    })
  }

  async function resetDemo() {
    await runAction(async () => {
      const response = await fetch('/api/v1/demo/reset', { method: 'POST' })
      if (!response.ok) throw new Error(await response.text())
      setState(await response.json())
      setRecoveryProposals([])
      setRecoveryReceipts([])
      setContingencyNotice(null)
    })
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
          <a href="#resources">Resources</a>
          <a href="#data-feeds">Data Feeds</a>
          <a href="#recovery">Recovery Plans</a>
          <a href="#vessel-exceptions">Vessel Exceptions</a>
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

        {actionError && <div className="action-error">{actionError}</div>}

        <section className="metrics metrics-seven" id="overview">
          <Metric label="VESSELS IN PICTURE" value={state.metrics.vessels_in_port_picture} />
          <Metric
            label="BERTHS OCCUPIED"
            value={String(state.metrics.berths_occupied) + '/' + String(state.metrics.berths_total)}
          />
          <Metric label="PORT CALLS AT RISK" value={state.metrics.port_calls_at_risk} />
          <Metric label="ACTIVE INCIDENTS" value={state.metrics.active_incidents || 0} />
          <Metric label="BERTH CONFLICTS" value={state.metrics.berth_conflicts || 0} />
          <Metric
            label="SERVICE BLOCKS"
            value={state.metrics.blocked_services || 0}
            detail={(state.metrics.delayed_services || 0) + ' delayed'}
          />
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

            <Suspense fallback={<div className="harbor-map map-loading">Loading geospatial layer...</div>}>
              <HarborMap state={state} />
            </Suspense>

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

          <div className="side-ops-stack">
            <div className="panel" id="incidents">
              <IncidentControls
                state={state}
                scenarios={scenarios}
                busy={busy}
                onRunScenario={runScenario}
                onReset={resetDemo}
              />
            </div>

            <div className="panel" id="resources">
              <div className="panel-title">
                <div>
                  <span>SERVICE RESOURCES</span>
                  <b>Pilots, tugs, berths, cranes, customs</b>
                </div>
                <small>{state.metrics.blocked_services || 0} blocked</small>
              </div>
              <ResourceBoard state={state} />
            </div>
          </div>
        </section>

        <section className="panel data-feeds-shell" id="data-feeds">
          <DataSourcesPanel
            current={state.data_sources || []}
            adapters={adapters}
            identity={operatorIdentity}
            busy={busy}
            onIngest={ingestAdapter}
          />
        </section>

        <section className="panel recovery-shell" id="recovery">
          <RecoveryPanel
            proposals={recoveryProposals}
            receipts={recoveryReceipts}
            identity={operatorIdentity}
            busy={busy}
            authBusy={authBusy}
            contingencyNotice={contingencyNotice}
            onApply={applyRecovery}
            onRefresh={loadRecovery}
            onConnect={connectOperator}
            onDisconnect={disconnectOperator}
          />
        </section>

        <section className="panel vessel-exceptions-shell" id="vessel-exceptions">
          <VesselExceptionsPanel
            exceptions={vesselExceptions}
            identity={operatorIdentity}
            busy={busy || authBusy}
            onRefresh={loadVesselExceptions}
          />
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
