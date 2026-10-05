import {useCallback, useEffect, useRef, useState, type CSSProperties, type FormEvent} from 'react'
import {dateLabel, productRequest, recordName, type Fact, type User} from './productClient'

type Action = {status:string; label:string; requires_proof:boolean; requires_review:boolean}
type Item = {record:Fact; creator_id:string; actions:Action[]}
const closed = new Set(['acknowledged','fulfilled','declined','cancelled','completed'])

function coordinationKey(item:Item) { return `${item.record.kind}:${item.record.record_id}` }
function responsibleParty(item:Item) { return String(item.record.payload.recipient_id ?? item.record.payload.assignee_id ?? '') }
function coordinationSteps(item:Item) {
  if (item.record.kind==='handoff') return ['prepared','sent','acknowledged']
  if (item.record.kind==='commitment') return ['proposed','accepted','fulfilled']
  return ['draft','active','completed']
}

function ProductHarborVisual({facts,items,focusedThreadKey}:{facts:Fact[];items:Item[];focusedThreadKey:string}) {
  const berths=facts.filter(f=>f.kind==='berth')
  const calls=facts.filter(f=>f.kind==='call' && !['departed','cancelled'].includes(String(f.payload.status)))
  const resources=facts.filter(f=>f.kind==='resource')
  const openItems=items.filter(item=>!closed.has(String(item.record.payload.status)))
  const focusedItem=items.find(item=>coordinationKey(item)===focusedThreadKey)
  const focusedCallId=String(focusedItem?.record.payload.call_id ?? '')
  const validCoordinate=(berth:Fact)=>typeof berth.payload.latitude==='number' && Number.isFinite(berth.payload.latitude) && typeof berth.payload.longitude==='number' && Number.isFinite(berth.payload.longitude)
  const geocodedBerths=berths.filter(validCoordinate)
  const schematicBerths=berths.filter(berth=>!validCoordinate(berth))
  const coordinateMode=geocodedBerths.length>0
  const vesselFor=(call:Fact)=>facts.find(f=>f.kind==='vessel' && f.record_id===call.payload.vessel_id)
  const threadCount=(callId:string)=>openItems.filter(item=>item.record.payload.call_id===callId).length
  const berthCalls=(berthId:string)=>calls.filter(call=>call.payload.berth_id===berthId)
  const lats=geocodedBerths.map(b=>Number(b.payload.latitude))
  const lons=geocodedBerths.map(b=>Number(b.payload.longitude))
  const minLat=lats.length?Math.min(...lats):0, maxLat=lats.length?Math.max(...lats):0
  const minLon=lons.length?Math.min(...lons):0, maxLon=lons.length?Math.max(...lons):0
  const latSpan=maxLat-minLat, lonSpan=maxLon-minLon
  const position=(berth:Fact)=>({
    left:`${lonSpan===0?50:8+84*((Number(berth.payload.longitude)-minLon)/lonSpan)}%`,
    top:`${latSpan===0?50:8+84*((maxLat-Number(berth.payload.latitude))/latSpan)}%`,
  })
  return <article className="coord-harbor-visual">
    <header><div><span className="product-index">{coordinateMode?'RECORDED COORDINATE MAP':'SCHEMATIC BERTH LAYOUT · NOT GEOGRAPHIC'}</span><h2>Harbor context</h2></div><div className="coord-visual-metrics"><b>{calls.length} active calls</b><small>{geocodedBerths.length}/{berths.length} berths geocoded</small></div></header>
    {coordinateMode ? <div className="coord-coordinate-map" aria-label="Recorded berth coordinate map">
      <div className="coord-coordinate-grid" aria-hidden="true"/>
      <div className="coord-coordinate-bounds"><span>{maxLat.toFixed(4)}, {minLon.toFixed(4)}</span><span>{minLat.toFixed(4)}, {maxLon.toFixed(4)}</span></div>
      {geocodedBerths.map(berth=>{
        const linkedCalls=berthCalls(berth.record_id)
        const focused=linkedCalls.some(call=>call.record_id===focusedCallId)
        return <div className={`coord-map-berth ${focused?'is-focused':''}`} key={berth.record_id} style={position(berth)}>
          <div className="coord-map-pin" aria-hidden="true"/>
          <div className="coord-map-berth-label"><b>{recordName(berth)}</b><span>{Number(berth.payload.latitude).toFixed(4)}, {Number(berth.payload.longitude).toFixed(4)}</span></div>
          <div className="coord-map-calls">{linkedCalls.length?linkedCalls.map(call=>{const vessel=vesselFor(call);return <div className={`coord-harbor-call coord-map-call ${call.record_id===focusedCallId?'is-focused':''}`} key={call.record_id}><b>{vessel?recordName(vessel):call.record_id}</b><span>{String(call.payload.status)}</span><em>{threadCount(call.record_id)} open threads</em></div>}):<span className="coord-berth-empty">No active call</span>}</div>
        </div>
      })}
    </div> : null}
    {(!coordinateMode || schematicBerths.length>0) && <div className={`coord-harbor-water ${coordinateMode?'coord-schematic-fallback':''}`}>
      {coordinateMode && <div className="coord-schematic-label"><span className="product-index">SCHEMATIC BERTH LAYOUT · NOT GEOGRAPHIC</span><small>Berths below have no recorded coordinates.</small></div>}
      {(coordinateMode?schematicBerths:berths).length?(coordinateMode?schematicBerths:berths).map((berth,index)=>{const linkedCalls=berthCalls(berth.record_id);const focused=linkedCalls.some(call=>call.record_id===focusedCallId);return <div className={`coord-berth-lane ${focused?'is-focused':''}`} key={berth.record_id} style={{'--lane':index} as CSSProperties}><div className="coord-berth-name"><b>{recordName(berth)}</b><span>{berth.payload.max_length_m ? `${berth.payload.max_length_m}m max` : 'capacity not recorded'}</span></div><div className="coord-berth-track">{linkedCalls.length?linkedCalls.map((call,callIndex)=>{const vessel=vesselFor(call);return <div className={`coord-vessel-chip coord-harbor-call ${call.record_id===focusedCallId?'is-focused':''}`} key={call.record_id} style={{'--call':callIndex} as CSSProperties}><b>{vessel?recordName(vessel):call.record_id}</b><span>{dateLabel(String(call.payload.eta))} → {dateLabel(String(call.payload.etd))}</span><em>{threadCount(call.record_id)} open coordination</em></div>}):<span className="coord-berth-empty">No active call</span>}</div></div>}):<div className="coord-visual-empty">No berth records yet.</div>}
    </div>}
    <div className="coord-resource-strip">{resources.length?resources.map(resource=><div key={resource.record_id} className={resource.payload.available===false?'unavailable':'available'}><span>{String(resource.payload.resource_type||'resource').toUpperCase()}</span><b>{recordName(resource)}</b><em>{resource.payload.available===false?'UNAVAILABLE':'AVAILABLE'}</em></div>):<div className="coord-visual-empty">No service resources recorded.</div>}</div>
  </article>
}

