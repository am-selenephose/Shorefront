import {useEffect,useMemo,useState} from 'react'
import {dateLabel,productRequest,recordName,type Fact,type Workspace} from './productClient'

type Check={code:string;label:string;state:'recorded'|'missing'|'attention'|'conflict';explanation:string;record_kind:string|null;record_id:string|null}
type CallReview={call_id:string;call_status:string;vessel_name:string;berth_name:string|null;eta:string;etd:string;call_source:string;known_at:string;assessment:'recorded'|'incomplete'|'attention'|'conflict';coverage:number;total_checks:number;checks:Check[]}
type ReadinessReport={read_at:string;scope:string;summary:{active_calls:number;conflicted_calls:number;attention_calls:number;incomplete_calls:number;fully_recorded_calls:number};calls:CallReview[]}
type Props={workspace:Workspace;writable:boolean;onCreate:(kind:string,payload?:Fact['payload'])=>void;onEdit:(fact:Fact)=>void}
type Lens='all'|'conflict'|'attention'|'incomplete'|'recorded'
const lenses:{value:Lens;label:string}[]=[
  {value:'all',label:'Every call'},
  {value:'conflict',label:'Conflicts'},
  {value:'attention',label:'Needs action'},
  {value:'incomplete',label:'Missing facts'},
  {value:'recorded',label:'Fully recorded'},
]
const label:{[state:string]:string}={recorded:'Recorded',incomplete:'Incomplete',attention:'Action needed',conflict:'Conflict',missing:'Unknown'}

function StateLabel({state}:{state:string}){
  return <span className={'readiness-state is-'+state}><i aria-hidden="true"/>{label[state]??state}</span>
}

