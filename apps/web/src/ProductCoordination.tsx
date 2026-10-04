import {useCallback, useEffect, useRef, useState, type FormEvent} from 'react'
import {dateLabel, productRequest, recordName, type Fact, type User} from './productClient'

type Action = {status:string; label:string; requires_proof:boolean; requires_review:boolean}
type Item = {record:Fact; creator_id:string; actions:Action[]}
const closed = new Set(['acknowledged','fulfilled','declined','cancelled','completed'])

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
      return <article className="coord-card" key={`${record.kind}:${record.record_id}`}>
        <header><span className="product-index">{record.kind} / V{record.revision}</span><span className={`coord-state ${overdue?'overdue':''}`}>{String(body.status)}{overdue?' · overdue':''}</span></header>
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
