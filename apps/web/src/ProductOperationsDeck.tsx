import {useMemo,useState} from 'react'
import {dateLabel,recordName,type Fact} from './productClient'

type Actions={
  writable:boolean
  onEdit:(record:Fact)=>void
}

type Props=Actions & {
  records:Fact[]
  calls:Fact[]
  selectedId:string
  onSelect:(id:string)=>void
  sourceConflicts:number|null
}

const text=(value:unknown)=>value==null?'':String(value)
const closed=new Set(['done','resolved','acknowledged','fulfilled','cancelled','declined','completed'])
const pending=(record:Fact)=>record.kind==='incident'
  ? record.payload.status!=='resolved'
  : record.kind==='resource'
    ? record.payload.available===false
    : ['task','handoff','commitment','obligation'].includes(record.kind)&&!closed.has(text(record.payload.status))
const find=(records:Fact[],kind:string,id:unknown)=>records.find(record=>record.kind===kind&&record.record_id===id)

export default function ProductOperationsDeck({records,calls,selectedId,onSelect,sourceConflicts,writable,onEdit}:Props){
  const [lens,setLens]=useState<'all'|'attention'|'unassigned'>('all')
  const [query,setQuery]=useState('')
  const [eventWindow,setEventWindow]=useState<'6h'|'24h'|'all'>('24h')

  const selected=calls.find(call=>call.record_id===selectedId)??calls[0]
  const resources=useMemo(()=>records.filter(record=>record.kind==='resource'),[records])
  const openWork=useMemo(()=>records.filter(pending),[records])
  const selectedWork=selected?openWork.filter(record=>record.payload.call_id===selected.record_id):[]
  const unavailable=resources.filter(resource=>resource.payload.available===false)

  const filteredCalls=calls.filter(call=>{
    const vessel=find(records,'vessel',call.payload.vessel_id)
    const berth=find(records,'berth',call.payload.berth_id)
    const linked=openWork.filter(record=>record.payload.call_id===call.record_id)
    const haystack=`${recordName(vessel??call)} ${call.record_id} ${berth?recordName(berth):''} ${call.source}`.toLowerCase()
    if(query&&!haystack.includes(query.toLowerCase())) return false
    if(lens==='attention'&&!linked.length) return false
    if(lens==='unassigned'&&call.payload.berth_id) return false
    return true
  })

  const now=Date.now()
  const windowMs=eventWindow==='6h'?6*3600000:eventWindow==='24h'?24*3600000:Infinity
  const events=[...records]
    .filter(record=>{
      if(!record.known_at) return false
      if(['task','handoff','commitment','obligation'].includes(record.kind)&&!pending(record)) return false
      if(record.kind==='incident'&&!pending(record)) return false
      if(eventWindow==='all') return true
      const known=new Date(record.known_at).getTime()
      return Number.isFinite(known)&&now-known<=windowMs
    })
    .sort((a,b)=>new Date(b.known_at).getTime()-new Date(a.known_at).getTime())
    .slice(0,9)

  const nextActions:{key:string;label:string;detail:string;kind:'link'|'record';target:string|Fact}[]=[]
  if((sourceConflicts??0)>0) nextActions.push({key:'conflicts',label:'Review source disagreements',detail:`${sourceConflicts} unresolved conflict${sourceConflicts===1?'':'s'} require human reconciliation`,kind:'link',target:'#evidence'})
  if(selected&&!selected.payload.berth_id) nextActions.push({key:'berth',label:'Assign selected call to a berth',detail:'The active call has no recorded berth assignment',kind:'record',target:selected})
  const firstIncident=selectedWork.find(record=>record.kind==='incident')
  if(firstIncident) nextActions.push({key:'incident',label:'Review selected-call incident',detail:recordName(firstIncident),kind:'record',target:firstIncident})
  const firstCoordination=selectedWork.find(record=>['handoff','commitment','obligation'].includes(record.kind))
  if(firstCoordination) nextActions.push({key:'coordination',label:'Open accountable coordination',detail:recordName(firstCoordination),kind:'link',target:'#coordination'})
  if(unavailable[0]) nextActions.push({key:'resource',label:'Resolve unavailable resource',detail:recordName(unavailable[0]),kind:'record',target:unavailable[0]})
  if(!nextActions.length) nextActions.push({key:'clear',label:'No unresolved decision trigger recorded',detail:'Continue monitoring sourced calls, resources and conflicts',kind:'link',target:'#calls'})

  return <section className="ops-operations-deck" role="region" aria-label="Integrated operations deck">
    <header className="ops-deck-toolbar">
      <div><span className="product-index">INTEGRATED OPERATIONS DECK</span><h2>Lineup, resources, events and decision context</h2></div>
      <label className="ops-deck-search">Search operating picture<input type="search" value={query} onChange={event=>setQuery(event.target.value)} placeholder="Vessel, berth, source or call"/></label>
      <div className="ops-view-lenses" role="group" aria-label="Operational saved views">
        {([['all','All'],['attention','Needs attention'],['unassigned','Unassigned']] as const).map(([value,label])=><button type="button" key={value} aria-pressed={lens===value} onClick={()=>setLens(value)}>{label}</button>)}
      </div>
    </header>

    <div className="ops-operations-grid">
      <section className="ops-panel ops-lineup-panel" aria-label="Operational lineup">
        <header><div><span className="product-index">LINEUP / SOURCE-AWARE REGISTER</span><h3>Operational lineup</h3></div><b>{filteredCalls.length}/{calls.length}</b></header>
        {filteredCalls.length?<div className="ops-lineup-scroll"><table><thead><tr><th>Vessel</th><th>Berth</th><th>Status</th><th>ETA → ETD</th><th>Open</th><th>Source</th></tr></thead><tbody>{filteredCalls.map(call=>{
          const vessel=find(records,'vessel',call.payload.vessel_id)
          const berth=find(records,'berth',call.payload.berth_id)
          const linked=openWork.filter(record=>record.payload.call_id===call.record_id)
          return <tr key={call.record_id} className={selected?.record_id===call.record_id?'is-selected':''} onClick={()=>onSelect(call.record_id)}>
            <td><button type="button" onClick={()=>onSelect(call.record_id)}><b>{recordName(vessel??call)}</b><small>{call.record_id}</small></button></td>
            <td>{berth?recordName(berth):<span className="ops-lineup-warning">Unassigned</span>}</td>
            <td><span className={`ops-status-pill ${text(call.payload.status)}`}>{text(call.payload.status)||'not recorded'}</span></td>
            <td><time>{dateLabel(text(call.payload.eta))}</time><span>→</span><time>{dateLabel(text(call.payload.etd))}</time></td>
            <td><b className={linked.length?'ops-count-alert':''}>{linked.length}</b></td>
            <td><span className="ops-source-chip">{call.source}</span></td>
          </tr>
        })}</tbody></table></div>:<div className="ops-empty small">No calls match this operating lens.</div>}
      </section>

      <section className="ops-panel ops-resource-board" aria-label="Resource lanes">
        <header><div><span className="product-index">RESOURCE BOARD / RECORDED AVAILABILITY</span><h3>Resource lanes</h3></div><b>{resources.length}</b></header>
        <div className="ops-resource-lanes">{resources.length?resources.slice(0,8).map(resource=>{
          const linkedTasks=records.filter(record=>record.kind==='task'&&record.payload.resource_id===resource.record_id&&pending(record)).length
          const available=resource.payload.available!==false
          return <button type="button" key={resource.record_id} disabled={!writable} onClick={()=>onEdit(resource)} className={available?'is-available':'is-unavailable'}>
            <span>{text(resource.payload.resource_type)||'resource'}</span><b>{recordName(resource)}</b><em>{available?'AVAILABLE':'UNAVAILABLE'}</em><small>{linkedTasks?`${linkedTasks} open linked task${linkedTasks===1?'':'s'}`:resource.source}</small>
          </button>
        }):<div className="ops-empty small">No operational resources recorded.</div>}</div>
      </section>

      <section className="ops-panel ops-event-scrubber" aria-label="Operational event scrubber">
        <header><div><span className="product-index">EVENT SCRUBBER / TWO-CLOCK RECORD</span><h3>Event scrubber</h3></div><div className="ops-event-window">{(['6h','24h','all'] as const).map(value=><button type="button" key={value} aria-pressed={eventWindow===value} onClick={()=>setEventWindow(value)}>{value.toUpperCase()}</button>)}</div></header>
        <div className="ops-event-rail">{events.length?events.map((record,index)=><article key={`${record.kind}:${record.record_id}:${record.revision}`}><i className={index===0?'is-latest':''}/><time>{dateLabel(record.known_at)}</time><div><span>{record.kind.toUpperCase()} · V{record.revision}</span><b>{recordName(record)}</b><small>{record.source} · valid {dateLabel(record.valid_at)}</small></div></article>):<div className="ops-empty small">No records in this event window.</div>}</div>
      </section>

      <section className="ops-panel ops-decision-lane" aria-label="Operator decision lane">
        <header><div><span className="product-index">NEXT ACTION / HUMAN AUTHORITY</span><h3>Operator decision lane</h3></div><b>{nextActions.length}</b></header>
        <div className="ops-decision-list">{nextActions.slice(0,5).map((item,index)=><article key={item.key}><span>{String(index+1).padStart(2,'0')}</span><div><b>{item.label}</b><small>{item.detail}</small></div>{item.kind==='link'?<a href={String(item.target)}>Open →</a>:<button type="button" disabled={!writable} onClick={()=>onEdit(item.target as Fact)}>Inspect →</button>}</article>)}</div>
        <footer><span>AUTHORITY</span><b>Operator / supervisor remains in control</b><small>No autonomous vessel or terminal actuation path.</small></footer>
      </section>
    </div>
  </section>
}