function CoordinationVisualContext({facts,items,team,focusedThreadKey,onFocusThread}:{facts:Fact[];items:Item[];team:User[];focusedThreadKey:string;onFocusThread:(key:string)=>void}) {
  const calls=facts.filter(f=>f.kind==='call' && !['departed','cancelled'].includes(String(f.payload.status)))
  const vesselFor=(call:Fact)=>facts.find(f=>f.kind==='vessel' && f.record_id===call.payload.vessel_id)
  const openItems=items.filter(item=>!closed.has(String(item.record.payload.status)))
  const dueItems=[...openItems].filter(item=>item.record.payload.due_at).sort((a,b)=>new Date(String(a.record.payload.due_at)).getTime()-new Date(String(b.record.payload.due_at)).getTime())
  const dueTimes=dueItems.map(item=>new Date(String(item.record.payload.due_at)).getTime()).filter(Number.isFinite)
  const min=dueTimes.length?Math.min(...dueTimes):Date.now(), max=dueTimes.length?Math.max(...dueTimes):min+3600000, span=Math.max(3600000,max-min)
  const member=(id:string)=>team.find(u=>u.id===id)?.name ?? (id || 'Unassigned')
  const focusedItem=items.find(item=>coordinationKey(item)===focusedThreadKey)
  const focusedCallId=String(focusedItem?.record.payload.call_id ?? '')
  return <section className="coord-visual-context" role="region" aria-label="Coordination visual context">
    <div className="coord-visual-grid">
      <ProductHarborVisual facts={facts} items={items} focusedThreadKey={focusedThreadKey}/>
      <article className="coord-network-visual">
        <header><div><span className="product-index">COORDINATION NETWORK</span><h2>Responsibility graph · CALL → THREAD → PARTY</h2></div><b>{openItems.length} open</b></header>
        <div className="coord-network">{calls.length?calls.map(call=>{const vessel=vesselFor(call);const linked=openItems.filter(item=>item.record.payload.call_id===call.record_id);const callFocused=call.record_id===focusedCallId;return <div className={`coord-network-row ${callFocused?'is-focused':''}`} key={call.record_id}><div className={`coord-call-node ${callFocused?'is-focused':''}`}><span>CALL</span><b>{vessel?recordName(vessel):call.record_id}</b><small>{String(call.payload.status)}</small></div><div className="coord-network-line" aria-hidden="true"/><div className="coord-thread-party-list">{linked.length?linked.map(item=>{const key=coordinationKey(item),partyId=responsibleParty(item),focused=key===focusedThreadKey,steps=coordinationSteps(item),status=String(item.record.payload.status);return <div className={`coord-thread-party ${focused?'is-focused':''}`} key={key}><button type="button" className={`coord-thread-node ${item.record.kind} ${focused?'is-focused':''}`} onClick={()=>onFocusThread(focused?'':key)} aria-pressed={focused}><span>{item.record.kind}</span><b>{recordName(item.record)}</b><em>{status}</em><div className="coord-thread-progress" aria-label={`${recordName(item.record)} state path`}>{steps.map((step,index)=>{const current=steps.indexOf(status);return <span className={index<current?'is-done':index===current?'is-current':'is-next'} key={step}>{step.toUpperCase()}</span>})}</div></button><div className="coord-party-line" aria-hidden="true"/><div className={`coord-party-node ${focused?'is-focused':''}`}><span>PARTY</span><b>{member(partyId)}</b><em>{partyId}</em></div></div>}):<span className="coord-thread-none">No open thread</span>}</div></div>}):<div className="coord-visual-empty">No active calls recorded.</div>}</div>
      </article>
    </div>
    <article className="coord-due-visual">
      <header><div><span className="product-index">DUE-WINDOW TIMELINE</span><h2>Open coordination deadlines</h2></div><b>{dueItems.length}</b></header>
      {dueItems.length?<div className="coord-due-track"><div className="coord-due-axis"><span>{dateLabel(new Date(min).toISOString())}</span><span>{dateLabel(new Date(max).toISOString())}</span></div>{dueItems.map(item=>{const value=new Date(String(item.record.payload.due_at)).getTime();const left=Math.max(2,Math.min(98,((value-min)/span)*100));const key=coordinationKey(item), overdue=value<Date.now(), focused=key===focusedThreadKey;return <button type="button" className={`coord-due-marker ${item.record.kind} ${overdue?'is-overdue':''} ${focused?'is-focused':''}`} key={key} style={{left:`${left}%`}} title={`${recordName(item.record)} · ${dateLabel(String(item.record.payload.due_at))}`} onClick={()=>onFocusThread(focused?'':key)}><i/><span>{overdue?'OVERDUE · ':''}{item.record.kind}</span><b>{recordName(item.record)}</b></button>})}</div>:<div className="coord-visual-empty padded">No open coordination deadlines.</div>}
    </article>
  </section>
}

