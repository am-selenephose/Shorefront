import {useEffect,useState} from 'react'
import {dateLabel,productRequest,recordName,type Fact,type User,type Workspace} from './productClient'

export type OperationalActions = {
  writable:boolean
  onCreate:(kind:string,payload?:Fact['payload'])=>void
  onEdit:(record:Fact)=>void
}
const byKind = (records:Fact[],kind:string)=>records.filter(r=>r.kind===kind)
const find = (records:Fact[],kind:string,id:unknown)=>records.find(r=>r.kind===kind && r.record_id===id)
const text = (value:unknown)=>value==null?'':String(value)
const closed = new Set(['done','resolved','acknowledged','fulfilled','cancelled','declined','completed'])
const coordination = new Set(['handoff','commitment','obligation'])
const activeCall = (r:Fact)=>r.kind==='call' && !['departed','cancelled'].includes(text(r.payload.status))
const pending = (r:Fact)=>r.kind==='incident' ? r.payload.status!=='resolved' : r.kind==='resource' ? r.payload.available===false : ['task',...coordination].includes(r.kind) && !closed.has(text(r.payload.status))
const due = (r:Fact)=>r.payload.due_at?new Date(text(r.payload.due_at)).getTime():Infinity
const owner = (r:Fact,team:User[])=>team.find(u=>u.id===(r.payload.assignee_id ?? r.payload.recipient_id))?.name ?? 'Owner not assigned'
const rank = (r:Fact)=>r.payload.severity==='critical'?0:r.payload.severity==='high'?1:due(r)<Date.now()?2:3
const attention = (facts:Fact[])=>facts.filter(pending).sort((a,b)=>rank(a)-rank(b) || due(a)-due(b) || a.record_id.localeCompare(b.record_id))
const severityClass = (r:Fact)=>['critical','high','medium','low'].includes(text(r.payload.severity))?text(r.payload.severity):'neutral'

function RecordActions({record,...actions}:OperationalActions & {record:Fact}) {
  if (coordination.has(record.kind)) return <a className="ops-action-link" href="#coordination">Review thread →</a>
  return <div className="product-actions"><button disabled={!actions.writable} onClick={()=>actions.onEdit(record)}>Update record</button>
    {record.kind==='incident' && <button disabled={!actions.writable} onClick={()=>actions.onCreate('task',{incident_id:record.record_id,call_id:record.payload.call_id})}>Assign task</button>}</div>
}

function SetupGuide({facts,...actions}:{facts:Fact[]} & OperationalActions) {
  const port = byKind(facts,'port')[0]
  const steps = [
    {kind:'port',label:'Set up port',detail:'Name and operating timezone',ready:true},
    {kind:'berth',label:'Add berth',detail:'A named berth and its recorded limits',ready:!!port},
    {kind:'vessel',label:'Add vessel',detail:'A vessel from your own register',ready:true},
    {kind:'call',label:'Plan first call',detail:'Arrival, departure and berth window',ready:byKind(facts,'vessel').length>0},
  ]
  return <section className="ops-panel ops-setup"><header><div><span className="product-index">WORKSPACE SETUP</span><h2>Bring your first call into view</h2></div><b>{steps.filter(s=>byKind(facts,s.kind).length).length}/4</b></header>
    <ol>{steps.map((step,i)=>{const done=byKind(facts,step.kind).length>0; return <li key={step.kind}><span className="setup-number">{done?'✓':`0${i+1}`}</span><div><b>{step.label}</b><p>{step.detail}</p><small>{done?'Recorded':!step.ready?'Complete its prerequisite first':'Ready to add'}</small></div><button disabled={!actions.writable || !step.ready} onClick={()=>actions.onCreate(step.kind,step.kind==='berth'&&port?{port_id:port.record_id}:{})}>{step.label}</button></li>})}</ol>
    <p>Already have a register? <a href="#records">Import your own records</a>. Setup never inserts sample operations.</p>
  </section>
}

function AttentionRows({items,team,...actions}:{items:Fact[];team:User[]} & OperationalActions) {
  return <div className="ops-queue">{items.map(record=><article key={`${record.kind}:${record.record_id}`} className={`ops-queue-item ${severityClass(record)}`}>
    <span>{record.kind}{due(record)<Date.now()?' / OVERDUE':''}</span><div><h2>{recordName(record)}</h2><p>{record.kind==='task'?`Assigned to ${owner(record,team)}`:coordination.has(record.kind)?`Responsible party: ${owner(record,team)}`:text(record.payload.detail || record.payload.resource_type)}</p>
      {record.payload.due_at && <p>Due {dateLabel(text(record.payload.due_at))}</p>}<small>Source: {record.source} · {text(record.payload.status || record.payload.severity || 'unavailable')}</small></div>
    <RecordActions record={record} {...actions}/></article>)}</div>
}

