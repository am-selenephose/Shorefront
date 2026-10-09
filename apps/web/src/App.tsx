import { lazy, Suspense, useEffect, useMemo, useState } from 'react'
import { BerthTimeline } from './BerthTimeline'
import { DataSourcesPanel } from './DataSourcesPanel'
import { IncidentControls } from './IncidentControls'
import { RecoveryPanel } from './RecoveryPanel'
import { VesselExceptionsPanel } from './VesselExceptionsPanel'
import { ResourceBoard, ServiceChain } from './ServiceChain'
import { ArchitectureView, GuidedDemo, Pulse, RecoveryComparison } from './DecisionViews'
import { readJson, useHarborStream } from './useHarborStream'
import { isRecoveryProposal } from './runtimeValidation'
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

const HarborMap = lazy(() =>
  import('./HarborMap').then(module => ({ default: module.HarborMap })),
)

const workspaces = [
  ['pulse', 'Pulse', 'What needs attention now?'],
  ['plan', 'Plan', 'Plan the next move'],
  ['calls', 'Calls', 'Follow each port call'],
  ['exceptions', 'Exceptions', 'Understand what changed'],
  ['recovery', 'Recovery', 'Choose a recovery path'],
  ['evidence', 'Evidence', 'Inspect the operational record'],
] as const
function currentWorkspace() {
  const value = location.hash.slice(1)
  return value === 'control-tower' || workspaces.some(([id]) => id === value) ? value : 'pulse'
}


