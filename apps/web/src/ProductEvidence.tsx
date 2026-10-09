import {useCallback,useEffect,useRef,useState,type FormEvent} from 'react'
import {dateLabel,productRequest,recordName,validateWorkspace,type Fact,type User,type Workspace} from './productClient'
import './ProductEvidence.css'

const show = (value:unknown)=>value==null?'Not recorded':String(value)
type FactConflict = {
  id:string; kind:string; record_id:string; fields:string[]; detected_at:string;
  state:'unresolved'|'resolved'; resolved_at:string|null; resolved_by:string|null;
  accepted_revision:number|null; resolution_note:string|null; resolution_revision:number|null;
  baseline:Fact; challenger:Fact;
}
function FactDetails({record,team}:{record:Fact;team:User[]}) {
  const actor=team.find(u=>u.id===record.actor_id)
  return <div className="evidence-detail"><dl className="evidence-values">{Object.entries(record.payload).map(([key,value])=><div key={key}><dt>{key.replaceAll('_',' ')}</dt><dd>{show(value)}</dd></div>)}</dl>
    <dl className="evidence-provenance"><div><dt>Source</dt><dd>{record.source}</dd></div><div><dt>Recorded by</dt><dd>{actor?.name ?? 'Recorded actor'} <code>{record.actor_id}</code></dd></div><div><dt>Known at</dt><dd><time dateTime={record.known_at}>{record.known_at}</time></dd></div><div><dt>Effective at</dt><dd><time dateTime={record.valid_at}>{record.valid_at}</time></dd></div></dl></div>
}

function ConflictReview({conflict,team,writable,onResolved}:{conflict:FactConflict;team:User[];writable:boolean;onResolved:(conflict:FactConflict)=>Promise<void>}) {
  const [note,setNote]=useState(''), [busy,setBusy]=useState(false), [error,setError]=useState('')
  const changed=(record:Fact)=>conflict.fields.map(field=><div key={field}><dt>{field.replaceAll('_',' ')}</dt><dd>{show(record.payload[field])}</dd></div>)
  async function resolve(revision:number) {
    if(!note.trim())return
    setBusy(true);setError('')
    try {
      const resolved=await productRequest<FactConflict>(`/reconciliation/conflicts/${conflict.id}/resolve`,{accepted_revision:revision,note:note.trim()},crypto.randomUUID())
      await onResolved(resolved)
    } catch(failure) {setError(failure instanceof Error?failure.message:String(failure))}
    finally {setBusy(false)}
  }
  return <article className="reconciliation-card" data-conflict-id={conflict.id}>
    <header><div><span className="product-index">SOURCE DISAGREEMENT / {conflict.kind.toUpperCase()}</span><h3>{recordName(conflict.challenger)}</h3></div><span className={`reconciliation-state ${conflict.state}`}>{conflict.state.toUpperCase()}</span></header>
    <p className="product-small">Detected {dateLabel(conflict.detected_at)} · changed {conflict.fields.map(field=>field.replaceAll('_',' ')).join(', ')}</p>
    <div className="reconciliation-versions">
      {[conflict.baseline,conflict.challenger].map((record,index)=>{
        const actor=team.find(member=>member.id===record.actor_id)
        return <section key={record.revision} aria-label={`${index?'Challenger':'Baseline'} version ${record.revision}`}>
          <span className="product-index">{index?'CHALLENGER':'BASELINE'} / V{record.revision}</span>
          <dl className="reconciliation-fields">{changed(record)}</dl>
          <div className="reconciliation-provenance"><b>{record.source}</b><span>{actor?.name??record.actor_id}</span><span>Recorded {dateLabel(record.known_at)}</span><span>Effective {dateLabel(record.valid_at)}</span></div>
          {conflict.state==='unresolved'&&<button disabled={!writable||busy||!note.trim()} onClick={()=>void resolve(record.revision)}>Accept V{record.revision}</button>}
        </section>
      })}
    </div>
    {conflict.state==='unresolved'?<div className="reconciliation-resolution"><label>Resolution note<textarea value={note} maxLength={2000} required onChange={event=>setNote(event.target.value)} placeholder="Record who confirmed the accepted fact and why."/></label>{!writable&&<p>Operational reconciliation authority is required to resolve this disagreement.</p>}{error&&<p className="product-error" role="alert">{error}</p>}</div>:
      <div className="reconciliation-resolution resolved"><b>Accepted V{conflict.accepted_revision}</b><p>{conflict.resolution_note}</p><span>{conflict.resolved_at?`Resolved ${dateLabel(conflict.resolved_at)}`:'Resolved'}{conflict.resolution_revision?` · materialized as V${conflict.resolution_revision}`:''}</span></div>}
  </article>
}

