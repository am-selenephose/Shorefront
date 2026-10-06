import {dateLabel, recordName, type Fact, type User, type Workspace} from './productClient'
import type {OperationalActions} from './ProductWorkspaces'

const text=(value:unknown)=>value==null?'':String(value)
const closed=new Set(['done','resolved','acknowledged','fulfilled','cancelled','declined','completed','departed'])
const activeCall=(record:Fact)=>record.kind==='call'&&!['departed','cancelled'].includes(text(record.payload.status))
const pending=(record:Fact)=>record.kind==='incident'?record.payload.status!=='resolved':record.kind==='resource'?record.payload.available===false:['task','handoff','commitment','obligation'].includes(record.kind)&&!closed.has(text(record.payload.status))
const due=(record:Fact)=>record.payload.due_at?new Date(text(record.payload.due_at)).getTime():Infinity
const owner=(record:Fact,team:User[])=>team.find(user=>user.id===(record.payload.assignee_id??record.payload.recipient_id))?.name??'Unassigned'

export default function ProductCommandRail({workspace,team,...actions}:{workspace:Workspace;team:User[]}&OperationalActions){
  const facts=workspace.records
  const calls=facts.filter(activeCall).sort((a,b)=>new Date(text(a.payload.eta)).getTime()-new Date(text(b.payload.eta)).getTime())
  const attention=facts.filter(pending).sort((a,b)=>due(a)-due(b))
  const resources=facts.filter(record=>record.kind==='resource')
  const berths=facts.filter(record=>record.kind==='berth')
  const mapped=berths.filter(record=>typeof record.payload.latitude==='number'&&typeof record.payload.longitude==='number').length
  const sources=new Set(facts.map(record=>record.source).filter(Boolean)).size
  const find=(kind:string,id:unknown)=>facts.find(record=>record.kind===kind&&record.record_id===id)
  const coverage=berths.length?Math.round(mapped/berths.length*100):0
  return <aside className="product-command-rail" aria-label="Operational status rail">
    <section className="command-rail-section command-rail-now">
      <header><span className="product-index">NOW / NEXT</span><b>{calls.length}</b></header>
      <h2>Arrival runway</h2>
      {calls.length?<div className="command-runway">{calls.slice(0,5).map(call=>{const vessel=find('vessel',call.payload.vessel_id),berth=find('berth',call.payload.berth_id);return <button type="button" key={call.record_id} onClick={()=>actions.onEdit(call)} disabled={!actions.writable}>
        <span><i className={'runway-state '+text(call.payload.status)}/>{vessel?recordName(vessel):call.record_id}</span>
        <strong>{berth?recordName(berth):'Berth unassigned'}</strong>
        <time>{dateLabel(text(call.payload.eta))}</time>
      </button>})}</div>:<div className="command-rail-empty">No active call is recorded.</div>}
    </section>
    <section className="command-rail-section">
      <header><span className="product-index">ATTENTION</span><b>{attention.length}</b></header>
      <div className="command-attention-list">{attention.slice(0,5).map(record=><a href="#exceptions" key={record.kind+':'+record.record_id} className={text(record.payload.severity)||'neutral'}>
        <span>{record.kind}{due(record)<Date.now()?' / overdue':''}</span><b>{recordName(record)}</b><small>{owner(record,team)}</small>
      </a>)}</div>
      {!attention.length&&<div className="command-rail-empty">No unresolved recorded attention.</div>}
    </section>
    <section className="command-rail-section">
      <header><span className="product-index">COVERAGE</span><b>{coverage}%</b></header>
      <div className="command-meter" aria-label={coverage+'% of recorded berths have coordinates'}><i style={{width:coverage+'%'}}/></div>
      <dl className="command-coverage"><div><dt>Geocoded berths</dt><dd>{mapped}/{berths.length}</dd></div><div><dt>Recorded sources</dt><dd>{sources}</dd></div><div><dt>Resources available</dt><dd>{resources.filter(r=>r.payload.available!==false).length}/{resources.length}</dd></div><div><dt>Fact versions in view</dt><dd>{facts.length}</dd></div></dl>
    </section>
    <section className="command-rail-section command-rail-actions">
      <header><span className="product-index">QUICK RECORD</span></header>
      <div><button disabled={!actions.writable} onClick={()=>actions.onCreate('incident')}>Incident</button><button disabled={!actions.writable} onClick={()=>actions.onCreate('task')}>Task</button><button disabled={!actions.writable} onClick={()=>actions.onCreate('handoff')}>Handoff</button></div>
      <p>Every quick action still opens an authoritative sourced record. Nothing is silently inferred.</p>
    </section>
  </aside>
}
