import { useEffect, useState } from 'react'
import { BerthTimeline } from './BerthTimeline'
import { ServiceChain } from './ServiceChain'
import { readJson } from './useHarborStream'
import type { HarborState } from './types'
import { isComparison, isStory, type Comparison, type Story } from './runtimeValidation'
const money = (amount: number) => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(amount)
const delay = (state: HarborState) => state.port_calls.reduce((sum, call) => sum + Math.max(call.delay_minutes, 0), 0)

export function EvidenceDisclosure({ state, reasons = [] }: { state: HarborState; reasons?: string[] }) {
  return <details className="evidence-disclosure">
    <summary>Why / Data / Age / Owner</summary>
    <p>Owner: not assigned. Role lenses are presentation filters, not responsibility assignments.</p>
    {reasons.map(reason => <p key={reason}>{reason}</p>)}
    <ul>{state.data_sources.map(source => <li key={source.source_id}>
      <strong>{source.domain.replaceAll('_', ' ')}</strong> · {source.provider} · {source.mode} · {source.health}
      <span>Observed {new Date(source.observed_at).toLocaleString()} · received {new Date(source.received_at).toLocaleString()} · snapshot age {source.freshness_seconds}s</span>
      <code>{source.source_id}</code>
    </li>)}</ul>
    <p>Evidence health is not a calibrated probability of operational success.</p>
  </details>
}

export function Pulse({ state, role, onDemo }: { state: HarborState; role: string; onDemo: () => void }) {
  const atRisk = state.port_calls.filter(call => call.delay_minutes > 0 || ['high', 'critical'].includes(call.risk))
  const resourceFocus = role === 'Harbor Master' || role === 'Terminal Ops'
  const ordered = [...atRisk].sort((a, b) => resourceFocus
    ? state.service_steps.filter(s => s.port_call_id === b.id && s.state === 'blocked').length - state.service_steps.filter(s => s.port_call_id === a.id && s.state === 'blocked').length
    : b.delay_minutes - a.delay_minutes)
  return <section className="pulse-workspace" aria-label="Operational attention">
    <div className="workspace-section-title"><h2>Attention queue <span>{ordered.length}</span></h2><p>{role} lens · {resourceFocus ? 'blocked dependencies first' : 'largest delay first'}</p></div>
    <div className="attention-grid">{ordered.map(call => {
      const vessel = state.vessels.find(item => item.id === call.vessel_id)
      const blocked = state.service_steps.filter(step => step.port_call_id === call.id && step.state === 'blocked').length
      return <article className="attention-card" key={call.id}>
        <div className="attention-top"><span className={'risk ' + call.risk}>{call.risk.toUpperCase()}</span><span>{call.berth_id}</span></div>
        <h3>{vessel?.name || call.id}</h3><p>{blocked ? `${blocked} blocked services require review` : 'Schedule impact needs review'}</p>
        <div className="attention-numbers"><strong>+{call.delay_minutes}<small>min delay</small></strong><strong>{money(call.estimated_cost_exposure_usd)}<small>modeled exposure</small></strong></div>
        <p className="assignment-note">Unassigned · suggested review: {blocked ? 'Harbor Master' : 'Berth Planner'}</p>
        <a className="workspace-link" href="#recovery">Review recovery →</a>
        <EvidenceDisclosure state={state} reasons={state.incidents.filter(i => i.status === 'active' && i.target_port_call_id === call.id).map(i => `${i.id}: ${i.title}`)} />
      </article>
    })}</div>
    {!ordered.length && <div className="workspace-empty"><h3>No delayed or high-risk calls in this snapshot.</h3><p>This does not certify port safety. Check source freshness and unresolved exceptions.</p></div>}
    <div className="pulse-intro">
      <div><p className="eyebrow">OBSERVE → UNDERSTAND → DECIDE</p><h2>Know what changed.<br />Choose what happens next.</h2>
        <p>A shared operational picture. Explainable choices. People in control.</p></div>
      <div className="demo-invitation"><span>EXPLORE THE DECISION LOOP</span><h3>One tug. A chain of consequences.</h3>
        <p>Follow an isolated disruption from first signal to a simulated recovery receipt.</p><button onClick={onDemo}>Explore a disruption ↗</button></div>
    </div>
  </section>
}

