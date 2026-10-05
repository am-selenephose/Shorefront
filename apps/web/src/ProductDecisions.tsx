import {useEffect, useRef, useState, type FormEvent} from 'react'
import {productRequest, dateLabel, recordName, type Fact, type User} from './productClient'
import ProductOutcome from './ProductOutcome'

type Option = {id:string; label:string; eligible:boolean; rejected_reasons:string[]; shift_minutes:number; call_payload:Record<string,string>}
type Packet = {id:string; created_at:string; question:string; call_id:string; input_digest:string; inputs:Fact[]; options:Option[]; trust:{confidence:string; warnings:string[]}; receipt:{approved_by:string; approved_at:string; reason:string; option_id:string; effect:string}|null}
type HistoryQuery = {q:string; state:'all'|'pending'|'approved'; after:string; trail:string[]}
const firstPage:HistoryQuery = {q:'',state:'all',after:'',trail:[]}
const pageSize = 25

export default function ProductDecisions({facts, user, writable, onRefresh}: {facts:Fact[]; user:User; writable:boolean; onRefresh:()=>Promise<void>}) {
  const [packets, setPackets] = useState<Packet[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loaded, setLoaded] = useState(false)
  const [listError, setListError] = useState('')
  const [notice, setNotice] = useState('')
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<HistoryQuery['state']>('all')
  const [viewQuery, setViewQuery] = useState<HistoryQuery>(firstPage)
  const [more, setMore] = useState(false)
  const requested = useRef<HistoryQuery>(firstPage)
  const generation = useRef(0)
  const [selected, setSelected] = useState<string|null>(null)
  const attempt = useRef<{intent:string; key:string}|null>(null)
  async function load(query:HistoryQuery=requested.current) {
    requested.current=query
    const requestGeneration=++generation.current
    setLoading(true); setListError('')
    try {
      const params=new URLSearchParams({limit:String(pageSize+1),after:query.after,q:query.q,state:query.state})
      const result=await productRequest<Packet[]>(`/decisions?${params}`)
      if (!Array.isArray(result) || !result.every(p=>p && typeof p.id==='string' && typeof p.question==='string' && Array.isArray(p.inputs) && Array.isArray(p.options) && Array.isArray(p.trust?.warnings))) throw new Error('Invalid decision response')
      if(requestGeneration!==generation.current)return
      setPackets(result.slice(0,pageSize)); setMore(result.length>pageSize); setViewQuery(query); setLoaded(true); setSelected(null)
      return true
    } catch (failure) {if(requestGeneration===generation.current)setListError(String(failure))}
    finally {if(requestGeneration===generation.current)setLoading(false)}
  }
  useEffect(() => {void load(); return()=>{generation.current++}}, [])
  async function propose(event:FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError('')
    const body = Object.fromEntries(new FormData(event.currentTarget))
    const intent = JSON.stringify(body)
    if (attempt.current?.intent !== intent) attempt.current = {intent, key:crypto.randomUUID()}
    try {const packet = await productRequest<Packet>('/decisions', body, attempt.current.key); setSearch(packet.id);setStatus('all'); const refreshed=await load({...firstPage,q:packet.id}); setSelected(packet.id);setNotice(refreshed?'Decision packet recorded. History is filtered to the new packet.':'Decision packet recorded, but history did not refresh. Retry decision history; do not submit the packet again.')}
    catch (failure) {setError(String(failure))} finally {setBusy(false)}
  }
  async function approve(event:FormEvent<HTMLFormElement>, packet:Packet) {
    event.preventDefault(); setBusy(true); setError('')
    try {await productRequest(`/decisions/${packet.id}/approve`, Object.fromEntries(new FormData(event.currentTarget))); await load(); setSelected(packet.id);setNotice('Approval recorded. Use the Approved history filter to find approved packets.'); await onRefresh()}
    catch (failure) {setError(String(failure))} finally {setBusy(false)}
  }
  const planned = facts.filter(f => f.kind === 'call' && f.payload.status === 'planned')
  return <><p className="eyebrow">PLAN / EVIDENCE-BOUND REVIEW</p><h1>A decision with its context intact.</h1><p>Compare recorded berth windows. A supervisor approves the plan; Shorefront never treats that as vessel clearance or a financial return.</p>
    <section className="product-card"><h2>Create a decision packet</h2><form onSubmit={propose}><fieldset disabled={!writable || busy}><div className="product-form-grid"><label>Planned call<select name="call_id" required><option value="">Select a planned call</option>{planned.map(c => <option value={c.record_id} key={c.record_id}>{recordName(facts.find(f => f.kind === 'vessel' && f.record_id === c.payload.vessel_id) ?? c)} · {dateLabel(String(c.payload.eta))}</option>)}</select></label><label>Decision question<input name="question" required maxLength={1000} defaultValue="Which recorded berth window should we use?"/></label></div><button className="product-primary">{busy ? 'Working…' : 'Prepare decision packet'}</button></fieldset></form>{!planned.length && <p>Create a planned port call in Records to start a review.</p>}</section>
    {error && <p className="product-error" role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    <section className="product-card" aria-label="Decision history">
      <h2>Decision history</h2>
      <p>Search all recorded packets by question, call ID or packet ID. Pages use stable packet-ID order, not chronological order. Refresh to include newly recorded packets.</p>
      <form onSubmit={e=>{e.preventDefault();setNotice('');void load({...firstPage,q:search.trim(),state:status})}}>
        <div className="product-form-grid"><label>Search decision history<input type="search" maxLength={200} value={search} onChange={e=>setSearch(e.target.value)}/></label>
        <label>Decision status<select value={status} onChange={e=>setStatus(e.target.value as HistoryQuery['state'])}><option value="all">All decisions</option><option value="pending">Pending review</option><option value="approved">Approved</option></select></label></div>
        <div className="product-actions"><button type="submit" disabled={busy}>Search packets</button><button type="button" disabled={busy || loading} onClick={()=>{setSearch('');setStatus('all');setNotice('');void load(firstPage)}}>Clear search</button><button type="button" disabled={busy || loading} onClick={()=>void load({...viewQuery,after:'',trail:[]})}>Refresh history</button></div>
      </form>
      <p role="status">{loaded?`Page ${viewQuery.trail.length+1} · ${packets.length} packets${viewQuery.q?` · Search: ${viewQuery.q}`:''} · ${viewQuery.state}`:'No page loaded'}{loading?' · Loading decision evidence…':''}</p>
      {listError && <div className="product-error" role="alert">{listError}<p>{loaded?'The last loaded page remains visible; it does not represent the failed request.':'Decision history has not loaded.'}</p><button disabled={loading} onClick={()=>void load()}>Retry decision history</button></div>}
      <div className="product-actions"><button disabled={busy || loading || !!listError || !viewQuery.trail.length} onClick={()=>void load({...viewQuery,after:viewQuery.trail.at(-1)!,trail:viewQuery.trail.slice(0,-1)})}>Previous page</button><button disabled={busy || loading || !!listError || !more} onClick={()=>void load({...viewQuery,after:packets.at(-1)!.id,trail:[...viewQuery.trail,viewQuery.after]})}>Next page</button></div>
    </section>
    {!loading && !listError && loaded && !packets.length && <div className="product-empty"><h2>{viewQuery.q || viewQuery.state!=='all' || viewQuery.after?'No matching decisions.':'No decisions recorded yet.'}</h2><p>A packet preserves the inputs, choices and limitations reviewed at that moment. Adjust the filters or refresh history.</p></div>}
    {packets.map(packet => <section className="product-card product-packet" key={packet.id}><div className="product-section-heading"><div><span className="product-index">{packet.receipt ? 'APPROVED PLAN' : 'AWAITING REVIEW'} / {dateLabel(packet.created_at)}</span><h2>{packet.question}</h2></div><button onClick={() => setSelected(selected === packet.id ? null : packet.id)} aria-expanded={selected === packet.id}>{selected === packet.id ? 'Close packet' : 'Review packet'}</button></div>
      {selected === packet.id && <><div className="product-boundary"><b>Confidence: {packet.trust.confidence}</b><ul>{packet.trust.warnings.map(w => <li key={w}>{w}</li>)}</ul><code>Input fingerprint: {packet.input_digest}</code><p>{packet.inputs.length} original facts preserved.</p></div><div className="product-record-grid">{packet.options.map(option => <article className="product-card" key={option.id}><span className="product-index">{option.eligible ? 'AVAILABLE FOR HUMAN REVIEW' : 'REJECTED BY RECORDED CONSTRAINTS'}</span><h3>{option.label}</h3><p>Schedule shift: {option.shift_minutes} minutes</p><p>{dateLabel(option.call_payload.eta)} → {dateLabel(option.call_payload.etd)}</p>{option.rejected_reasons.map(reason => <p key={reason}>{reason}</p>)}</article>)}</div>
        {packet.receipt ? <div className="product-boundary"><h3>Approval recorded</h3><p>{packet.receipt.reason}</p><p>{dateLabel(packet.receipt.approved_at)} · {packet.receipt.effect.replaceAll('_',' ')}</p></div> : <form onSubmit={e => void approve(e, packet)}><fieldset disabled={busy || loading || !!listError || !writable || user.role !== 'supervisor'}><div className="product-form-grid"><label>Option to approve<select name="option_id" required><option value="">Select an eligible option</option>{packet.options.filter(o => o.eligible).map(o => <option key={o.id} value={o.id}>{o.label}</option>)}</select></label><label>Approval reason<input name="reason" required maxLength={2000}/></label></div><button className="product-primary">Approve recorded plan</button></fieldset>{user.role !== 'supervisor' && <p>A supervisor account is required. Administrator access alone cannot approve this decision.</p>}</form>}
        {packet.receipt && <ProductOutcome decisionId={packet.id} expected={packet.options.find(o => o.id === packet.receipt?.option_id)!.call_payload as {eta:string; etd:string}} existing={facts.find(f => f.kind === 'outcome' && f.payload.decision_id === packet.id)} writable={writable} onRefresh={onRefresh}/>}
      </>}
    </section>)}
  </>
}