function Transition({item, action, writable, onDone, onCancel}: {
  item:Item; action:Action; writable:boolean; onDone:()=>Promise<void>; onCancel:()=>void
}) {
  const [busy,setBusy] = useState(false)
  const [error,setError] = useState('')
  const [committed,setCommitted] = useState(false)
  const attempt = useRef<{intent:string; key:string}|null>(null)
  async function submit(event:FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!writable || busy || committed) return
    setBusy(true); setError('')
    const data = new FormData(event.currentTarget)
    // Do not round-trip frozen terms through editable date inputs. Preserve precision/offset.
    const payload:Fact['payload'] = {...item.record.payload, status:action.status}
    if (action.requires_proof) payload.proof = String(data.get('proof'))
    if (action.requires_review) payload.review_note = String(data.get('review_note'))
    const command = {record_id:item.record.record_id,expected_revision:item.record.revision,
      source:String(data.get('source')),payload}
    const intent = JSON.stringify(command)
    if (attempt.current?.intent !== intent) attempt.current = {intent,key:crypto.randomUUID()}
    try {
      await productRequest(`/records/${item.record.kind}`,command,attempt.current.key)
      setCommitted(true)
      await onDone()
    } catch (failure) {setError(failure instanceof Error ? failure.message : 'Action could not be completed')}
    finally {setBusy(false)}
  }
  return <form className="coord-transition" onSubmit={submit} aria-label={action.label} aria-busy={busy}>
    <h3>{action.label}</h3><p>The existing terms stay unchanged. This action creates a new, sourced version.</p>
    <fieldset disabled={!writable || busy || committed}>
      {action.requires_proof && <label>Evidence / confirmation<textarea name="proof" required maxLength={2000} rows={3}/></label>}
      {action.requires_review && <label>Human review note<textarea name="review_note" required maxLength={2000} rows={3} defaultValue={String(item.record.payload.review_note ?? '')}/></label>}
      <label>Action source<input name="source" required maxLength={500} defaultValue="Operator confirmation"/></label>
      <div className="product-actions"><button type="submit" className="product-primary">{busy ? 'Recording…' : 'Confirm action'}</button></div>
    </fieldset>
    {committed && <p role="status">Action recorded. If the view could not refresh, do not resubmit.</p>}
    {error && <p className="product-error" role="alert">{error}</p>}
    <div className="product-actions">{committed && <button type="button" disabled={busy || !writable} onClick={() => {setBusy(true); void onDone().catch(e=>setError(String(e))).finally(()=>setBusy(false))}}>Refresh recorded action</button>}
      <button type="button" disabled={busy} onClick={onCancel}>{committed ? 'Close action' : 'Cancel action'}</button></div>
  </form>
}