export function OperationalPulse({workspace,team,...actions}:{workspace:Workspace;team:User[]} & OperationalActions) {
  const records=workspace.records, queue=attention(records), port=byKind(records,'port')[0]
  const incidents=records.filter(r=>r.kind==='incident'&&pending(r)), tasks=records.filter(r=>r.kind==='task'&&pending(r))
  const handoffs=records.filter(r=>r.kind==='handoff'&&pending(r)), resources=records.filter(r=>r.kind==='resource'&&pending(r))
  return <div className="ops-workspace" data-product-workspace="pulse">
    <section className="ops-hero"><div><span className="product-index">PULSE / OPERATIONAL CONTROL</span><h1>Your port. Your operational record.</h1><p>{port?`${recordName(port)} — sourced facts, accountable actions and preserved context.`:'Your working picture begins with your port and its first recorded call.'}</p></div><div className="ops-live-badge">RECORDED FACTS<b>{records.length}</b></div></section>
    {!byKind(records,'call').length && <SetupGuide facts={records} {...actions}/>}
    <div className="ops-kpis">{[['ACTIVE CALLS',records.filter(activeCall).length],['OPEN INCIDENTS',incidents.length],['OPEN TASKS',tasks.length],['OPEN HANDOFFS',handoffs.length],['UNAVAILABLE RESOURCES',resources.length]].map(([label,count])=><article key={label}><span>{label}</span><strong>{count}</strong></article>)}</div>
    <div className="ops-pulse-grid"><section className="ops-panel"><header><div><span className="product-index">ATTENTION QUEUE</span><h2>What needs action now</h2></div><b>{queue.length}</b></header>
      {queue.length?<><AttentionRows items={queue.slice(0,12)} team={team} {...actions}/><a className="ops-link" href="#exceptions">View all {queue.length} attention items →</a></>:<div className="ops-empty"><b>No unresolved attention items</b><p>No unresolved work is recorded here. This does not certify that the port is risk-free.</p><button disabled={!actions.writable} onClick={()=>actions.onCreate('incident')}>Record incident</button></div>}</section>
      <section className="ops-panel"><header><div><span className="product-index">COORDINATION</span><h2>Commitments & obligations</h2></div></header><div className="ops-mini-stats">{[['OPEN COMMITMENTS',records.filter(r=>r.kind==='commitment'&&pending(r)).length],['OPEN OBLIGATIONS',records.filter(r=>r.kind==='obligation'&&pending(r)).length],['OVERDUE TASKS',tasks.filter(r=>due(r)<Date.now()).length],['TRACKED RESOURCES',byKind(records,'resource').length]].map(([label,count])=><div key={label}><span>{label}</span><b>{count}</b></div>)}</div><a className="ops-link" href="#coordination">Open coordination desk →</a><div className="ops-panel-actions"><button disabled={!actions.writable} onClick={()=>actions.onCreate('task')}>Assign new task</button></div></section></div>
    <aside className="product-boundary"><b>Real operational mode.</b><p>No synthetic vessels, weather or savings. Unknown values remain unknown; Shorefront does not control vessels.</p></aside>
  </div>
}

