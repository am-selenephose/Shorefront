import type { HarborState, ScenarioFixture } from './types'

export function IncidentControls({
  state,
  scenarios,
  busy,
  onRunScenario,
  onReset,
}: {
  state: HarborState
  scenarios: ScenarioFixture[]
  busy: boolean
  onRunScenario: (scenarioId: string) => Promise<void>
  onReset: () => Promise<void>
}) {
  const active = state.incidents.filter(item => item.status === 'active')

  return (
    <div className="scenario-lab">
      <div className="scenario-head">
        <div>
          <span>SCENARIO LAB</span>
          <b>Deterministic operational fixtures</b>
        </div>
        <button disabled={busy} onClick={onReset}>Reset demo</button>
      </div>

      <div className="scenario-grid">
        {scenarios.length === 0 && (
          <p className="scenario-empty">Loading canonical scenario fixtures...</p>
        )}
        {scenarios.map(item => (
          <button
            key={item.id}
            disabled={busy}
            onClick={() => onRunScenario(item.id)}
          >
            <b>{item.title}</b>
            <span>{item.description}</span>
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