function storedOperatorToken() {
  try {
    // Do not silently adopt credentials saved under the retired product identity.
    sessionStorage.removeItem('portflow.operator_token')
    return sessionStorage.getItem('shorefront.operator_token') || ''
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
  const [theme, setTheme] = useState<'light' | 'dark'>(() =>
    document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light',
  )
  const { state, setState, online, error: connectionError, stale, retry } = useHarborStream()
  const [actionBusy, setBusy] = useState(false)
  const busy = actionBusy || stale || !online || !!connectionError
  const [workspace, setWorkspace] = useState(currentWorkspace)
  const [surface, setSurface] = useState<'operations' | 'demo' | 'architecture'>('operations')
  const [roleLens, setRoleLens] = useState('Berth Planner')
  const [authBusy, setAuthBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [operatorToken, setOperatorToken] = useState(storedOperatorToken)
  const [operatorIdentity, setOperatorIdentity] = useState<OperatorIdentity | null>(null)
  const [scenarios, setScenarios] = useState<ScenarioFixture[]>([])
  const [demoControls, setDemoControls] = useState(false)
  const [adapters, setAdapters] = useState<AdapterSnapshot[]>([])
  const [recoveryProposals, setRecoveryProposals] = useState<RecoveryProposal[]>([])
  const [recoveryStatus, setRecoveryStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [recoveryReceipts, setRecoveryReceipts] = useState<RecoveryReceipt[]>([])
  const [vesselExceptions, setVesselExceptions] = useState<VesselOperationalException[]>([])
  const [contingencyNotice, setContingencyNotice] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    void readJson<{ demo_controls_enabled: boolean }>('/api/v1/runtime/capabilities', controller.signal)
      .then(value => { if (!controller.signal.aborted) setDemoControls(value.demo_controls_enabled === true) })
      .catch(() => { if (!controller.signal.aborted) setDemoControls(false) })
    const changed = () => { setWorkspace(currentWorkspace()); setSurface('operations'); window.scrollTo(0, 0) }
    window.addEventListener('hashchange', changed)
    return () => {
      controller.abort()
      window.removeEventListener('hashchange', changed)
    }
  }, [])

  const visible = (...names: string[]) => surface === 'operations' && (workspace === 'control-tower' || names.includes(workspace))

  function toggleTheme() {
    const next = theme === 'dark' ? 'light' : 'dark'
    // Apply tokens before React updates the canvas; do not remount the workspace.
    document.documentElement.dataset.theme = next
    const meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')
    if (meta) meta.content = getComputedStyle(document.documentElement).getPropertyValue('--background').trim()
    try {
      localStorage.setItem('shorefront.theme', next)
    } catch {
      // The switch still works for this visit when persistence is unavailable.
    }
    setTheme(next)
  }

  useEffect(() => {
    fetch('/api/v1/scenarios')
      .then(response => response.json())
      .then(setScenarios)
      .catch(() => setScenarios([]))

    fetch('/api/v1/adapters')
      .then(response => response.json())
      .then(setAdapters)
      .catch(() => setAdapters([]))

  }, [])

  useEffect(() => {
    if (operatorToken) {
      void connectOperator(operatorToken)
    }
  }, [])

  useEffect(() => {
    if (!state) return
    const controller = new AbortController()

    setRecoveryStatus('loading')
    readJson<{ proposals: RecoveryProposal[] }>('/api/v1/recovery/proposals', controller.signal)
      .then(payload => {
        if (!controller.signal.aborted) {
          if (!Array.isArray(payload.proposals) || !payload.proposals.every(isRecoveryProposal)) throw new Error('Invalid proposal response')
          setRecoveryProposals(payload.proposals)
          setRecoveryStatus('ready')
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setRecoveryStatus('error')
      })

    return () => controller.abort()
  }, [
    state?.decision_revision,
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
    setRecoveryStatus('loading')
    try {
      const payload = await readJson<{ proposals: RecoveryProposal[] }>('/api/v1/recovery/proposals')
      if (!Array.isArray(payload.proposals) || !payload.proposals.every(isRecoveryProposal)) throw new Error('Invalid proposal response')
      setRecoveryProposals(payload.proposals)
      setRecoveryStatus('ready')
    } catch {
      setRecoveryStatus('error')
      return
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
        sessionStorage.setItem('shorefront.operator_token', token)
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
        sessionStorage.removeItem('shorefront.operator_token')
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
      sessionStorage.removeItem('shorefront.operator_token')
    } catch {
      // Ignore unavailable browser storage.
    }
  }

  async function runAction(action: () => Promise<void>) {
    if (stale || !online || connectionError) {
      setActionError('Refresh the operational picture before making a change.')
      return
    }
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
        Shorefront
        <span role="status">{connectionError || 'Loading shore operations picture...'}</span>
        {connectionError && <button onClick={retry}>Retry connection</button>}
      </div>
    )
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brandmark">S</div>
          <div>
            <b>Shorefront</b>
            <span>MARITIME · SHORE</span>
          </div>
        </div>

        <nav aria-label="Shorefront workspace">
          {workspaces.map(([id, label], index) => <a key={id} className={workspace === id ? 'active' : ''} aria-current={workspace === id ? 'page' : undefined} href={'#' + id} onClick={() => setSurface('operations')}><span className="nav-index" aria-hidden="true">0{index + 1}</span>{label}</a>)}
          <a href="#control-tower" className={workspace === 'control-tower' ? 'active' : ''} onClick={() => setSurface('operations')}>Full control tower</a>
        </nav>

        <div className="side-foot">
          <span className={online ? 'live-dot' : 'offline-dot'} />
          {stale ? 'STALE PICTURE' : online ? 'CONNECTED' : 'RECONNECTING'}
          <small>Persistent synthetic operations</small>
        </div>
      </aside>

      <main>
        <header>
          <div>
            <p className="eyebrow">SHOREFRONT · OPERATIONS CONTROL TOWER</p>
            <h1>{surface === 'demo' ? 'Guided demonstration' : surface === 'architecture' ? 'The decision infrastructure' : workspaces.find(([id]) => id === workspace)?.[2] || state.port_name}</h1>
          </div>
          <div className="header-right">
            <span>{new Date(state.generated_at).toLocaleString()}</span>
            <div className="header-controls">
              <button className="theme-toggle" type="button" aria-label="Dark mode" aria-pressed={theme === 'dark'} onClick={toggleTheme}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M20.9 13.1A9 9 0 0 1 10.9 3.1a9 9 0 1 0 10 10Z" />
                </svg>
                <span>Dark mode</span>
                <span className="theme-toggle-state" aria-hidden="true">{theme === 'dark' ? 'ON' : 'OFF'}</span>
              </button>
              <div className={'system-state ' + (stale || !online || connectionError || state.weather.restriction_active ? 'restricted' : 'normal')}>
                {connectionError ? 'DATA ERROR · READ ONLY' : stale ? 'STALE DATA · READ ONLY' : !online ? 'DISCONNECTED · READ ONLY' : state.weather.restriction_active ? 'MOVEMENT RESTRICTED' : 'MODELED OPERATIONS'}
              </div>
            </div>
          </div>
        </header>

        <div className="workspace-toolbar">
          <div className="surface-switch" aria-label="Product mode">{(['operations', 'demo', 'architecture'] as const).map(mode => <button type="button" key={mode} aria-pressed={surface === mode} onClick={() => setSurface(mode)}>{mode === 'demo' ? 'Guided demo' : mode === 'operations' ? 'Operations' : 'Architecture'}</button>)}</div>
          <label className="role-lens">Role lens<select value={roleLens} onChange={event => setRoleLens(event.target.value)}>{['Berth Planner', 'Harbor Master', 'Terminal Ops', 'Carrier-Agent', 'Viewer'].map(role => <option key={role}>{role}</option>)}</select><small>View only · does not grant authority</small></label>
        </div>

        {(stale || !online || connectionError) && <div className="connection-warning" role="status">{connectionError || 'The operational stream is not current. Last verified picture retained; changes are disabled.'}<button onClick={retry}>Retry connection</button></div>}

        <div className="shorefront-context-strip" aria-label="Shorefront authority boundary">
          <span>SHORE COORDINATION</span>
          <span>PRIVACY-MINIMIZED VESSEL EVENTS</span>
          <span>HUMAN APPROVAL</span>
          <span className="locked">NO VESSEL ACTUATION</span>
        </div>

        {actionError && <div className="action-error">{actionError}</div>}

        {surface === 'demo' && <GuidedDemo />}
        {surface === 'architecture' && <ArchitectureView />}
        {surface === 'operations' && workspace === 'pulse' && <Pulse state={state} role={roleLens} onDemo={() => setSurface('demo')} />}

        {visible('plan') && <section className="metrics metrics-seven" id="overview">
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
        </section>}

        {visible('plan') && <section className="grid">
          <div className="panel map-panel">
            <div className="panel-title">
              <div>
                <span>LIVE HARBOR</span>
                <b>Operational picture</b>
              </div>
              <small>vessels · berths · movement</small>
            </div>

            <Suspense fallback={<div className="harbor-map map-loading">Loading geospatial layer...</div>}>
              <HarborMap state={state} theme={theme} />
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

            {demoControls && <div className="mode-buttons">
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
            </div>}
          </div>
        </section>}

        {visible('plan') && <section className="panel timeline-panel" id="berth-schedule">
          <div className="panel-title">
            <div>
              <span>BERTH SCHEDULE</span>
              <b>16-hour allocation and conflict horizon</b>
            </div>
            <small>{state.metrics.berth_conflicts || 0} mechanical conflict(s)</small>
          </div>
          <BerthTimeline state={state} />
        </section>}

        {visible('calls', 'exceptions', 'plan') && <section className={'operations-grid ' + (workspace !== 'control-tower' ? 'focused-grid' : '')} id="port-calls">
          {visible('calls') && <div className="panel">
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
          </div>}

          <div className="side-ops-stack">
            {visible('exceptions') && <div className="panel" id="incidents">
              <IncidentControls
                state={state}
                demoEnabled={demoControls}
                scenarios={scenarios}
                busy={busy}
                onRunScenario={runScenario}
                onReset={resetDemo}
              />
            </div>}

            {visible('plan') && <div className="panel" id="resources">
              <div className="panel-title">
                <div>
                  <span>SERVICE RESOURCES</span>
                  <b>Pilots, tugs, berths, cranes, customs</b>
                </div>
                <small>{state.metrics.blocked_services || 0} blocked</small>
              </div>
              <ResourceBoard state={state} />
            </div>}
          </div>
        </section>}

        {visible('evidence') && <section className="panel data-feeds-shell" id="data-feeds">
          <DataSourcesPanel
            current={state.data_sources || []}
            adapters={adapters}
            identity={operatorIdentity}
            busy={busy}
            onIngest={ingestAdapter}
          />
        </section>}

        {surface === 'operations' && workspace === 'recovery' && <RecoveryComparison revision={state.decision_revision} />}
        {visible('recovery', 'evidence', 'exceptions') && <section className="panel recovery-shell" id="recovery">
          <RecoveryPanel
            proposals={recoveryProposals}
            queryStatus={recoveryStatus}
            receipts={recoveryReceipts}
            identity={operatorIdentity}
            busy={busy}
            authBusy={authBusy}
            contingencyNotice={contingencyNotice}
            onApply={applyRecovery}
            onRefresh={() => loadRecovery()}
            onConnect={connectOperator}
            onDisconnect={disconnectOperator}
          />
        </section>}

        {visible('exceptions') && <section className="panel vessel-exceptions-shell" id="vessel-exceptions">
          <VesselExceptionsPanel
            exceptions={vesselExceptions}
            identity={operatorIdentity}
            busy={busy || authBusy}
            onRefresh={loadVesselExceptions}
          />
        </section>}

        {visible('evidence') && <section className="panel feed-panel" id="ledger">
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
        </section>}

        <footer>{state.data_disclaimer}</footer>
      </main>
    </div>
  )
}
