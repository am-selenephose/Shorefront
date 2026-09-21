import type { HarborState, IncidentType } from './types'

type Inject = (incidentType: IncidentType, target?: string, impact?: number) => Promise<void>

const scenarios: Array<{ type: IncidentType; label: string; detail: string; target?: string; impact?: number }> = [
  { type: 'pilot_delay', label: 'Pilot +25m', detail: 'Shift Aurora critical path', target: 'pc-aurora', impact: 25 },
  { type: 'tug_unavailable', label: 'Tug unavailable', detail: 'Delay maneuver + berth', target: 'pc-aurora', impact: 40 },
  { type: 'berth_overrun', label: 'Berth overrun', detail: 'Create downstream B07 conflict', target: 'pc-glory', impact: 90 },
  { type: 'wind_restriction', label: 'Wind restriction', detail: 'Hold inbound pilot movements', impact: 30 },
  { type: 'connectivity_loss', label: 'Lose control link', detail: 'Switch to edge-only queueing' },
]

export function IncidentControls({
  state,
  busy,
  onInject,
  onReset,
}: {
  state: HarborState
  busy: boolean
  onInject: Inject
  onReset: () => Promise<void>
}) {
  const active = state.incidents.filter(item => item.status === 'active')

  return (
    <div className="scenario-lab">
      <div className="scenario-head">
        <div>
          <span>SCENARIO LAB</span>
          <b>Inject operational failures</b>
        </div>
        <button disabled={busy} onClick={onReset}>Reset demo</button>
      </div>

      <div className="scenario-grid">
        {scenarios.map(item => (
          <button
            key={item.type}
            disabled={busy}
            onClick={() => onInject(item.type, item.target, item.impact)}
          >
            <b>{item.label}</b>
            <span>{item.detail}</span>
          </button>
        ))}
      </div>

      <div className="active-incidents">
        <span className="section-kicker">ACTIVE INCIDENTS · {active.length}</span>
        {active.length === 0 && <p>No active operational exceptions.</p>}
        {active.slice(0, 4).map(item => (
          <div className="incident-row" key={item.id}>
            <i className={item.severity} />
            <div>
              <b>{item.title}</b>
              <span>{item.details}</span>
            </div>
            <small>+{item.impact_minutes}m</small>
          </div>
        ))}
      </div>
    </div>
  )
}