export default function ProductEvidence({facts,team,user,writable,onRefresh}:{facts:Fact[];team:User[];user:User;writable:boolean;onRefresh:()=>Promise<void>}) {
  const [history,setHistory]=useState<Fact[]>([]), [loading,setLoading]=useState(true), [more,setMore]=useState(false)
  const [historyError,setHistoryError]=useState(''), [exportError,setExportError]=useState(''), [replayError,setReplayError]=useState('')
  const [download,setDownload]=useState(false), [knownAt,setKnownAt]=useState(''), [validAt,setValidAt]=useState('')
  const [replaying,setReplaying]=useState(false), [query,setQuery]=useState('')
  const [replay,setReplay]=useState<{facts:Fact[];known:string;valid:string}|null>(null)
  const [conflicts,setConflicts]=useState<FactConflict[]>([]), [conflictError,setConflictError]=useState('')
  const historyGeneration=useRef(0), replayGeneration=useRef(0), mounted=useRef(true)
  const load=useCallback(async(after=0)=>{
    const request=++historyGeneration.current
    setLoading(true);setHistoryError('')
    try {
      const rows=await productRequest<Fact[]>(`/history?after=${after}&limit=100`)
      if(!Array.isArray(rows))throw new Error('Invalid history response')
      if(!mounted.current||request!==historyGeneration.current)return
      setHistory(old=>after?[...old,...rows]:rows);setMore(rows.length===100)
    }catch(failure){if(mounted.current&&request===historyGeneration.current)setHistoryError(String(failure))}
    finally{if(mounted.current&&request===historyGeneration.current)setLoading(false)}
  },[])
  const loadConflicts=useCallback(async()=>{
    try {
      const rows=await productRequest<FactConflict[]>('/reconciliation/conflicts?state=all')
      if(!Array.isArray(rows))throw new Error('Invalid reconciliation response')
      if(mounted.current){setConflicts(rows);setConflictError('')}
    } catch(failure) {if(mounted.current)setConflictError(failure instanceof Error?failure.message:String(failure))}
  },[])
  useEffect(()=>{mounted.current=true;void load();void loadConflicts();return()=>{mounted.current=false;historyGeneration.current++;replayGeneration.current++}},[load,loadConflicts])
  async function exportEvidence() {
    setDownload(true);setExportError('')
    try {
      const data=await productRequest('/evidence')
      if(!mounted.current)return
      const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}))
      const link=document.createElement('a');link.href=url;link.download='shorefront-evidence.json';link.click();window.setTimeout(()=>URL.revokeObjectURL(url),1000)
    }catch(failure){if(mounted.current)setExportError(String(failure))}
    finally{if(mounted.current)setDownload(false)}
  }
  async function reconstruct(event:FormEvent) {
    event.preventDefault()
    const request=++replayGeneration.current
    setReplaying(true);setReplay(null);setReplayError('')
    try {
      const known=new Date(knownAt).toISOString(), valid=new Date(validAt).toISOString()
      const params=new URLSearchParams({known_at:known,valid_at:valid})
      const result=validateWorkspace(await productRequest<Workspace>(`/workspace?${params}`))
      if(mounted.current&&request===replayGeneration.current)setReplay({facts:result.records,known,valid})
    }catch(failure){if(mounted.current&&request===replayGeneration.current)setReplayError(String(failure))}
    finally{if(mounted.current&&request===replayGeneration.current)setReplaying(false)}
  }
  const filtered=history.filter(r=>`${recordName(r)} ${r.kind} ${r.source}`.toLowerCase().includes(query.toLowerCase()))
  const categories=new Set(facts.map(record=>record.kind)).size
  const sources=new Set(facts.map(record=>record.source).filter(Boolean)).size
  const unresolved=conflicts.filter(conflict=>conflict.state==='unresolved')
  const resolved=conflicts.filter(conflict=>conflict.state==='resolved')
  return <div className="ops-workspace evidence-workspace-advanced" data-product-workspace="evidence">
    <div className="product-section-heading ops-heading-action"><div><p className="eyebrow">EVIDENCE / PRESERVED CONTEXT</p><h1>Every correction keeps its past.</h1><p>Recorded time answers “what did we know?” Effective time answers “when did it apply?” Exported evidence uses a SHA-256 chain, not a digital signature.</p></div><button disabled={download} onClick={()=>void exportEvidence()}>{download?'Preparing…':'Export evidence'}</button></div>
    <div className="evidence-signal-strip" aria-label="Evidence coverage summary"><div><span>CURRENT FACTS</span><b>{facts.length}</b></div><div><span>VERSIONS LOADED</span><b>{history.length}</b></div><div><span>SOURCES</span><b>{sources}</b></div><div><span>OPEN CONFLICTS</span><b>{unresolved.length}</b></div><div><span>TEAM ACTORS</span><b>{team.filter(member=>member.active).length}</b></div></div>
    {exportError&&<p className="product-error" role="alert">{exportError} Retry the export when connected.</p>}
    <section className="ops-panel reconciliation-panel" aria-label="Source reconciliation">
      <header><div><span className="product-index">MULTI-SOURCE RECONCILIATION</span><h2>Source disagreements</h2></div><b>{unresolved.length} OPEN</b></header>
      <div className="reconciliation-intro"><p>Shorefront never silently chooses between contradictory sources. Compare the preserved versions, record the human basis for acceptance, and keep both observations in history.</p><button onClick={()=>void loadConflicts()}>Refresh conflicts</button></div>
      {conflictError&&<p className="product-error" role="alert">{conflictError}</p>}
      {!conflictError&&!unresolved.length&&<div className="ops-empty"><b>No unresolved source disagreements.</b><p>Cross-source changes will appear here when two operational actors or feeds disagree on the same fact.</p></div>}
      <div className="reconciliation-list">{unresolved.map(conflict=><ConflictReview key={conflict.id} conflict={conflict} team={team} writable={writable&&user.role!=='viewer'} onResolved={async resolved=>{setConflicts(old=>old.map(item=>item.id===resolved.id?resolved:item));await Promise.all([load(),onRefresh()])}}/>)}</div>
      {!!resolved.length&&<details className="reconciliation-resolved"><summary>Resolved disagreements · {resolved.length}</summary><div className="reconciliation-list">{resolved.map(conflict=><ConflictReview key={conflict.id} conflict={conflict} team={team} writable={false} onResolved={async()=>{}}/>)}</div></details>}
    </section>
    <section className="ops-panel"><header><div><span className="product-index">TWO-CLOCK RECONSTRUCTION</span><h2>Inspect the record as it stood</h2></div></header><div className="evidence-controls"><form className="product-replay" onSubmit={reconstruct}><label>Known by<input type="datetime-local" step="any" value={knownAt} required onChange={e=>setKnownAt(e.target.value)}/></label><label>Effective at<input type="datetime-local" step="any" value={validAt} required onChange={e=>setValidAt(e.target.value)}/></label><button type="submit">Reconstruct view</button></form><p>Inputs use your browser’s local timezone. Results retain their exact UTC timestamps. Historical facts are read-only.</p></div></section>
    {replaying&&<div className="evidence-loading" role="status">Reconstructing the selected clocks…</div>}
    {replayError&&<p className="product-error" role="alert">{replayError} Check the clocks and reconstruct again.</p>}
    {replay&&<section className="evidence-reconstruction" aria-label="Historical reconstruction"><div className="product-section-heading"><div><span className="product-index">READ-ONLY</span><h2>Historical facts · {replay.facts.length}</h2></div></div><p>Read-only historical view. Known by <code>{replay.known}</code> · Effective at <code>{replay.valid}</code></p>
      {replay.facts.length===0&&<div className="ops-empty"><b>No facts match both clocks.</b><p>Later observations are deliberately excluded. Choose another time to inspect them.</p></div>}
      {replay.facts.map(record=>{
        const current=facts.find(f=>f.kind===record.kind&&f.record_id===record.record_id)
        const keys=[...new Set([...Object.keys(record.payload),...Object.keys(current?.payload??{})])]
        const changes=keys.filter(key=>record.payload[key]!==current?.payload[key])
        return <article className="product-card" key={`${record.kind}:${record.record_id}`}><span className="product-index">{record.kind} / V{record.revision}</span><h3>{recordName(record)}</h3><FactDetails record={record} team={team}/>
          {current&&changes.length>0?<div className="evidence-table-scroll"><table aria-label={`Changes for ${recordName(record)}`}><thead><tr><th>Field</th><th>At selected clocks</th><th>Current recorded view · V{current.revision}</th></tr></thead><tbody>{changes.map(key=><tr key={key}><th scope="row">{key.replaceAll('_',' ')}</th><td>{show(record.payload[key])}</td><td>{show(current.payload[key])}</td></tr>)}</tbody></table></div>:<p>{current?'No payload differences from the current recorded view.':'Not present in the current effective view.'}</p>}
        </article>
      })}</section>}
    <section><div className="product-section-heading"><div><span className="product-index">APPEND-ONLY VERSIONS</span><h2>Record history</h2></div><button disabled={loading} onClick={()=>void load()}>Refresh history</button></div><label>Search loaded history<input type="search" value={query} onChange={e=>setQuery(e.target.value)}/></label><p className="product-small">{history.length} versions loaded, earliest first. Search applies to loaded versions.</p>
      {historyError&&<p className="product-error" role="alert">{historyError}<button onClick={()=>void load()}>Retry history</button></p>}
      {loading&&<p role="status">Loading recorded history…</p>}
      {!loading&&!filtered.length&&<div className="product-empty"><h3>{history.length?'No loaded versions match.':'No operational versions yet.'}</h3><p>{history.length?'Try another search, or load more versions.':'Create a record to start its history.'}</p></div>}
      <ol className="product-history">{filtered.map(record=><li key={record.sequence}><div><span className="product-index">{record.kind} / V{record.revision}</span><strong>{recordName(record)}</strong><span>{record.source}</span></div><div><span>Recorded {dateLabel(record.known_at)}</span><span>Effective {dateLabel(record.valid_at)}</span></div><details><summary>Inspect version</summary><FactDetails record={record} team={team}/></details></li>)}</ol>
      {more&&<button disabled={loading} onClick={()=>void load(history.at(-1)?.sequence)}>Load more versions</button>}
    </section>
  </div>
}
