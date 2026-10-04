import {dateLabel, recordName, type Fact, type User, type Workspace} from './productClient'

const byKind = (records: Fact[], kind: string) => records.filter(record => record.kind === kind)
const find = (records: Fact[], kind: string, id: unknown) => records.find(record => record.kind === kind && record.record_id === id)
const text = (value: unknown) => value == null ? '' : String(value)
const when = (value: unknown) => value ? new Date(String(value)) : null
const now = () => new Date()
const due = (record: Fact) => when(record.payload.due_at)
const unresolvedIncident = (record: Fact) => record.kind === 'incident' && record.payload.status !== 'resolved'
const unfinishedTask = (record: Fact) => record.kind === 'task' && record.payload.status !== 'done'
const unavailableResource = (record: Fact) => record.kind === 'resource' && record.payload.available === false
const incompleteHandoff = (record: Fact) => record.kind === 'handoff' && record.payload.status !== 'acknowledged'
const activeObligation = (record: Fact) => record.kind === 'obligation' && !['completed','cancelled'].includes(text(record.payload.status))
const openCommitment = (record: Fact) => record.kind === 'commitment' && !['fulfilled','cancelled','declined'].includes(text(record.payload.status))

function severityClass(value: unknown) {
  const level = text(value)
  return ['critical','high','medium','low'].includes(level) ? level : 'neutral'
}

export function OperationalPulse({workspace, team}: {workspace: Workspace; team: User[]}) {
  const {records, attention} = workspace
  const calls = byKind(records, 'call')
  const incidents = records.filter(unresolvedIncident)
  const resources = records.filter(unavailableResource)
  const obligations = records.filter(activeObligation)
  const handoffs = records.filter(incompleteHandoff)
  const port = byKind(records, 'port')[0]
  const queue = [
    ...incidents.map(record => ({record, type:'INCIDENT', detail:text(record.payload.detail) || 'Operational incident requires review'})),
    ...attention.map(record => ({record, type:'TASK', detail:`Due ${dateLabel(text(record.payload.due_at))} · ${record.payload.assignee_id ? `Assigned to ${team.find(member => member.id === record.payload.assignee_id)?.name ?? record.payload.assignee_id}` : 'Unassigned'}`})),
    ...handoffs.map(record => ({record, type:'HANDOFF', detail:`${text(record.payload.status).toUpperCase()} · recipient confirmation incomplete`})),
    ...obligations.map(record => ({record, type:'OBLIGATION', detail:`${text(record.payload.status).toUpperCase()} · due ${dateLabel(text(record.payload.due_at))}`})),
    ...resources.map(record => ({record, type:'RESOURCE', detail:'Recorded unavailable'})),
  ].slice(0, 12)
  return <div className="ops-workspace" data-product-workspace="pulse">
    <section className="ops-hero"><div><span className="product-index">PULSE / OPERATIONAL CONTROL</span><h1>Your port. Your operational record.</h1><p>{port ? `${recordName(port)} — real records, preserved sources and accountable actions.` : 'Start with your port. Shorefront will not fill the gaps with invented operations.'}</p></div><div className="ops-live-badge">RECORDED FACTS<br/><b>{records.length}</b></div></section>
    <div className="ops-kpis">
      <article><span>ACTIVE CALLS</span><strong>{calls.filter(call => !['departed','cancelled'].includes(text(call.payload.status))).length}</strong><small>{calls.length} recorded</small></article>
      <article className={incidents.length ? 'critical' : 'healthy'}><span>OPEN INCIDENTS</span><strong>{incidents.length}</strong><small>{incidents.filter(i => ['high','critical'].includes(text(i.payload.severity))).length} high/critical</small></article>
      <article className={attention.length ? 'warning' : 'healthy'}><span>ACTIONS DUE</span><strong>{attention.length}</strong><small>{attention.filter(task => (due(task)?.getTime() ?? Infinity) < now().getTime()).length} overdue</small></article>
      <article className={handoffs.length ? 'warning' : 'healthy'}><span>OPEN HANDOFFS</span><strong>{handoffs.length}</strong><small>recipient-confirmed closeout</small></article>
      <article className={resources.length ? 'warning' : 'healthy'}><span>RESOURCE PRESSURE</span><strong>{resources.length}</strong><small>{byKind(records,'resource').length} tracked</small></article>
    </div>
    <div className="ops-pulse-grid">
      <section className="ops-panel"><header><div><span className="product-index">ATTENTION QUEUE</span><h2>What needs action now</h2></div><b>{queue.length}</b></header>{queue.length ? <div className="ops-queue">{queue.map(({record,type,detail}) => <article key={`${record.kind}:${record.record_id}`} className={`product-card ops-queue-item ${severityClass(record.payload.severity)}`}><span>{type}</span><div><h2>{recordName(record)}</h2><p>{detail}</p><small>{record.source}</small></div><em>{record.kind === 'task' && record.payload.assignee_id ? team.find(member => member.id === record.payload.assignee_id)?.name ?? 'Assigned' : text(record.payload.status || record.payload.severity || '')}</em></article>)}</div> : <div className="ops-empty"><b>No unresolved attention items</b><p>This means Shorefront has no unresolved records. It does not certify that the port is risk-free.</p></div>}</section>
      <section className="ops-panel"><header><div><span className="product-index">COORDINATION</span><h2>Commitments & obligations</h2></div></header><div className="ops-mini-stats"><div><span>OPEN COMMITMENTS</span><b>{records.filter(openCommitment).length}</b></div><div><span>ACTIVE OBLIGATIONS</span><b>{obligations.length}</b></div><div><span>UNAVAILABLE RESOURCES</span><b>{resources.length}</b></div><div><span>VERSIONED FACTS</span><b>{records.reduce((sum,r)=>sum+r.revision,0)}</b></div></div><a className="ops-link" href="#exceptions">Open exception inbox →</a></section>
    </div>
    <aside className="product-boundary"><b>Real operational mode.</b><p>No synthetic vessels, weather or savings are inserted here. Unknown values remain unknown; Shorefront does not control vessels.</p></aside>
  </div>
}