export default function ProductReadiness({workspace,writable,onCreate,onEdit}:Props){
  const [report,setReport]=useState<ReadinessReport|null>(null)
  const [error,setError]=useState('')
  const [loading,setLoading]=useState(true)
  const [retry,setRetry]=useState(0)
  const [lens,setLens]=useState<Lens>('all')
  const [query,setQuery]=useState('')
  const [selectedId,setSelectedId]=useState('')
  const [missingOnly,setMissingOnly]=useState(false)

  useEffect(()=>{
    let active=true
    setLoading(true)
    void productRequest<ReadinessReport>('/readiness').then(result=>{
      if(!active)return
      setReport(result);setError('');setLoading(false)
    }).catch(reason=>{
      if(!active)return
      setError(reason instanceof Error?reason.message:'Could not load readiness')
      setLoading(false)
    })
    return ()=>{active=false}
  },[workspace.records,retry])

  const calls=report?.calls??[]
  const visible=useMemo(()=>calls.filter(call=>
    (lens==='all'||call.assessment===lens)&&
    (call.vessel_name+' '+call.berth_name+' '+call.call_id+' '+call.call_source).toLowerCase().includes(query.trim().toLowerCase())
  ),[calls,lens,query])
  const selected=visible.find(call=>call.call_id===selectedId)??visible[0]
  const checks=selected?.checks.filter(check=>!missingOnly||check.state!=='recorded')??[]
  const count=(value:Lens)=>value==='all'?calls.length:calls.filter(call=>call.assessment===value).length
  const related=(check:Check)=>workspace.records.find(f=>f.kind===check.record_kind&&f.record_id===check.record_id)

  return <div className="ops-workspace readiness-workspace" data-product-workspace="readiness">
    <header className="readiness-hero">
      <div className="readiness-hero-copy"><span className="product-index">SHOREFRONT / VERIFIED OPERATING INTELLIGENCE</span>
        <h1>Know what is recorded.<br/>See what is missing.</h1>
        <p>An explainable call-by-call control picture, assembled from your installation's own records. No synthetic traffic, fabricated forecasts or implied clearance.</p>
        <div className="readiness-hero-actions"><button type="button" className="product-primary" disabled={!writable} onClick={()=>onCreate('call')}>+ Plan a port call</button><a href="#coordination">Coordination desk →</a><a href="#evidence">Inspect source history →</a></div>
      </div>
      <aside className="readiness-hero-meta" aria-label="Assessment provenance">
        <span className="product-index">LIVE CUSTOMER RECORDS</span><strong>{report?.read_at?dateLabel(report.read_at):'Connecting...'}</strong>
        <span><i className={error?'is-degraded':'is-verified'}/> {error?'SOURCE UNAVAILABLE':loading?'REFRESHING REVIEW':'RECORD SNAPSHOT'}</span>
        <small>This is information coverage, not navigational safety certification.</small>
      </aside>
    </header>

    <section className="readiness-metrics" aria-label="Recorded call coverage">
      {[
        ['TRACKED CALLS',report?.summary.active_calls??0,'Current recorded schedule','all'],
        ['RECORDED CONFLICTS',report?.summary.conflicted_calls??0,'Overlap / limits require review','conflict'],
        ['NEEDS ACTION',report?.summary.attention_calls??0,'Open recorded work','attention'],
        ['MISSING INFORMATION',report?.summary.incomplete_calls??0,'Absent operating facts','incomplete'],
        ['FULLY RECORDED',report?.summary.fully_recorded_calls??0,'Coverage only, not clearance','recorded']
      ].map(([title,value,detail,target])=><button key={title} type="button" onClick={()=>setLens(target as Lens)} className={'readiness-metric'+(lens===target?' is-active':'')}>
        <span>{title}</span><strong>{value}</strong><small>{detail}</small></button>)}
    </section>

    {error&&<div className="product-error" role="alert">Readiness data cannot be refreshed: {error}. Last validated result is retained. <button type="button" onClick={()=>setRetry(i=>i+1)}>Retry</button></div>}
    <section className="readiness-console" role="region" aria-label="Operational readiness intelligence">
      <header className="readiness-console-toolbar"><div><span className="product-index">CALL CONTROL / RECORDED FACTS</span><h2>Operating coverage register</h2><p>{loading?'Refreshing from durable records...':`${visible.length} of ${calls.length} call reviews in view`}</p></div>
        <label>Find a call<input type="search" aria-label="Search call readiness" placeholder="Vessel, berth, call or source" value={query} onChange={event=>setQuery(event.target.value)}/></label>
      </header>
      <div className="readiness-lenses" role="group" aria-label="Readiness lenses">{lenses.map(item=><button type="button" key={item.value} aria-pressed={lens===item.value} onClick={()=>{setLens(item.value);setMissingOnly(false)}}>{item.label}<b>{count(item.value)}</b></button>)}</div>

      {!calls.length&&!loading&&!error ? <div className="readiness-zero"><span className="product-index">NO CUSTOMER CALLS RECORDED</span><h2>Start with a genuine operating schedule.</h2><p>Add the port, vessel and berth first, then create your first call. The intelligence desk will derive checks from real records; it will not invent a harbor to make this screen look busy.</p><div className="product-actions"><button disabled={!writable} onClick={()=>onCreate('port')}>Add port</button><button disabled={!writable} onClick={()=>onCreate('vessel')}>Add vessel</button><a href="#records">Open records →</a></div></div>
      :!visible.length ? <div className="readiness-zero"><h2>No call matches this lens.</h2><p>Try another filter or search term. Existing records were not changed.</p><button type="button" onClick={()=>{setLens('all');setQuery('')}}>Show all calls</button></div>
      :<div className="readiness-split">
        <div className="readiness-call-list" aria-label="Verified call list">
          {visible.map(call=><button type="button" key={call.call_id} className={'readiness-call'+(selected?.call_id===call.call_id?' is-selected':'')} onClick={()=>{setSelectedId(call.call_id);setMissingOnly(false)}} aria-pressed={selected?.call_id===call.call_id}>
            <span className="readiness-call-top"><span className="readiness-vessel-name">{call.vessel_name}</span><StateLabel state={call.assessment}/></span>
            <span className="readiness-call-meta"><span>{call.berth_name??'No berth assigned'}</span><span>{call.call_status}</span></span>
            <span className="readiness-call-clock"><span>ETA {dateLabel(call.eta)}</span><span>ETD {dateLabel(call.etd)}</span></span>
            <span className="readiness-coverage-meter" aria-label={`${call.coverage} of ${call.total_checks} recorded-information checks`}><span style={{width:`${call.total_checks?100*call.coverage/call.total_checks:0}%`}}/></span>
            <span className="readiness-call-tail"><span>{call.coverage}/{call.total_checks} facts checked</span><span>REVIEW ↗</span></span>
          </button>)}
        </div>
        {selected&&<section className="readiness-inspector" role="region" aria-label="Call evidence review">
          <header className="readiness-inspector-header"><div><span className="product-index">SELECTED CALL / INDEPENDENT FACT CHECK</span><h2>{selected.vessel_name}</h2><span className="readiness-inspector-sub">{selected.berth_name??'Berth not assigned'} · {selected.call_status}</span></div><StateLabel state={selected.assessment}/></header>
          <div className="readiness-inspector-source"><div><span>PRIMARY SOURCE</span><b>{selected.call_source}</b></div><div><span>LAST KNOWN RECORD</span><b>{dateLabel(selected.known_at)}</b></div><div><span>CHECK COVERAGE</span><b>{selected.coverage} of {selected.total_checks}</b></div></div>
          <div className="readiness-review-bar"><div><span className="product-index">EVIDENCE CHECKLIST</span><h3>{missingOnly?'Gaps and open work':'Every evaluated dimension'}</h3></div><button type="button" aria-pressed={missingOnly} onClick={()=>setMissingOnly(v=>!v)}>{missingOnly?'All checks':'Missing coverage'}</button></div>
          <div className="readiness-checks">
            {checks.length?checks.map(check=><article key={check.code} className={'readiness-check is-'+check.state}>
              <span className="readiness-check-icon" aria-hidden="true">{check.state==='recorded'?'✓':check.state==='missing'?'?':'!'}</span>
              <div><header><b>{check.label}</b><StateLabel state={check.state}/></header><p>{check.explanation}</p>
                {related(check)?<button type="button" disabled={!writable} onClick={()=>onEdit(related(check)!)}>Inspect recorded {check.record_kind} ↗</button>:
                  check.code==='port_resources'?<a href="#plan">Review resource planning →</a>:
                  check.code==='coordination'?<a href="#coordination">Open coordination →</a>:
                  check.code==='berth_assignment'?<button type="button" disabled={!writable} onClick={()=>onEdit(workspace.records.find(r=>r.kind==='call'&&r.record_id===selected.call_id)!)}>Review berth assignment ↗</button>:null}
              </div>
            </article>):<div className="readiness-all-covered">No missing or open recorded checks in this review. This does not establish operational safety.</div>}
          </div>
          <footer className="readiness-inspector-foot"><span>VERIFICATION BOUNDARY</span><p>Shorefront analyzes only information explicitly recorded or ingested into this installation. Weather, vessel movements, navigation clearance, resource dependencies and external acknowledgements are not inferred.</p><a href="#evidence">Full provenance and history →</a></footer>
        </section>}
      </div>}
    </section>
  </div>
}