export default function ProductCoordination({facts,team,writable,onRefresh,onCreate}: {
  facts:Fact[]; team:User[]; writable:boolean; onRefresh:()=>Promise<void>;
  onCreate:(kind:string, payload?:Fact['payload'])=>void
}) {
  const [items,setItems] = useState<Item[]>([])
  const [loading,setLoading] = useState(true)
  const [error,setError] = useState('')
  const [current,setCurrent] = useState(false)
  const [scope,setScope] = useState('open')
  const [kind,setKind] = useState('all')
  const [query,setQuery] = useState('')
  const [focusedThreadKey,setFocusedThreadKey] = useState('')
  const [selected,setSelected] = useState<{item:Item; action:Action}|null>(null)
  const generation = useRef(0)
  const load = useCallback(async () => {
    const request = ++generation.current
    try {
      const result = await productRequest<{items:Item[]}>('/coordination')
      if (!Array.isArray(result.items)) throw new Error('Invalid coordination response')
      if (request !== generation.current) return
      setItems(result.items); setError(''); setCurrent(true)
    } catch (failure) {
      if (request !== generation.current) return
      setError(String(failure)); setCurrent(false); throw failure
    } finally {if (request === generation.current) setLoading(false)}
  },[])
  useEffect(()=>{void load().catch(()=>{}); return ()=>{generation.current++}},[load,facts])
  const member = (id:unknown)=>team.find(u=>u.id===id)?.name ?? String(id ?? 'Not assigned')
  const callLabel = (id:unknown)=> {
    const call = facts.find(f=>f.kind==='call' && f.record_id===id)
    const vessel = facts.find(f=>f.kind==='vessel' && f.record_id===call?.payload.vessel_id)
    return vessel ? recordName(vessel) : String(id)
  }
  const filtered = items.filter(({record,actions}) =>
    (scope==='all' || (scope==='mine' ? actions.length>0 : !closed.has(String(record.payload.status)))) &&
    (kind==='all' || record.kind===kind) &&
    `${recordName(record)} ${callLabel(record.payload.call_id)}`.toLowerCase().includes(query.toLowerCase()))
  return <div className="ops-workspace" data-product-workspace="coordination">
    <section className="ops-heading"><span className="product-index">COORDINATION / NAMED PARTIES · CLEAR RESPONSIBILITY</span><h1>Promises become accountable work.</h1><p>Send a handoff, confirm receipt, fulfill a commitment or close a reviewed obligation—with the named party and its evidence preserved.</p></section>
    <div className="product-actions">{['handoff','commitment','obligation'].map(k=><button className={k==='handoff'?'product-primary':''} key={k} disabled={!writable} onClick={()=>onCreate(k)}>New {k}</button>)}</div>
    <CoordinationVisualContext facts={facts} items={items} team={team} focusedThreadKey={focusedThreadKey} onFocusThread={setFocusedThreadKey}/>
    <div className="ops-kpis compact"><article><span>WAITING ON MY ACTION</span><strong>{items.filter(i=>i.actions.length>0).length}</strong></article><article><span>OPEN THREADS</span><strong>{items.filter(i=>!closed.has(String(i.record.payload.status))).length}</strong></article><article><span>OVERDUE OPEN THREADS</span><strong>{items.filter(i=>!closed.has(String(i.record.payload.status)) && new Date(String(i.record.payload.due_at))<new Date()).length}</strong></article><article><span>PRESERVED THREADS</span><strong>{items.length}</strong></article></div>
    <div className="coord-filters"><label>Coordination scope<select value={scope} onChange={e=>setScope(e.target.value)}><option value="open">Open threads</option><option value="mine">My available actions</option><option value="all">All, including closed</option></select></label><label>Thread type<select value={kind} onChange={e=>setKind(e.target.value)}><option value="all">All types</option>{['handoff','commitment','obligation'].map(k=><option key={k}>{k}</option>)}</select></label><label>Search coordination<input type="search" value={query} onChange={e=>setQuery(e.target.value)}/></label></div>
    {loading && <div className="ops-empty" role="status">Loading accountable threads…</div>}
    {error && <div className="product-error" role="alert">{error}<button onClick={()=>void load().catch(()=>{})}>Retry coordination</button></div>}
    {!loading && !error && !filtered.length && <section className="product-empty"><h2>No threads in this view.</h2><p>Create a handoff for a recorded call, or choose another filter. Only installation members can confirm receipt here; no external message is sent.</p></section>}
    <p className="product-index">{filtered.length} of {items.length} threads · actions checked by the server</p>
    <div className="coord-grid">{filtered.map(item=>{
      const {record} = item, body = record.payload
      const overdue = !closed.has(String(body.status)) && new Date(String(body.due_at))<new Date()
      const opened = selected?.item.record.record_id===record.record_id && selected.item.record.kind===record.kind
      const key = coordinationKey(item)
      const focused = key===focusedThreadKey
      return <article className={`coord-card ${focused?'is-focused':''}`} key={key}>
        <header><span className="product-index">{record.kind} / V{record.revision}</span><span className={`coord-state ${overdue?'overdue':''}`}>{String(body.status)}{overdue?' · overdue':''}</span></header>
        <button type="button" className="coord-focus-link" aria-pressed={focused} onClick={()=>setFocusedThreadKey(focused?'':key)}>{focused?'Clear visual focus':'Focus in visual'}</button>
        <h2>{recordName(record)}</h2><p className="coord-call">{callLabel(body.call_id)}</p>
        <dl><div><dt>Originating party</dt><dd>{member(item.creator_id)}</dd></div><div><dt>{record.kind==='obligation'?'Responsible party':'Recipient'}</dt><dd>{member(body.recipient_id ?? body.assignee_id)}</dd></div><div><dt>Due</dt><dd><time dateTime={String(body.due_at)}>{dateLabel(String(body.due_at))}</time></dd></div></dl>
        <p>{String(body.note || body.clause_reference || 'No additional terms recorded.')}</p>
        {body.review_note && <p><b>Human review</b><br/>{String(body.review_note)}</p>}
        {body.proof && <div className="coord-proof"><b>Recorded evidence</b><p>{String(body.proof)}</p></div>}
        <p className="product-provenance">{record.source} · Recorded {dateLabel(record.known_at)}</p>
        {opened ? <Transition key={`${record.kind}:${record.record_id}:${selected.action.status}`} item={selected.item} action={selected.action} writable={writable && current} onCancel={()=>setSelected(null)} onDone={async()=>{await load(); await onRefresh(); setSelected(null)}}/> : <div className="product-actions">{item.actions.map(action=><button key={action.status} disabled={!writable || !current} onClick={()=>setSelected({item,action})}>{action.label}</button>)}{!item.actions.length && <small>{closed.has(String(body.status))?'Closed record · preserved in Evidence':'No action available to your account in this state.'}</small>}</div>}
      </article>
    })}</div>
    <aside className="product-boundary"><b>Acknowledgement is a named-party assertion.</b><p>It is not proof of physical execution, legal acceptance, external delivery or a financial return.</p></aside>
  </div>
}