export type Conflict = {kind:string;record_ids:string[];explanation:string}
export function OperationalPlan({workspace,conflictsOverride,...actions}:{workspace:Workspace;conflictsOverride?:Conflict[]} & OperationalActions) {
  const records=workspace.records, calls=records.filter(activeCall), berths=byKind(records,'berth'), resources=byKind(records,'resource')
  const [conflicts,setConflicts]=useState<Conflict[]>(conflictsOverride ?? []), [error,setError]=useState(''), [loaded,setLoaded]=useState(!!conflictsOverride), [retry,setRetry]=useState(0)
  useEffect(()=>{if(conflictsOverride){setConflicts(conflictsOverride);setError('');setLoaded(true);return} let active=true; setLoaded(false); void productRequest<Conflict[]>('/conflicts').then(value=>{if(active){setConflicts(value);setError('');setLoaded(true)}}).catch(e=>{if(active){setError(String(e));setLoaded(true)}}); return ()=>{active=false}},[records,retry,conflictsOverride])
  const start=calls.length?Math.min(...calls.map(r=>new Date(text(r.payload.eta)).getTime())):0
  const end=calls.length?Math.max(...calls.map(r=>new Date(text(r.payload.etd)).getTime())):1
  return <div className="ops-workspace" data-product-workspace="plan"><section className="ops-heading"><span className="product-index">PLAN / BERTH & RESOURCE PICTURE</span><h1>See the recorded plan before you change it.</h1><p>Recorded occupancy, resource availability and conflicts. Movement clearance stays with your operational authority.</p></section>
    <div className="product-actions"><button className="product-primary" disabled={!actions.writable} onClick={()=>actions.onCreate('call')}>Plan port call</button><button disabled={!actions.writable} onClick={()=>actions.onCreate('resource')}>Add resource</button></div>
    <section className="ops-panel"><header><div><span className="product-index">BERTH HORIZON</span><h2>Recorded occupancy windows</h2></div></header>
      {calls.length&&berths.length?<div className="ops-berth-board"><div className="ops-axis"><span>{dateLabel(new Date(start).toISOString())}</span><span>{dateLabel(new Date(end).toISOString())}</span></div>{berths.map(berth=>{const rows=calls.filter(call=>call.payload.berth_id===berth.record_id);return <div key={berth.record_id} className="ops-berth-row"><div className="ops-berth-label"><b>{recordName(berth)}</b><small>{text(berth.payload.max_length_m)?`${berth.payload.max_length_m}m max`:'Capacity not recorded'}</small></div><div className="ops-lane-stack">{rows.length?rows.map(call=>{const left=(new Date(text(call.payload.eta)).getTime()-start)/(end-start)*100; const width=(new Date(text(call.payload.etd)).getTime()-new Date(text(call.payload.eta)).getTime())/(end-start)*100;return <div className="ops-timeline-track" key={call.record_id}><button className="ops-timeline-call" style={{marginLeft:`${left}%`,width:`${Math.max(1,width)}%`}} onClick={()=>actions.onEdit(call)} disabled={!actions.writable} title={`${recordName(find(records,'vessel',call.payload.vessel_id)??call)} · ${dateLabel(text(call.payload.eta))} → ${dateLabel(text(call.payload.etd))}`}><b>{recordName(find(records,'vessel',call.payload.vessel_id)??call)}</b></button></div>}):<p>No recorded call</p>}</div></div>})}</div>:<div className="ops-empty"><b>No berth timeline yet.</b><p>Add your berth and call windows to see the recorded schedule.</p><button disabled={!actions.writable} onClick={()=>actions.onCreate(berths.length?'call':'berth')}>{berths.length?'Plan port call':'Add berth'}</button></div>}
    </section>
    <div className="ops-plan-grid"><section className="ops-panel"><header><div><span className="product-index">RECORDED CONSTRAINTS</span><h2>Schedule conflicts</h2></div><b>{conflicts.length}</b></header>{!loaded&&<p className="ops-empty" role="status">Checking recorded constraints…</p>}{error?<div className="product-error" role="alert">{error}<button onClick={()=>setRetry(v=>v+1)}>Retry conflicts</button></div>:loaded&&(!conflicts.length?<div className="ops-empty"><b>No conflicts found in recorded constraints.</b><p>Unrecorded resource requirements, weather and navigational limits are not checked.</p></div>:conflicts.map((conflict,i)=><div className="ops-conflict" key={i}><span className="product-index">{conflict.kind.replaceAll('_',' ')}</span><p>{conflict.explanation}</p>{conflict.record_ids.map(id=>{const call=find(records,'call',id);return call?<button key={id} disabled={!actions.writable} onClick={()=>actions.onEdit(call)}>Review {recordName(find(records,'vessel',call.payload.vessel_id)??call)}</button>:null})}</div>))}</section>
    <section className="ops-panel"><header><div><span className="product-index">RESOURCE PICTURE</span><h2>Availability</h2></div></header><div className="ops-resource-list">{resources.length?resources.map(resource=><article key={resource.record_id}><div><b>{recordName(resource)}</b><span>{text(resource.payload.resource_type)} · {resource.payload.available?'Available':'Unavailable'}</span></div><button disabled={!actions.writable} onClick={()=>actions.onEdit(resource)}>Update availability</button></article>):<div className="ops-empty"><b>No resources recorded.</b><button disabled={!actions.writable} onClick={()=>actions.onCreate('resource')}>Add resource</button></div>}</div></section></div>
  </div>
}

