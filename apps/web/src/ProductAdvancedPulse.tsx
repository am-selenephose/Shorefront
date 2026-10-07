import {lazy,Suspense,useEffect,useState} from 'react'
import {dateLabel,productRequest,recordName,type Fact,type Workspace} from './productClient'
import ProductOperationsDeck from './ProductOperationsDeck'
const ProductHarborMap=lazy(()=>import('./ProductHarborMap'))

type Actions={
  writable:boolean
  onCreate:(kind:string,payload?:Fact['payload'])=>void
  onEdit:(record:Fact)=>void
}

const text=(value:unknown)=>value==null?'':String(value)
const activeCall=(record:Fact)=>record.kind==='call'&&!['departed','cancelled'].includes(text(record.payload.status))
const closed=new Set(['done','resolved','acknowledged','fulfilled','cancelled','declined','completed'])
const pending=(record:Fact)=>record.kind==='incident'?record.payload.status!=='resolved':record.kind==='resource'?record.payload.available===false:['task','handoff','commitment','obligation'].includes(record.kind)&&!closed.has(text(record.payload.status))
const find=(records:Fact[],kind:string,id:unknown)=>records.find(record=>record.kind===kind&&record.record_id===id)

export default function ProductAdvancedPulse({workspace,simulated=false,...actions}:{workspace:Workspace;simulated?:boolean}&Actions){
  const records=workspace.records
  const calls=records.filter(activeCall).sort((a,b)=>new Date(text(a.payload.eta)).getTime()-new Date(text(b.payload.eta)).getTime())
  const berths=records.filter(record=>record.kind==='berth')
  const mapped=berths.filter(record=>typeof record.payload.latitude==='number'&&typeof record.payload.longitude==='number').length
  const sources=new Set(records.map(record=>record.source).filter(Boolean)).size
  const [selectedId,setSelectedId]=useState('')
  const [horizonHours,setHorizonHours]=useState(24)
  const [sourceConflicts,setSourceConflicts]=useState<number|null>(simulated?0:null)

  useEffect(()=>{
    if(simulated){setSourceConflicts(0);return}
    let active=true
    void productRequest<{id:string}[]>('/reconciliation/conflicts?state=unresolved')
      .then(rows=>{if(active)setSourceConflicts(Array.isArray(rows)?rows.length:null)})
      .catch(()=>{if(active)setSourceConflicts(null)})
    return()=>{active=false}
  },[records,simulated])

  useEffect(()=>{
    if(!calls.length){if(selectedId)setSelectedId('');return}
    if(!calls.some(call=>call.record_id===selectedId))setSelectedId(calls[0].record_id)
  },[calls,selectedId])

  const selected=calls.find(call=>call.record_id===selectedId)??calls[0]
  const selectedVessel=selected?find(records,'vessel',selected.payload.vessel_id):undefined
  const selectedBerth=selected?find(records,'berth',selected.payload.berth_id):undefined
  const selectedThreads=selected?records.filter(record=>record.payload.call_id===selected.record_id&&pending(record)):[]
  const selectedIncidents=selectedThreads.filter(record=>record.kind==='incident')
  const latest=[...records].filter(record=>record.known_at).sort((a,b)=>new Date(b.known_at).getTime()-new Date(a.known_at).getTime())[0]
  const unassigned=calls.filter(call=>!call.payload.berth_id).length
  const unmapped=Math.max(0,berths.length-mapped)
  const validStarts=calls.map(call=>new Date(text(call.payload.eta)).getTime()).filter(Number.isFinite)
  const horizonStart=validStarts.length?Math.min(...validStarts):Date.now()
  const horizonEnd=horizonStart+horizonHours*3600000
  const timelineCalls=calls.filter(call=>{
    const eta=new Date(text(call.payload.eta)).getTime()
    const rawEnd=new Date(text(call.payload.etd)).getTime()
    const etd=Number.isFinite(rawEnd)?rawEnd:eta+3600000
    return Number.isFinite(eta)&&etd>=horizonStart&&eta<=horizonEnd
  })
  const timePct=(value:number)=>Math.max(0,Math.min(100,(value-horizonStart)/(horizonEnd-horizonStart)*100))

  return <>
    <section className="ops-command-center" role="region" aria-label="Port operations command center">
      <section className="ops-decision-cockpit" role="region" aria-label="Operational decision cockpit">
        <div className="ops-command-map ops-panel">
          <header><div><span className="product-index">GEOSPATIAL OPERATING PICTURE</span><h2>{records.find(record=>record.kind==='port')?recordName(records.find(record=>record.kind==='port')!):'Port geography'}</h2></div><div className="ops-map-metrics"><span>{mapped}/{berths.length} BERTHS MAPPED</span><b>{calls.length} ACTIVE CALLS</b></div></header>
          <Suspense fallback={<div className="coord-map-loading" role="status">Loading operational map…</div>}><ProductHarborMap facts={records} focusedCallId={selected?.record_id??''} writable={actions.writable} onCreate={actions.onCreate} onEdit={actions.onEdit}/></Suspense>
          <section className="ops-operating-horizon" role="region" aria-label="Port operating horizon">
            <header><div><span className="product-index">BERTH HORIZON / RECORDED WINDOWS</span><h3>Operating horizon</h3></div><div className="ops-horizon-switch" aria-label="Operating horizon range">{[6,12,24,48].map(value=><button type="button" key={value} className={horizonHours===value?'active':''} aria-pressed={horizonHours===value} onClick={()=>setHorizonHours(value)}>{value}H</button>)}</div></header>
            <div className="ops-horizon-scroll" role="group" aria-label="Scrollable berth timeline" tabIndex={0}>
              <div className="ops-horizon-axis"><span>{dateLabel(new Date(horizonStart).toISOString())}</span><span>+{Math.round(horizonHours/2)}h</span><span>+{horizonHours}h</span></div>
              {berths.length?<div className="ops-horizon-lanes">{berths.slice(0,8).map(berth=>{
                const berthCalls=timelineCalls.filter(call=>call.payload.berth_id===berth.record_id)
                return <div className="ops-horizon-lane" key={berth.record_id}><div className="ops-horizon-berth"><b>{recordName(berth)}</b><small>{typeof berth.payload.latitude==='number'&&typeof berth.payload.longitude==='number'?'GEO':'NO GEO'}</small></div><div className="ops-horizon-track">{berthCalls.map(call=>{
                  const eta=new Date(text(call.payload.eta)).getTime()
                  const rawEnd=new Date(text(call.payload.etd)).getTime()
                  const etd=Number.isFinite(rawEnd)?rawEnd:eta+3600000
                  const vessel=find(records,'vessel',call.payload.vessel_id)
                  const left=timePct(eta),right=timePct(etd),width=Math.max(3,right-left)
                  return <button type="button" key={call.record_id} className={`ops-horizon-call${selected?.record_id===call.record_id?' is-focused':''}`} style={{left:`${left}%`,width:`${width}%`}} onClick={()=>setSelectedId(call.record_id)}><b>{vessel?recordName(vessel):call.record_id}</b><span>{text(call.payload.status)}</span></button>
                })}</div></div>
              })}</div>:<div className="ops-empty small"><b>No berth horizon yet.</b><p>Record berths and calls to build the operating timeline.</p></div>}
            </div>
          </section>
        </div>

        <aside className="ops-focus-panel ops-panel">
          <header><div><span className="product-index">NEXT MOVEMENTS</span><h2>Arrival runway</h2></div><b>{calls.length}</b></header>
          {selected?<article className="ops-call-focus"><span className="product-index">SELECTED CALL</span><h2>Call focus</h2><h3>{selectedVessel?recordName(selectedVessel):selected.record_id}</h3>
            <div className="ops-focus-grid"><div><span>STATUS</span><b>{text(selected.payload.status)||'not recorded'}</b></div><div><span>BERTH</span><b>{selectedBerth?recordName(selectedBerth):'Unassigned'}</b></div><div><span>ETA</span><b>{dateLabel(text(selected.payload.eta))}</b></div><div><span>ETD</span><b>{dateLabel(text(selected.payload.etd))}</b></div><div><span>OPEN WORK</span><b>{selectedThreads.length}</b></div><div><span>INCIDENTS</span><b>{selectedIncidents.length}</b></div></div>
            <div className="ops-focus-source"><span>SOURCE</span><b>{selected.source}</b><small>Known {dateLabel(selected.known_at)}</small></div>
            <div className="ops-focus-actions"><button type="button" disabled={!actions.writable} onClick={()=>actions.onEdit(selected)}>Inspect call</button><a href="#coordination">Open coordination</a></div>
          </article>:<div className="ops-empty small"><b>No active call selected.</b><p>Add a port call to create a focus context.</p></div>}
          {calls.length?<div className="ops-runway-list ops-runway-dense">{calls.slice(0,9).map((call,index)=>{
            const vessel=find(records,'vessel',call.payload.vessel_id)
            const berth=find(records,'berth',call.payload.berth_id)
            const linked=records.filter(record=>record.payload.call_id===call.record_id&&pending(record)).length
            return <div className={`ops-runway-row${selected?.record_id===call.record_id?' is-selected':''}`} key={call.record_id}><button type="button" className="ops-runway-select" onClick={()=>setSelectedId(call.record_id)}><span className="runway-order">{String(index+1).padStart(2,'0')}</span><div><b>{vessel?recordName(vessel):call.record_id}</b><span>{berth?recordName(berth):'Berth unassigned'} · {text(call.payload.status)}</span><small>{dateLabel(text(call.payload.eta))} → {dateLabel(text(call.payload.etd))}</small></div><em className={linked?'has-work':''}>{linked} open</em></button><button type="button" className="ops-runway-inspect" disabled={!actions.writable} aria-label={`Inspect ${vessel?recordName(vessel):call.record_id}`} onClick={()=>actions.onEdit(call)}>↗</button></div>
          })}</div>:null}
        </aside>
      </section>
    </section>

    <section className="ops-truth-ribbon" role="region" aria-label="Operational truth ribbon">
      <div className={sourceConflicts?'is-alert':''}><span>SOURCE CONFLICTS</span><b>{sourceConflicts==null?'—':sourceConflicts}</b><small>{sourceConflicts==null?'reconciliation unavailable':sourceConflicts?'human review required':'no unresolved disagreement'}</small></div>
      <div><span>LATEST RECORD</span><b>{latest?dateLabel(latest.known_at):'—'}</b><small>{latest?latest.source:'no sourced record yet'}</small></div>
      <div><span>UNASSIGNED CALLS</span><b>{unassigned}</b><small>{unassigned?'berth decision missing':'all active calls assigned'}</small></div>
      <div className={unmapped?'is-warning':''}><span>UNMAPPED BERTHS</span><b>{unmapped}</b><small>{berths.length?`${mapped}/${berths.length} geocoded`:'no berth records'}</small></div>
      <div><span>PROVENANCE</span><b>{sources}</b><small>distinct recorded sources</small></div>
    </section>
    <ProductOperationsDeck records={records} calls={calls} selectedId={selected?.record_id??''} onSelect={setSelectedId} sourceConflicts={sourceConflicts} writable={actions.writable} onEdit={actions.onEdit}/>
  </>
}
