import {useCallback,useEffect,useRef,useState,type FormEvent} from 'react'
import {dateLabel,productRequest,recordName,validateWorkspace,type Fact,type User,type Workspace} from './productClient'
import './ProductEvidence.css'

const show = (value:unknown)=>value==null?'Not recorded':String(value)
function FactDetails({record,team}:{record:Fact;team:User[]}) {
  const actor=team.find(u=>u.id===record.actor_id)
  return <div className="evidence-detail"><dl className="evidence-values">{Object.entries(record.payload).map(([key,value])=><div key={key}><dt>{key.replaceAll('_',' ')}</dt><dd>{show(value)}</dd></div>)}</dl>
    <dl className="evidence-provenance"><div><dt>Source</dt><dd>{record.source}</dd></div><div><dt>Recorded by</dt><dd>{actor?.name ?? 'Recorded actor'} <code>{record.actor_id}</code></dd></div><div><dt>Known at</dt><dd><time dateTime={record.known_at}>{record.known_at}</time></dd></div><div><dt>Effective at</dt><dd><time dateTime={record.valid_at}>{record.valid_at}</time></dd></div></dl></div>
}

export default function ProductEvidence({facts,team}:{facts:Fact[];team:User[]}) {
  const [history,setHistory]=useState<Fact[]>([]), [loading,setLoading]=useState(true), [more,setMore]=useState(false)
  const [historyError,setHistoryError]=useState(''), [exportError,setExportError]=useState(''), [replayError,setReplayError]=useState('')
  const [download,setDownload]=useState(false), [knownAt,setKnownAt]=useState(''), [validAt,setValidAt]=useState('')
  const [replaying,setReplaying]=useState(false), [query,setQuery]=useState('')
  const [replay,setReplay]=useState<{facts:Fact[];known:string;valid:string}|null>(null)
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
  useEffect(()=>{mounted.current=true;void load();return()=>{mounted.current=false;historyGeneration.current++;replayGeneration.current++}},[load])
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
  return <div className="ops-workspace" data-product-workspace="evidence">
    <div className="product-section-heading"><div><p className="eyebrow">EVIDENCE / PRESERVED CONTEXT</p><h1>Every correction keeps its past.</h1></div><button disabled={download} onClick={()=>void exportEvidence()}>{download?'Preparing…':'Export evidence'}</button></div>
    <p>Recorded time answers “what did we know?” Effective time answers “when did it apply?” Exported evidence uses a SHA-256 chain, not a digital signature.</p>
    {exportError&&<p className="product-error" role="alert">{exportError} Retry the export when connected.</p>}
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