function timelineWindow(calls: Fact[]) {
  const points = calls.flatMap(call => [when(call.payload.eta), when(call.payload.etd)]).filter((value): value is Date => !!value)
  if (!points.length) return null
  const start = Math.min(...points.map(value => value.getTime()))
  const end = Math.max(...points.map(value => value.getTime()))
  return {start, end: Math.max(end, start + 60 * 60 * 1000)}
}

export function OperationalPlan({workspace}: {workspace: Workspace}) {
  const records = workspace.records
  const calls = byKind(records,'call').filter(call => !['cancelled','departed'].includes(text(call.payload.status)))
  const berths = byKind(records,'berth')
  const resources = byKind(records,'resource')
  const window = timelineWindow(calls)
  return <div className="ops-workspace" data-product-workspace="plan">
    <section className="ops-heading"><span className="product-index">PLAN / BERTH & RESOURCE PICTURE</span><h1>See the recorded plan before you change it.</h1><p>Berth windows, calls and resources are drawn only from your operational records.</p></section>
    <div className="ops-kpis compact"><article><span>BERTHS</span><strong>{berths.length}</strong></article><article><span>ACTIVE CALLS</span><strong>{calls.length}</strong></article><article><span>RESOURCES</span><strong>{resources.length}</strong></article><article className={resources.some(unavailableResource)?'warning':'healthy'}><span>UNAVAILABLE</span><strong>{resources.filter(unavailableResource).length}</strong></article></div>
    <section className="ops-panel"><header><div><span className="product-index">BERTH HORIZON</span><h2>Recorded occupancy windows</h2></div></header>{window && berths.length ? <div className="ops-berth-board">{berths.map(berth => {const berthCalls=calls.filter(call=>call.payload.berth_id===berth.record_id); return <div className="ops-berth-row" key={berth.record_id}><div className="ops-berth-label"><b>{recordName(berth)}</b><small>{text(berth.payload.max_length_m) ? `${text(berth.payload.max_length_m)}m max` : 'capacity not recorded'}</small></div><div className="ops-berth-lane">{berthCalls.map(call => {const eta=when(call.payload.eta)!, etd=when(call.payload.etd)!; const left=((eta.getTime()-window.start)/(window.end-window.start))*100; const width=Math.max(4,((etd.getTime()-eta.getTime())/(window.end-window.start))*100); const vessel=find(records,'vessel',call.payload.vessel_id); return <article className="ops-call-block" key={call.record_id} style={{left:`${Math.max(0,left)}%`,width:`${Math.min(100-left,width)}%`}}><b>{vessel?recordName(vessel):call.record_id}</b><span>{eta.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})} → {etd.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}</span></article>})}</div></div>})}</div> : <div className="ops-empty"><b>No berth timeline yet.</b><p>Create berth and planned call records to populate this board.</p></div>}</section>
    <div className="ops-plan-grid"><section className="ops-panel"><header><div><span className="product-index">RESOURCE PICTURE</span><h2>Availability</h2></div></header><div className="ops-resource-list">{resources.length ? resources.map(resource => <article key={resource.record_id}><div><b>{recordName(resource)}</b><span>{text(resource.payload.resource_type)}</span></div><em className={resource.payload.available ? 'healthy' : 'warning'}>{resource.payload.available ? 'AVAILABLE':'UNAVAILABLE'}</em></article>) : <div className="ops-empty"><b>No resources recorded.</b></div>}</div></section><section className="ops-panel"><header><div><span className="product-index">CALL PRESSURE</span><h2>Schedule state</h2></div></header><div className="ops-resource-list">{calls.map(call => {const vessel=find(records,'vessel',call.payload.vessel_id); const berth=find(records,'berth',call.payload.berth_id); return <article key={call.record_id}><div><b>{vessel?recordName(vessel):call.record_id}</b><span>{berth?recordName(berth):'Berth not assigned'} · {text(call.payload.status)}</span></div><em>{dateLabel(text(call.payload.eta))}</em></article>})}</div></section></div>
  </div>
}

