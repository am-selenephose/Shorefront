import {useRef, useState, type FormEvent} from 'react'
import {type Fact, type User, ProductError, productRequest, recordName, dateLabel} from './productClient'
import ProductImport from './ProductImport'

type Field = {key: string; label: string; type?: 'time'|'number'|'text'|'boolean'; ref?: string; choices?: string[]; optional?: boolean}
export const recordFields: Record<string, Field[]> = {
  port: [{key:'name', label:'Name'}, {key:'timezone', label:'Timezone'}, {key:'latitude', label:'Latitude', type:'number', optional:true}, {key:'longitude', label:'Longitude', type:'number', optional:true}],
  berth: [{key:'name', label:'Name'}, {key:'port_id', label:'Port', ref:'port'}, {key:'max_length_m', label:'Maximum length (m)', type:'number', optional:true}, {key:'max_draft_m', label:'Maximum draft (m)', type:'number', optional:true}, {key:'latitude', label:'Latitude', type:'number', optional:true}, {key:'longitude', label:'Longitude', type:'number', optional:true}],
  vessel: [{key:'name', label:'Name'}, {key:'imo', label:'IMO number', optional:true}, {key:'length_m', label:'Length (m)', type:'number', optional:true}, {key:'draft_m', label:'Draft (m)', type:'number', optional:true}],
  call: [{key:'vessel_id', label:'Vessel', ref:'vessel'}, {key:'berth_id', label:'Berth', ref:'berth', optional:true}, {key:'eta', label:'Arrival (your local time)', type:'time'}, {key:'etd', label:'Departure (your local time)', type:'time'}, {key:'status', label:'Status', choices:['planned','arrived','berthed','departed','cancelled']}],
  resource: [{key:'name', label:'Name'}, {key:'port_id', label:'Port', ref:'port'}, {key:'resource_type', label:'Resource type', choices:['tug','pilot','crew','equipment']}, {key:'available', label:'Available', type:'boolean'}],
  incident: [{key:'title', label:'Title'}, {key:'call_id', label:'Port call', ref:'call', optional:true}, {key:'severity', label:'Severity', choices:['medium','low','high','critical']}, {key:'status', label:'Status', choices:['open','acknowledged','resolved']}, {key:'detail', label:'Details', optional:true}],
  task: [{key:'title', label:'Title'}, {key:'call_id', label:'Port call', ref:'call', optional:true}, {key:'incident_id', label:'Incident', ref:'incident', optional:true}, {key:'assignee_id', label:'Assigned to', ref:'team', optional:true}, {key:'due_at', label:'Due (your local time)', type:'time'}, {key:'status', label:'Status', choices:['open','in_progress','done']}, {key:'completion_note', label:'Completion note', optional:true}],
  commitment: [{key:'title', label:'Title'}, {key:'call_id', label:'Port call', ref:'call'}, {key:'recipient_id', label:'Recipient', ref:'team'}, {key:'due_at', label:'Due (your local time)', type:'time'}, {key:'status', label:'Status', choices:['proposed','accepted','declined','fulfilled','cancelled']}, {key:'note', label:'Terms', optional:true}, {key:'proof', label:'Completion evidence', optional:true}],
  handoff: [{key:'title', label:'Title'}, {key:'call_id', label:'Port call', ref:'call'}, {key:'recipient_id', label:'Recipient', ref:'team'}, {key:'due_at', label:'Due (your local time)', type:'time'}, {key:'status', label:'Status', choices:['prepared','sent','acknowledged']}, {key:'note', label:'Handoff details', optional:true}, {key:'proof', label:'Recipient confirmation', optional:true}],
  obligation: [{key:'title', label:'Title'}, {key:'call_id', label:'Port call', ref:'call'}, {key:'assignee_id', label:'Assigned to', ref:'team'}, {key:'due_at', label:'Due (your local time)', type:'time'}, {key:'clause_reference', label:'Clause or SOP reference'}, {key:'status', label:'Status', choices:['draft','active','completed','cancelled']}, {key:'review_note', label:'Human review note', optional:true}, {key:'proof', label:'Completion evidence', optional:true}],
}

