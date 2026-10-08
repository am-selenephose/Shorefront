import {useEffect,useRef,useState} from 'react'
import {dateLabel,productRequest,recordName,type Fact} from './productClient'

type Conflict={kind:string;record_ids:string[];explanation:string}
type Alternative={berth_id:string|null;berth_name:string|null;eta:string;etd:string;conflicts:Conflict[]}
type Result={call_id:string;vessel_name:string;source:string;known_at:string;read_at:string;read_only:true;baseline:Alternative;candidate:Alternative;change:{berth_changed:boolean;eta_minutes:number;etd_minutes:number};boundary:string}
type Props={facts:Fact[];writable:boolean;onEdit:(record:Fact)=>void}
const clock=(date:unknown)=>{
  if(!date)return''
  const time=new Date(String(date))
  return Number.isFinite(time.getTime())?time.toISOString().slice(0,16):''
}
const delta=(value:number)=>`${value>0?'+':''}${value} min`
const conflictName=(kind:string)=>kind==='berth_overlap'?'Recorded berth overlap':kind==='vessel_overlap'?'Recorded vessel overlap':kind==='berth_limit'?'Recorded dimensional limit':kind.replaceAll('_',' ')

export default function ProductWhatIf({facts,writable,onEdit}:Props){
  const calls=facts.filter(f=>f.kind==='call'&&!['departed','cancelled'].includes(String(f.payload.status)))
  const berths=facts.filter(f=>f.kind==='berth')
  const vessels=facts.filter(f=>f.kind==='vessel')
  const [callId,setCallId]=useState('')
  const selected=calls.find(call=>call.record_id===callId)??calls[0]
  const [berthId,setBerthId]=useState('')
  const [eta,setEta]=useState('')
  const [etd,setEtd]=useState('')
  const [result,setResult]=useState<Result|null>(null)
  const [error,setError]=useState('')
  const [busy,setBusy]=useState(false)
  const generation=useRef(0)
  useEffect(()=>{
    generation.current++
    setBerthId(String(selected?.payload.berth_id??''))
    setEta(clock(selected?.payload.eta))
    setEtd(clock(selected?.payload.etd))
    setResult(null);setError('');setBusy(false)
  },[selected?.record_id,selected?.revision])

  function revise(fn:()=>void){generation.current++;fn();setResult(null);setError('');setBusy(false)}
  async function simulate(){
    if(!selected || !eta || !etd)return
    const requestId=++generation.current
    setBusy(true);setError('');setResult(null)
    try{
      const scenario=await productRequest<Result>('/plan/what-if',{
        call_id:selected.record_id,berth_id:berthId||null,
        eta:new Date(eta+'Z').toISOString(),etd:new Date(etd+'Z').toISOString(),
      })
      if(requestId===generation.current)setResult(scenario)
    }catch(reason){if(requestId===generation.current)setError(reason instanceof Error?reason.message:'Unable to evaluate scenario')}
    finally{if(requestId===generation.current)setBusy(false)}
  }
  const vesselName=(call:Fact)=>recordName(vessels.find(v=>v.record_id===call.payload.vessel_id)??call)
  return <section className="whatif-workspace" role="region" aria-label="What-if berth scenario planning">
    <header className="whatif-heading"><div><span className="product-index">PLAN LAB / HUMAN-APPROVED CHANGE CONTROL</span><h2>Compare a berth plan before it becomes an order.</h2><p>Use the real call ledger to challenge a schedule, inspect added constraints and keep the live plan untouched until a human commits an approved change.</p></div>
      <span className="whatif-status"><i/> READ-ONLY ANALYSIS</span>
    </header>
    <div className="whatif-content">
      <div className="whatif-editor">
        <div className="whatif-editor-top"><span className="product-index">01 / SET PROPOSED CONDITIONS</span><b>{calls.length} active calls</b></div>
        {calls.length?<form onSubmit={event=>{event.preventDefault();void simulate()}}>
          <label>Call to simulate<select value={selected?.record_id??''} onChange={event=>{setCallId(event.target.value)}}>{calls.map(call=><option value={call.record_id} key={call.record_id}>{vesselName(call)} / {call.record_id}</option>)}</select></label>
          <label>Proposed berth<select value={berthId} onChange={event=>revise(()=>setBerthId(event.target.value))}><option value="">Unassigned / no berth</option>{berths.map(berth=><option value={berth.record_id} key={berth.record_id}>{recordName(berth)}</option>)}</select></label>
          <div className="whatif-time-grid"><label>Proposed ETA (UTC)<input type="datetime-local" required value={eta} onChange={event=>revise(()=>setEta(event.target.value))}/></label><label>Proposed ETD (UTC)<input type="datetime-local" required value={etd} onChange={event=>revise(()=>setEtd(event.target.value))}/></label></div>
          <div className="whatif-editor-actions"><button className="product-primary" type="submit" disabled={busy||!selected||!eta||!etd}>{busy?'Checking constraints...':'Compare this scenario'}</button><button type="button" disabled={!selected} onClick={()=>revise(()=>{setBerthId(String(selected?.payload.berth_id??''));setEta(clock(selected?.payload.eta));setEtd(clock(selected?.payload.etd))})}>Reset</button></div>
        </form>:<div className="whatif-empty"><h3>No recorded calls available.</h3><p>Create a real vessel and port call to evaluate a plan. The simulator never inserts test calls into customer records.</p><a href="#records">Open customer records →</a></div>}
        {error&&<p role="alert" className="product-error">{error}</p>}
        <div className="whatif-boundary"><span className="product-index">NOT A TRAFFIC FORECAST</span><p>Calculations use recorded berth windows, vessel overlap and entered dimensions. AIS, tides, pilots, maritime safety, personnel suitability and navigation clearance are not inferred.</p></div>
      </div>
      <div className="whatif-results" aria-label="Scenario comparison">
        {result?<><div className="whatif-results-top"><div><span className="product-index">02 / BEFORE AND AFTER</span><h3>{result.vessel_name}</h3><p>Source: {result.source} · Recorded {dateLabel(result.known_at)}</p></div><span className="whatif-uncommitted">UNCOMMITTED SCENARIO</span></div>
          <div className="whatif-comparison">
            {([['EXISTING PLAN',result.baseline],['PROPOSED PLAN',result.candidate]] as const).map(([title,variant])=><div key={title} className="whatif-variant"><span className="product-index">{title}</span><h4>{variant.berth_name??'Unassigned berth'}</h4><dl><div><dt>Arrival</dt><dd>{dateLabel(variant.eta)}</dd></div><div><dt>Departure</dt><dd>{dateLabel(variant.etd)}</dd></div><div><dt>Recorded conflicts</dt><dd className={variant.conflicts.length?'whatif-issue':''}>{variant.conflicts.length}</dd></div></dl>
              {variant.conflicts.length?<ul>{variant.conflicts.map((conflict,i)=><li key={i}><b>{conflictName(conflict.kind)}</b><span>{conflict.explanation}</span></li>)}</ul>:<p className="whatif-no-conflict">No conflicts found in the limited recorded schedule rules.</p>}</div>)}
          </div>
          <div className="whatif-delta"><div><span>BERTH CHANGE</span><b>{result.change.berth_changed?'Changed':'Unchanged'}</b></div><div><span>ARRIVAL SHIFT</span><b>{delta(result.change.eta_minutes)}</b></div><div><span>DEPARTURE SHIFT</span><b>{delta(result.change.etd_minutes)}</b></div></div>
          <footer><p>Read-only calculation. No underlying record, recipient agreement or approval has changed.</p><button type="button" disabled={!writable} onClick={()=>{const target=facts.find(f=>f.kind==='call'&&f.record_id===result.call_id);if(target)onEdit(target)}}>Open original call editor ↗</button><a href="#evidence">Inspect recorded history →</a></footer>
        </>:<div className="whatif-awaiting"><div className="whatif-diagram" aria-hidden="true"><span>BERTH / A</span><div><i/><i/><i/><i/></div><span>BERTH / B</span></div><span className="product-index">02 / CONSTRAINT COMPARISON</span><h3>Plan changes without committing them.</h3><p>Select a recorded call, adjust berth or UTC timings and compare against its current schedule. Conflicts will appear here with explicit reason codes and preserved provenance.</p></div>}
      </div>
    </div>
  </section>
}