export function ComparisonView({ data }: { data: Comparison }) {
  const columns = [{ label: 'Current', state: data.current, proposal: null }, ...data.options.map((option, index) => ({ label: `Option ${String.fromCharCode(65 + index)}`, state: option.harbor, proposal: option.proposal }))]
  return <section className="recovery-comparison" aria-label="Recovery comparison">
    <div className="workspace-section-title"><h2>Compare before committing</h2><span>READ-ONLY PROJECTIONS</span></div>
    <div className="comparison-grid">{columns.map(column => <article className="comparison-column" key={column.label}>
      <p className="eyebrow">{column.label}</p><h3>{column.proposal?.title || 'Keep current allocation'}</h3>
      <div className="comparison-numbers"><b>{delay(column.state)}m <small>total delay</small></b><b>{column.state.metrics.berth_conflicts} <small>conflicts</small></b><b>{column.state.metrics.blocked_services} <small>blocked</small></b></div>
      {column.proposal && <p>{delay(data.current) - column.proposal.projected_total_delay_minutes}m modeled delay reduction · evidence {column.proposal.decision_confidence}</p>}
      <div className="comparison-timeline"><BerthTimeline state={column.state} /></div>
      <EvidenceDisclosure state={data.current} reasons={column.proposal?.rationale || ['Current observed/modelled allocation; no action applied.']} />
    </article>)}</div>
    {!data.options.length && <p>No recovery options are available for this snapshot.</p>}
    <details className="evidence-disclosure"><summary>Model assumptions</summary><p>{data.model_notice}</p><p>Comparison is not a reservation or an approval. Recalculate before an operational decision.</p></details>
  </section>
}

export function RecoveryComparison({ revision }: { revision: string }) {
  const [data, setData] = useState<Comparison | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setData(null); setError('')
    void readJson<unknown>('/api/v1/recovery/comparison', controller.signal).then(value => {
      if (!isComparison(value)) throw new Error('Invalid comparison response')
      if (!controller.signal.aborted) setData(value)
    }).catch(() => { if (!controller.signal.aborted) setError('Comparison unavailable. No operational change was made.') })
    return () => controller.abort()
  }, [revision, attempt])
  if (error) return <div role="alert" className="workspace-empty">{error} <button onClick={() => setAttempt(x => x + 1)}>Retry comparison</button></div>
  return data ? <ComparisonView data={data} /> : <p role="status">Calculating recovery comparison…</p>
}