export function OperationalCalls({workspace,...actions}:{workspace:Workspace} & OperationalActions) {
  const [query,setQuery]=useState(''), [scope,setScope]=useState('all')
  const records=workspace.records, all=byKind(records,'call')
  const calls=all.filter(call=>(scope==='all'||activeCall(call)) && `${recordName(find(records,'vessel',call.payload.vessel_id)??call)} ${call.record_id}`.toLowerCase().includes(query.toLowerCase()))
  return <div className="ops-workspace" data-product-workspace="calls"><section className="ops-heading"><span className="product-index">CALLS / COORDINATION JOURNEYS</span><h1>One call, every accountable thread.</h1><p>Work directly from the call. Its schedule, incidents, tasks and coordination stay linked.</p></section><div className="product-actions"><button className="product-primary" disabled={!actions.writable} onClick={()=>actions.onCreate('call')}>Plan port call</button></div>
    <div className="product-filter"><label>Search calls<input type="search" value={query} onChange={e=>setQuery(e.target.value)}/></label><label>Call scope<select value={scope} onChange={e=>setScope(e.target.value)}><option value="all">All calls</option><option value="active">Active calls</option></select></label></div>
    {calls.length?<div className="ops-call-grid">{calls.map(call=>{const vessel=find(records,'vessel',call.payload.vessel_id), berth=find(records,'berth',call.payload.berth_id),linked=records.filter(r=>['incident','task',...coordination].includes(r.kind)&&r.payload.call_id===call.record_id);return <article className="ops-call-card" key={call.record_id}><header><div><span>{call.record_id}</span><h2>{vessel?recordName(vessel):call.record_id}</h2><p>{berth?recordName(berth):'Berth not assigned'} · {text(call.payload.status)}</p></div><button disabled={!actions.writable} onClick={()=>actions.onEdit(call)}>Edit call</button></header><div className="ops-call-times"><div><span>ETA</span><b>{dateLabel(text(call.payload.eta))}</b></div><div><span>ETD</span><b>{dateLabel(text(call.payload.etd))}</b></div></div>
      <div className="ops-panel-actions product-actions"><button disabled={!actions.writable} onClick={()=>actions.onCreate('incident',{call_id:call.record_id})}>Record incident</button><button disabled={!actions.writable} onClick={()=>actions.onCreate('task',{call_id:call.record_id})}>Assign task</button><button disabled={!actions.writable} onClick={()=>actions.onCreate('handoff',{call_id:call.record_id})}>Prepare handoff</button></div>
      <div className="ops-call-threads">{linked.length?linked.map(item=><div key={`${item.kind}:${item.record_id}`}><div><span className="product-index">{item.kind} · {text(item.payload.status)}</span><b>{recordName(item)}</b></div><RecordActions record={item} {...actions}/></div>):<div className="ops-empty"><b>No linked operational threads yet.</b><p>Create an incident, task or handoff using the actions above.</p></div>}</div><p className="ops-source">Source: {call.source}</p></article>})}</div>:<div className="product-empty"><h2>{all.length?'No calls match this view.':'No port calls recorded.'}</h2><p>{all.length?'Try another search or scope.':'Start with your vessel and berth, then add the arrival and departure window.'}</p>{!all.length&&<SetupGuide facts={records} {...actions}/>}</div>}
  </div>
}

export function OperationalExceptions({workspace,team,...actions}:{workspace:Workspace;team:User[]} & OperationalActions) {
  const [scope,setScope]=useState('all'), [kind,setKind]=useState('all'), [query,setQuery]=useState('')
  const all=attention(workspace.records), items=all.filter(r=>(kind==='all'||r.kind===kind) && (scope==='all'||r.payload.assignee_id===workspace.user.id||r.payload.recipient_id===workspace.user.id) && recordName(r).toLowerCase().includes(query.toLowerCase()))
  return <div className="ops-workspace" data-product-workspace="exceptions"><section className="ops-heading"><span className="product-index">EXCEPTIONS / ACTION INBOX</span><h1>Turn attention into accountable action.</h1><p>Critical incidents first, then high severity, overdue work and remaining open threads. A due date is not a proof of breach.</p></section>
    <div className="product-actions"><button className="product-primary" disabled={!actions.writable} onClick={()=>actions.onCreate('incident')}>Record incident</button><button disabled={!actions.writable} onClick={()=>actions.onCreate('task')}>Assign task</button></div>
    <div className="coord-filters"><label>Attention scope<select value={scope} onChange={e=>setScope(e.target.value)}><option value="all">All attention</option><option value="mine">Assigned to me</option></select></label><label>Attention type<select value={kind} onChange={e=>setKind(e.target.value)}><option value="all">All types</option>{['incident','task','handoff','commitment','obligation','resource'].map(k=><option key={k}>{k}</option>)}</select></label><label>Search attention<input type="search" value={query} onChange={e=>setQuery(e.target.value)}/></label></div>
    <section className="ops-panel"><header><div><span className="product-index">{items.length} OF {all.length} RECORDED ITEMS</span><h2>Prioritized deviations</h2></div></header>{items.length?<AttentionRows items={items} team={team} {...actions}/>:<div className="ops-empty"><b>No attention items in this view.</b><p>Try another filter or record the operational issue you need to track.</p></div>}</section>
  </div>
}