function localTime(value: unknown) {
  if (typeof value !== 'string' || !value) return ''
  const date = new Date(value)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0,16)
}

export function RecordEditor({record, initialKind, initialPayload={}, fixedKind=false, facts, team, writable, onSave, onCancel}: {record: Fact|null; initialKind: string; initialPayload?:Fact['payload']; fixedKind?:boolean; facts: Fact[]; team: User[]; writable:boolean; onSave: () => Promise<void>; onCancel: () => void}) {
  const [kind, setKind] = useState(record?.kind ?? initialKind)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [committed, setCommitted] = useState(false)
  const [baseRecord, setBaseRecord] = useState(record)
  const [conflict, setConflict] = useState(false)
  const [latest, setLatest] = useState<Fact|null>(null)
  const [reviewing, setReviewing] = useState(false)
  const [replaced, setReplaced] = useState(false)
  const values = baseRecord?.payload ?? initialPayload
  const identity = useRef(record?.record_id ?? crypto.randomUUID())
  const attempt = useRef<{intent: string; key: string}|null>(null)
  async function reviewLatest() {
    if (!record || !writable || busy || reviewing || committed) return
    setReviewing(true); setError(''); setLatest(null)
    try {
      const head = await productRequest<Fact>(`/records/${encodeURIComponent(kind)}/${encodeURIComponent(record.record_id)}/head`)
      if (head.kind !== kind || head.record_id !== record.record_id || !Number.isInteger(head.revision) || !head.payload) throw new Error('Invalid record response; your draft has not changed.')
      setLatest(head)
    } catch (failure) {setError(failure instanceof Error ? failure.message : 'Could not load latest version')}
    finally {setReviewing(false)}
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!writable || busy || reviewing || committed) return
    setError(''); setBusy(true)
    const data = new FormData(event.currentTarget)
    const payload: Fact['payload'] = {}
    try {
      for (const field of recordFields[kind]) {
        const value = String(data.get(field.key) ?? '')
        if (!value && field.optional) continue
        payload[field.key] = field.type === 'number' ? Number(value) : field.type === 'boolean' ? value === 'true' : field.type === 'time' ? (values[field.key] && value===localTime(values[field.key]) ? values[field.key] : new Date(value).toISOString()) : value
      }
      const command = {record_id: identity.current, expected_revision: baseRecord?.revision ?? 0, source: String(data.get('source')), payload}
      const intent = JSON.stringify({kind, command})
      if (attempt.current?.intent !== intent) attempt.current = {intent, key: crypto.randomUUID()}
      await productRequest(`/records/${kind}`, command, attempt.current.key)
      setCommitted(true)
      await onSave()
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Could not save record')
      if (failure instanceof ProductError && failure.status === 409 && record) {setConflict(true); setLatest(null)}
    }
    finally {setBusy(false)}
  }
  return <section className="product-editor" aria-label="Record editor">
    <div className="product-section-heading"><div><p className="eyebrow">AUTHORITATIVE RECORD</p><h2>{record ? 'Record a correction' : 'Add an operational record'}</h2></div><button type="button" onClick={onCancel} disabled={busy}>Cancel</button></div>
    <p>Changes create a new version. Original facts and their source stay in the history.</p>
    {replaced && <p role="status">Saving creates a new version effective now. Existing scheduled versions remain recorded and can still take effect at their original time.</p>}
    <form onSubmit={submit} aria-busy={busy || reviewing}>
      <fieldset disabled={busy || reviewing || !writable || committed}>
        <label>Record type<select value={kind} disabled={!!record || fixedKind} onChange={e => setKind(e.target.value)}>{Object.keys(recordFields).map(k => <option key={k} value={k}>{k}</option>)}</select></label>
        <div className="product-form-grid" key={`${kind}:${baseRecord?.sequence ?? 'new'}`}>
          {recordFields[kind].map(field => {
            const options = field.ref === 'team' ? team.filter(u => u.active && (!['handoff','commitment','obligation'].includes(kind) || u.role!=='viewer')).map(u => ({id:u.id, name:u.name})) : field.ref ? facts.filter(f => f.kind === field.ref).map(f => ({id:f.record_id, name:recordName(f)})) : []
            const recordedReference = field.ref ? String(values[field.key] ?? '') : ''
            const missingReference = recordedReference && !options.some(option => option.id === recordedReference)
            return <label key={field.key}>{field.label}{field.optional ? <small>Optional</small> : null}
              {field.ref ? <select name={field.key} required={!field.optional} defaultValue={recordedReference}><option value="">{field.optional ? 'Not specified' : `Select ${field.label.toLowerCase()}`}</option>{missingReference && <option value={recordedReference}>Recorded reference unavailable in current choices: {recordedReference}</option>}{options.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}</select>
                : field.choices || field.type === 'boolean' ? <select name={field.key} defaultValue={String(values[field.key] ?? field.choices?.[0] ?? 'false')}>{(field.choices ?? ['false','true']).map(c => <option key={c} value={c}>{c.replaceAll('_',' ')}</option>)}</select>
                : <input name={field.key} required={!field.optional} type={field.type === 'time' ? 'datetime-local' : 'text'} inputMode={field.type === 'number' ? 'decimal' : undefined} maxLength={field.key === 'detail' ? 4000 : 2000} defaultValue={field.type === 'time' ? localTime(values[field.key]) : String(values[field.key] ?? (field.key === 'timezone' ? Intl.DateTimeFormat().resolvedOptions().timeZone : ''))}/>}</label>
          })}
          <label>Source<input name="source" required maxLength={500} defaultValue="Operator entry"/><small>Who or what supplied this information?</small></label>
        </div>
        {error && <p role="alert" className="product-error">{error}</p>}
        <button className="product-primary" type="submit">{busy ? 'Saving…' : 'Save record'}</button>
      </fieldset>
      {conflict && !committed && <section className="product-boundary" aria-label="Version conflict">
        <h3>Review the latest recorded version</h3>
        <p>Your draft is unchanged. A scheduled or backdated version may differ from the current workspace. Review it before deciding which values to save.</p>
        <button type="button" disabled={busy || reviewing || !writable} onClick={()=>void reviewLatest()}>{reviewing ? 'Loading latest version…' : 'Review latest version'}</button>
        {latest && <section aria-label="Latest recorded version">
          <h4>{recordName(latest)} · revision {latest.revision}</h4>
          <p>Source: {latest.source}<br/>Recorded: {latest.known_at}<br/>Effective: {latest.valid_at}</p>
          <dl>{Object.entries(latest.payload).map(([field,value])=><div key={field}><dt>{field.replaceAll('_',' ')}</dt><dd>{String(value ?? 'Not specified')}</dd></div>)}</dl>
          <p>The next action replaces your unsaved form values. Nothing is written until you select Save record.</p>
          <button type="button" disabled={busy || reviewing || !writable} onClick={()=>{setBaseRecord(latest); setLatest(null); setConflict(false); setReplaced(true); setError(''); attempt.current=null}}>Replace draft with latest version</button>
        </section>}
      </section>}
      {committed && <div role="status"><p>Record saved. Refresh to show the committed version; do not submit it again.</p><button type="button" disabled={busy || !writable} onClick={()=>void onSave().catch(e=>setError(String(e)))}>Refresh saved record</button></div>}
    </form>
  </section>
}