export function OperationalCalls({workspace}: {workspace: Workspace}) {
  const records = workspace.records
  const calls = byKind(records,'call')
  return <div className="ops-workspace" data-product-workspace="calls"><section className="ops-heading"><span className="product-index">CALLS / COORDINATION JOURNEYS</span><h1>One call, every accountable thread.</h1><p>Schedule, incidents, tasks, handoffs, commitments and obligations stay attached to the same call.</p></section>{calls.length ? <div className="ops-call-grid">{calls.map(call => {const vessel=find(records,'vessel',call.payload.vessel_id); const berth=find(records,'berth',call.payload.berth_id); const linked=records.filter(record => ['incident','task','handoff','commitment','obligation'].includes(record.kind) && record.payload.call_id === call.record_id); return <article className="ops-call-card" key={call.record_id}><header><div><span>{call.record_id}</span><h2>{vessel?recordName(vessel):call.record_id}</h2><p>{berth?recordName(berth):'Berth not assigned'} · {text(call.payload.status).toUpperCase()}</p></div><em>{text(call.payload.status)}</em></header><div className="ops-call-times"><div><span>ETA</span><b>{dateLabel(text(call.payload.eta))}</b></div><div><span>ETD</span><b>{dateLabel(text(call.payload.etd))}</b></div></div><div className="ops-journey">{linked.length ? linked.map(item => <div key={`${item.kind}:${item.record_id}`} className={item.kind}><i/><div><span>{item.kind}</span><b>{recordName(item)}</b><small>{text(item.payload.status || item.payload.severity || '')}</small></div></div>) : <div className="ops-empty small"><b>No linked operational threads yet.</b></div>}</div></article>})}</div> : <div className="ops-empty"><b>No port calls recorded.</b><p>Create vessel, berth and call records to build the call journeys.</p></div>}</div>
}

export function OperationalExceptions({workspace, team}: {workspace: Workspace; team: User[]}) {
  const records = workspace.records
  const items = [
    ...records.filter(unresolvedIncident).map(record => ({record,type:'INCIDENT',state:text(record.payload.severity),detail:text(record.payload.detail)})),
    ...records.filter(unfinishedTask).filter(record => (due(record)?.getTime() ?? Infinity) < now().getTime()).map(record => ({record,type:'OVERDUE TASK',state:text(record.payload.status),detail:`Assigned ${team.find(member=>member.id===record.payload.assignee_id)?.name ?? 'unassigned'}`})),
    ...records.filter(unavailableResource).map(record => ({record,type:'RESOURCE',state:'unavailable',detail:text(record.payload.resource_type)})),
    ...records.filter(incompleteHandoff).map(record => ({record,type:'HANDOFF',state:text(record.payload.status),detail:'Recipient acknowledgement incomplete'})),
    ...records.filter(activeObligation).filter(record => (due(record)?.getTime() ?? Infinity) < now().getTime()).map(record => ({record,type:'OBLIGATION',state:text(record.payload.status),detail:`Due ${dateLabel(text(record.payload.due_at))}`})),
  ]
  return <div className="ops-workspace" data-product-workspace="exceptions"><section className="ops-heading"><span className="product-index">EXCEPTIONS / ACTION INBOX</span><h1>What has diverged from the record?</h1><p>Operational deviations are grouped by source, state and accountable next action.</p></section><div className="ops-kpis compact"><article className={records.filter(unresolvedIncident).length?'critical':'healthy'}><span>INCIDENTS</span><strong>{records.filter(unresolvedIncident).length}</strong></article><article className={records.filter(unavailableResource).length?'warning':'healthy'}><span>RESOURCES</span><strong>{records.filter(unavailableResource).length}</strong></article><article className={records.filter(incompleteHandoff).length?'warning':'healthy'}><span>HANDOFFS</span><strong>{records.filter(incompleteHandoff).length}</strong></article><article className={items.length?'warning':'healthy'}><span>TOTAL EXCEPTIONS</span><strong>{items.length}</strong></article></div><section className="ops-panel"><header><div><span className="product-index">OPERATIONAL EXCEPTION INBOX</span><h2>Prioritized deviations</h2></div><b>{items.length}</b></header>{items.length ? <div className="ops-exception-list">{items.map(({record,type,state,detail}) => <article key={`${type}:${record.record_id}`} className={severityClass(record.payload.severity)}><span>{type}</span><div><b>{recordName(record)}</b><p>{detail}</p><small>{record.source}</small></div><em>{state}</em></article>)}</div> : <div className="ops-empty"><b>No operational exceptions recorded.</b><p>The inbox is empty because no unresolved exceptions exist in Shorefront records.</p></div>}</section></div>
}