export function GuidedDemo() {
  const [story, setStory] = useState<Story | null>(null)
  const [step, setStep] = useState(0)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setError(''); setStory(null); setStep(0)
    void readJson<unknown>('/api/v1/demo/story', controller.signal).then(value => {
      if (!isStory(value)) throw new Error('Invalid story response')
      if (!controller.signal.aborted) setStory(value)
    }).catch(() => { if (!controller.signal.aborted) setError('The isolated demonstration could not load.') })
    return () => controller.abort()
  }, [attempt])
  if (error) return <div role="alert" className="workspace-empty">{error} <button onClick={() => setAttempt(x => x + 1)}>Retry demo</button></div>
  if (!story) return <p role="status">Building an isolated scenario with the recovery engine…</p>
  const current = step === 0 ? story.baseline : step === 3 ? story.recovered : story.disrupted
  const call = current.port_calls.find(item => item.id === 'pc-aurora')!
  return <section className="guided-story">
    <div className="demo-boundary">ISOLATED SYNTHETIC DEMO · no operational writes · no vessel actuation</div>
    <ol className="story-steps" aria-label="Demonstration progress">{['Observe', 'Disrupt', 'Compare', 'Record'].map((label, index) => <li key={label} aria-current={step === index ? 'step' : undefined}><span>0{index + 1}</span>{label}</li>)}</ol>
    <h2>{['A disruption. A decision. A record.', 'Tug 14 is unavailable', 'Choose with the consequences in view', 'An inspectable decision record'][step]}</h2>
    <p className="story-lede">{['Begin with a clean synthetic harbor. Follow the same engine used by the operational recovery workspace.', 'The engine propagates the resource failure through dependent services. The figures below are computed, not scripted marketing numbers.', 'Compare independent branches. Looking at an option does not change any operational state.', 'This is a simulated receipt produced by the engine. It is not a real operator approval or evidence that a vessel executed a command.'][step]}</p>
    <div className="story-metrics"><div><strong>{current.port_calls.length}</strong><span>port calls</span></div><div><strong>{delay(current)}m</strong><span>total modeled delay</span></div><div><strong>{current.metrics.blocked_services}</strong><span>blocked services</span></div><div><strong>{current.metrics.berth_conflicts}</strong><span>berth conflicts</span></div></div>
    {step !== 2 && <div className="panel"><h3>MSC Aurora · service dependencies</h3><ServiceChain call={call} state={current} /></div>}
    {step === 2 && <ComparisonView data={story.comparison} />}
    {step === 3 && <div className="decision-receipt"><h3>Simulated receipt · not an operational approval</h3><dl><dt>Actor</dt><dd>{story.receipt.approved_by}</dd><dt>Proposal</dt><dd>{story.receipt.proposal_id}</dd><dt>State fingerprint</dt><dd><code>{story.receipt.state_fingerprint}</code></dd><dt>Resulting modeled delay</dt><dd>{story.receipt.resulting_total_delay_minutes} minutes</dd></dl></div>}
    <div className="story-actions">{step > 0 && <button onClick={() => setStep(step - 1)}>Back one step</button>}{step < 3 ? <button onClick={() => setStep(step + 1)}>{['Introduce tug disruption', 'Compare recovery options', 'Simulate approval of Option A'][step]}</button> : <button onClick={() => setStep(0)}>Restart demonstration</button>}</div>
    <p>No autoplay or forced timing. Move through the story at your own pace.</p>
  </section>
}

export function ArchitectureView() {
  return <section className="architecture-view"><h2>Inside Shorefront</h2><p className="story-lede">An operational decision and evidence layer. Existing systems keep their authority; the people accountable for operations keep control.</p>
    <div className="architecture-chain">{['Signals', 'Harbor state', 'Dependencies', 'Recovery options', 'Human approval', 'Evidence'].map((label, i) => <div key={label}><span>0{i + 1}</span><h3>{label}</h3></div>)}</div>
    <div className="architecture-columns"><article className="panel"><h3>Implemented building blocks</h3><ul><li>React / TypeScript workspace and WebSocket snapshots.</li><li>FastAPI domain model and deterministic recovery simulation.</li><li>SQLite / PostgreSQL storage, proposals and identity-bound receipts.</li><li>Source provenance and freshness warnings.</li><li>Authenticated recovery approval and stale-proposal checks.</li><li>Vessel-scoped normalized event intake with advisory-only coordination.</li><li>Isolated synthetic story and read-only recovery comparison.</li></ul></article>
    <article className="panel"><h3>Not yet implemented</h3><ul><li>Complete transactional operational command boundary.</li><li>Bitemporal historical replay and historical counterfactuals.</li><li>DCSA conformance and experimental S-211 mapping.</li><li>Organisation-scoped identity and projection policies.</li><li>Real downstream transport delivery acknowledgements.</li><li>Commercial obligations, validated integrations and outcome calibration.</li></ul></article></div>
    <div className="demo-boundary">Prototype evidence is not a production-readiness or standards-conformance certificate.</div>
  </section>
}