export default function ProductRecords({facts, team, writable, onSave}: {facts: Fact[]; team: User[]; writable: boolean; onSave: () => Promise<void>}) {
  const [kind,setKind]=useState('port')
  const [edit,setEdit]=useState<Fact|null|undefined>(undefined)
  const [query,setQuery]=useState('')
  const [importing,setImporting]=useState(false)
  const categories=Object.keys(recordFields)
  const filtered=facts.filter(f=>f.kind===kind&&recordName(f).toLowerCase().includes(query.toLowerCase()))
  const sourceCount=new Set(facts.map(f=>f.source).filter(Boolean)).size
  const cell=(record:Fact,key:string,value:unknown)=>key.endsWith('_id')?facts.find(f=>f.record_id===value)?.payload.name??team.find(u=>u.id===value)?.name??String(value):String(value)
  return <div className="records-workspace">
    <div className="product-section-heading ops-heading-action"><div><p className="eyebrow">RECORDS / SOURCED & VERSIONED</p><h1>Build the operational picture.</h1><p>Every table cell is backed by a recorded source and revision. No generated harbor activity.</p></div><div className="product-actions"><button disabled={!writable} aria-expanded={importing} onClick={()=>setImporting(!importing)}>{importing?'Close import':'Import records'}</button><button className="product-primary" disabled={!writable} onClick={()=>setEdit(null)}>Add record</button></div></div>
    <div className="records-signal-strip" aria-label="Record inventory summary"><div><span>FACTS IN VIEW</span><b>{facts.length}</b></div><div><span>SOURCES</span><b>{sourceCount}</b></div><div><span>CATEGORIES</span><b>{categories.filter(k=>facts.some(f=>f.kind===k)).length}/{categories.length}</b></div><div><span>TEAM</span><b>{team.filter(u=>u.active).length}</b></div></div>
    {importing&&<ProductImport writable={writable} onSave={onSave}/>}
    <div className="records-category-tabs" role="tablist" aria-label="Record categories">{categories.map(category=><button type="button" role="tab" aria-selected={kind===category} key={category} onClick={()=>{setKind(category);setEdit(undefined)}}><span>{category}</span><b>{facts.filter(f=>f.kind===category).length}</b></button>)}</div>
    <div className="records-toolbar"><label className="records-category-select">Record category<select value={kind} onChange={e=>{setKind(e.target.value);setEdit(undefined)}}>{categories.map(category=><option key={category} value={category}>{category}</option>)}</select></label><label>Search {kind} records<input type="search" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Name or title"/></label><div><span className="product-index">VISIBLE / TOTAL</span><b>{filtered.length}/{facts.filter(f=>f.kind===kind).length}</b></div></div>
    {edit!==undefined&&<RecordEditor key={edit?.record_id??`new-${kind}`} record={edit} initialKind={kind} facts={facts} team={team} writable={writable} onCancel={()=>setEdit(undefined)} onSave={async()=>{await onSave();setEdit(undefined)}}/>}
    {!filtered.length&&<div className="product-empty"><span className="product-index">01 / START WITH FACTS</span><h2>No {kind} records yet.</h2><p>Add your own record. References appear after their port, berth or vessel has been created.</p></div>}
    {!!filtered.length&&<section className="ops-panel records-register"><header><div><span className="product-index">{kind.toUpperCase()} REGISTER</span><h2>Current effective records</h2></div><b>{filtered.length}</b></header><div className="ops-table-scroll"><table aria-label={`${kind} record register`}><thead><tr><th>Name</th><th>Revision</th><th>Recorded fields</th><th>Source</th><th>Known</th><th/></tr></thead><tbody>{filtered.map(record=>{const details=Object.entries(record.payload).filter(([key,value])=>!['name','title'].includes(key)&&value!==null&&value!=='');return <tr key={record.record_id}><td><h2>{recordName(record)}</h2><small>{record.record_id}</small></td><td><span className="record-version">V{record.revision}</span></td><td><div className="record-field-preview">{details.slice(0,3).map(([key,value])=><span key={key}><i>{key.replaceAll('_',' ')}</i><b>{cell(record,key,value)}</b></span>)}{details.length>3&&<em>+{details.length-3} fields</em>}</div></td><td>{record.source}</td><td><time>{dateLabel(record.known_at)}</time></td><td><button aria-label={`Edit ${recordName(record)}`} disabled={!writable} onClick={()=>setEdit(record)}>Edit</button></td></tr>})}</tbody></table></div></section>}
  </div>
}
