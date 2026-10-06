import {useCallback,useEffect,useRef,useState,type FormEvent} from 'react'
import {dateLabel,productRequest,recordName,type Fact,type User} from './productClient'

type Source = {id:string;name:string;allowed_kinds:string[];standard_profiles:string[];active:boolean;created_by:string;created_at:string;expires_at:string;expired:boolean;last_used_at:string|null;write_count:number}
type Grant = {id:string;name:string;allowed_kinds:string[];fields:Record<string,string[]>;call_ids:string[];active:boolean;created_by:string;created_at:string;expires_at:string;expired:boolean;last_used_at:string|null;access_count:number}
type StandardProfile = {id:string;standard:string;version:string;direction:string;conformance:string;native_materialization:string[];notes:string;event_versions:number}
type StandardEvent = {sequence:number;source_id:string;profile_id:string;event_id:string;revision:number;external_key:string;event_updated_at:string;received_at:string;state:string;materialized:{kind:string;record_id:string;revision:number}[]}
type Delivery = {id:string;grant_id:string;created_by:string;created_at:string;payload_digest:string;record_count:number;state:'pending'|'delivered'|'acknowledged';first_delivered_at:string|null;last_delivered_at:string|null;retrieval_count:number;acknowledged_at:string|null;acknowledged_digest:string|null;acknowledgement_note:string}
type Reconciliation = {delivery_id:string;grant_id:string;state:'in_sync'|'drifted';delivered_digest:string;current_digest:string;acknowledged_at:string;added:string[];removed:string[];changed:string[]}

const sourceKinds=['port','berth','vessel','call','resource','incident','task','outcome']
const grantKinds=['port','berth','vessel','call','resource','incident','task','handoff','commitment','obligation','outcome']
const safeFields:Record<string,string[]>={
  port:['name','timezone','latitude','longitude'],
  berth:['name','port_id','max_length_m','max_draft_m','latitude','longitude'],
  vessel:['name','imo','length_m','draft_m'],
  call:['vessel_id','berth_id','eta','etd','status'],
  resource:['name','port_id','resource_type','available'],
  incident:['title','call_id','severity','status'],
  task:['title','call_id','incident_id','due_at','status'],
  handoff:['title','call_id','due_at','status'],
  commitment:['title','call_id','due_at','status'],
  obligation:['title','call_id','due_at','status','clause_reference'],
  outcome:['decision_id','actual_arrival','actual_departure'],
}
const defaultSource=new Set(['port','berth','vessel','call','resource','incident'])
const defaultGrant=new Set(['port','berth','vessel','call','incident'])

function TokenReceipt({title,token,onHide}:{title:string;token:string;onHide:()=>void}){
  const [copied,setCopied]=useState(false)
  async function copy(){try{await navigator.clipboard.writeText(token);setCopied(true)}catch{/* visible token remains available */}}
  return <div className="connection-token" role="status"><div><span className="product-index">ONE-TIME CREDENTIAL</span><b>{title}</b><p>Store this secret now. Shorefront keeps only its SHA-256 digest and cannot show this token again.</p></div><code>{token}</code><div className="product-actions"><button type="button" onClick={()=>void copy()}>{copied?'Copied':'Copy token'}</button><button type="button" onClick={onHide}>Hide credential</button></div></div>
}

function KindSelector({label,kinds,selected,onChange}:{label:string;kinds:string[];selected:Set<string>;onChange:(value:Set<string>)=>void}){
  return <fieldset className="connection-kind-selector"><legend>{label}</legend>{kinds.map(kind=><label key={kind}><input type="checkbox" checked={selected.has(kind)} onChange={event=>{const next=new Set(selected);if(event.target.checked)next.add(kind);else next.delete(kind);onChange(next)}}/><span>{kind}</span></label>)}</fieldset>
}

export default function ProductConnections({user,facts,writable}:{user:User;facts:Fact[];writable:boolean}){
  const [sources,setSources]=useState<Source[]>([])
  const [grants,setGrants]=useState<Grant[]>([])
  const [profiles,setProfiles]=useState<StandardProfile[]>([])
  const [standardEvents,setStandardEvents]=useState<StandardEvent[]>([])
  const [deliveries,setDeliveries]=useState<Delivery[]>([])
  const [reconciliations,setReconciliations]=useState<Record<string,Reconciliation>>({})
  const [sourceKindsSelected,setSourceKindsSelected]=useState(new Set(defaultSource))
  const [sourceStandardsSelected,setSourceStandardsSelected]=useState(new Set<string>())
  const [grantKindsSelected,setGrantKindsSelected]=useState(new Set(defaultGrant))
  const [sourceToken,setSourceToken]=useState<{label:string;token:string}|null>(null)
  const [grantToken,setGrantToken]=useState<{label:string;token:string}|null>(null)
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('')
  const [sourceOpen,setSourceOpen]=useState(false),[grantOpen,setGrantOpen]=useState(false)
  const deliveryKeys=useRef(new Map<string,string>())

  const load=useCallback(async()=>{
    if(user.role!=='admin') return
    const [sourceRows,grantRows,profileRows,eventRows,deliveryRows]=await Promise.all([
      productRequest<Source[]>('/connections/sources'),
      productRequest<Grant[]>('/connections/partner-grants'),
      productRequest<StandardProfile[]>('/connections/standards'),
      productRequest<StandardEvent[]>('/connections/standard-events?limit=50'),
      productRequest<Delivery[]>('/connections/deliveries'),
    ])
    setSources(sourceRows);setGrants(grantRows);setProfiles(profileRows);setStandardEvents(eventRows);setDeliveries(deliveryRows);setError('')
  },[user.role])
  useEffect(()=>{void load().catch(failure=>setError(String(failure)))},[load])

  if(user.role!=='admin') return <div className="ops-workspace"><section className="ops-heading"><span className="product-index">CONNECTIONS / LEAST PRIVILEGE</span><h1>External access stays scoped.</h1><p>Connection credentials and partner projections are managed by an administrator. Your operational role is unchanged.</p></section><div className="product-boundary"><b>Administrator authority required.</b><p>This workspace does not reveal integration credentials, partner grants or their usage to non-administrators.</p></div></div>

  async function createSource(event:FormEvent<HTMLFormElement>){
    event.preventDefault();if(!sourceKindsSelected.size)return
    setBusy(true);setError('')
    const form=event.currentTarget,data=new FormData(form)
    try{
      const result=await productRequest<{source:Source;token:string}>('/connections/sources',{
        id:String(data.get('id')),name:String(data.get('name')),expires_in_hours:Number(data.get('expires_in_hours')),
        allowed_kinds:[...sourceKindsSelected],standard_profiles:[...sourceStandardsSelected],
      })
      setSourceToken({label:result.source.name,token:result.token});setSourceOpen(false);form.reset();setSourceKindsSelected(new Set(defaultSource));setSourceStandardsSelected(new Set());await load()
    }catch(failure){setError(failure instanceof Error?failure.message:String(failure))}finally{setBusy(false)}
  }
  async function createGrant(event:FormEvent<HTMLFormElement>){
    event.preventDefault();if(!grantKindsSelected.size)return
    setBusy(true);setError('')
    const form=event.currentTarget,data=new FormData(form),call=String(data.get('call_id')??'')
    const fields=Object.fromEntries([...grantKindsSelected].map(kind=>[kind,safeFields[kind]]))
    try{
      const result=await productRequest<{grant:Grant;token:string}>('/connections/partner-grants',{
        id:String(data.get('id')),name:String(data.get('name')),expires_in_hours:Number(data.get('expires_in_hours')),
        allowed_kinds:[...grantKindsSelected],fields,call_ids:call?[call]:[],
      })
      setGrantToken({label:result.grant.name,token:result.token});setGrantOpen(false);form.reset();setGrantKindsSelected(new Set(defaultGrant));await load()
    }catch(failure){setError(failure instanceof Error?failure.message:String(failure))}finally{setBusy(false)}
  }
  async function mutate(path:string,kind:'source'|'grant',label:string){
    setBusy(true);setError('')
    try{
      const result=await productRequest<{token?:string;source?:Source;grant?:Grant}>(path,{})
      if(result.token){(kind==='source'?setSourceToken:setGrantToken)({label,token:result.token})}
      await load()
    }catch(failure){setError(failure instanceof Error?failure.message:String(failure))}finally{setBusy(false)}
  }

  async function freezeDelivery(grant:Grant){
    setBusy(true);setError('');setNotice('')
    let key=deliveryKeys.current.get(grant.id)
    if(!key){key=crypto.randomUUID();deliveryKeys.current.set(grant.id,key)}
    try{
      const result=await productRequest<{delivery:Delivery;records:unknown[]}>('/connections/partner-grants/'+grant.id+'/deliveries',{},key)
      deliveryKeys.current.delete(grant.id)
      setNotice('Frozen delivery '+result.delivery.id+' · '+result.delivery.record_count+' records · '+result.delivery.payload_digest.slice(0,12)+'…')
      await load()
    }catch(failure){setError(failure instanceof Error?failure.message:String(failure))}finally{setBusy(false)}
  }
  async function reconcile(delivery:Delivery){
    setBusy(true);setError('')
    try{
      const result=await productRequest<Reconciliation>('/connections/deliveries/'+delivery.id+'/reconciliation')
      setReconciliations(current=>({...current,[delivery.id]:result}))
    }catch(failure){setError(failure instanceof Error?failure.message:String(failure))}finally{setBusy(false)}
  }

  const activeSources=sources.filter(source=>source.active&&!source.expired)
  const activeGrants=grants.filter(grant=>grant.active&&!grant.expired)
  const integrationFacts=facts.filter(fact=>fact.source.startsWith('integration:'))
  const calls=facts.filter(fact=>fact.kind==='call'&&!['departed','cancelled'].includes(String(fact.payload.status)))

  return <div className="ops-workspace connections-workspace" data-product-workspace="connections">
    <section className="ops-heading ops-heading-action"><div><span className="product-index">CONNECTIONS / DATA IN · SCOPED DATA OUT</span><h1>Connect the port without surrendering the workspace.</h1><p>Inbound sources get kind-scoped write credentials. Partners get field-scoped read projections. Tokens are shown once and stored only as digests.</p></div><div className="product-actions"><button disabled={!writable||busy} onClick={()=>setSourceOpen(value=>!value)}>Add data source</button><button className="product-primary" disabled={!writable||busy} onClick={()=>setGrantOpen(value=>!value)}>Create partner projection</button></div></section>
    <div className="connection-signal-strip" aria-label="Connection summary"><div><span>ACTIVE SOURCES</span><b>{activeSources.length}</b></div><div><span>STANDARD EVENTS</span><b>{standardEvents.length}</b></div><div><span>ACTIVE PROJECTIONS</span><b>{activeGrants.length}</b></div><div><span>DELIVERIES</span><b>{deliveries.length}</b></div><div><span>ACKNOWLEDGED</span><b>{deliveries.filter(item=>item.state==='acknowledged').length}</b></div></div>
    {sourceToken&&<TokenReceipt title={sourceToken.label} token={sourceToken.token} onHide={()=>setSourceToken(null)}/>}
    {grantToken&&<TokenReceipt title={grantToken.label} token={grantToken.token} onHide={()=>setGrantToken(null)}/>}
    {error&&<p className="product-error" role="alert">{error}</p>}
    {notice&&<p className="connection-notice" role="status">{notice}</p>}

    {sourceOpen&&<section className="connection-editor ops-panel"><header><div><span className="product-index">INBOUND MACHINE CREDENTIAL</span><h2>Register a data source</h2></div><button onClick={()=>setSourceOpen(false)}>Close</button></header><form onSubmit={createSource}><fieldset disabled={!writable||busy}><div className="product-form-grid"><label>Source ID<input name="id" required pattern="[A-Za-z0-9_-]+" maxLength={96} placeholder="terminal-tos"/></label><label>Display name<input name="name" required maxLength={200} placeholder="Terminal TOS feed"/></label><label>Credential lifetime (hours)<input name="expires_in_hours" type="number" min={1} max={8760} defaultValue={720} required/></label></div><KindSelector label="Allowed inbound record kinds" kinds={sourceKinds} selected={sourceKindsSelected} onChange={setSourceKindsSelected}/><fieldset className="connection-standard-selector"><legend>Optional standards profiles</legend>{profiles.map(profile=><label key={profile.id}><input type="checkbox" checked={sourceStandardsSelected.has(profile.id)} onChange={event=>{const next=new Set(sourceStandardsSelected);if(event.target.checked)next.add(profile.id);else next.delete(profile.id);setSourceStandardsSelected(next)}}/><span><b>{profile.standard} {profile.version}</b><small>{profile.conformance.replaceAll('-',' ')}</small></span></label>)}</fieldset><p className="connection-policy">The source cannot create users, approve decisions, manage grants, or write coordination state. Every accepted native record is attributed to <code>integration:&lt;source-id&gt;</code>; standards materialization is separately profile-gated.</p><button className="product-primary" disabled={!sourceKindsSelected.size}>Create source credential</button></fieldset></form></section>}

    {grantOpen&&<section className="connection-editor ops-panel"><header><div><span className="product-index">OUTBOUND READ PROJECTION</span><h2>Create a partner projection</h2></div><button onClick={()=>setGrantOpen(false)}>Close</button></header><form onSubmit={createGrant}><fieldset disabled={!writable||busy}><div className="product-form-grid"><label>Grant ID<input name="id" required pattern="[A-Za-z0-9_-]+" maxLength={96} placeholder="agent-call-window"/></label><label>Partner / purpose<input name="name" required maxLength={200} placeholder="Port agent call window"/></label><label>Credential lifetime (hours)<input name="expires_in_hours" type="number" min={1} max={2160} defaultValue={24} required/></label><label>Call scope<select name="call_id" defaultValue=""><option value="">All records in allowed kinds</option>{calls.map(call=><option key={call.record_id} value={call.record_id}>{recordName(facts.find(f=>f.kind==='vessel'&&f.record_id===call.payload.vessel_id)??call)+' · '+call.record_id}</option>)}</select></label></div><KindSelector label="Projected record kinds" kinds={grantKinds} selected={grantKindsSelected} onChange={setGrantKindsSelected}/><div className="connection-field-rules"><span className="product-index">FIELD ALLOWLIST PREVIEW</span>{[...grantKindsSelected].map(kind=><div key={kind}><b>{kind}</b><span>{safeFields[kind].join(' · ')}</span></div>)}</div><p className="connection-policy">Raw source attribution, actor IDs, proof notes, internal review notes and credentials are excluded from these default projections.</p><button className="product-primary" disabled={!grantKindsSelected.size}>Create projection credential</button></fieldset></form></section>}

    <section className="ops-panel connection-standards"><header><div><span className="product-index">STANDARDS GATEWAY</span><h2>Validated external event contracts</h2></div><b>{profiles.length}</b></header><div className="standard-profile-grid">{profiles.map(profile=><article key={profile.id}><span className="product-index">{profile.id}</span><h3>{profile.standard} {profile.version}</h3><p>{profile.notes}</p><div><span>Conformance</span><b>{profile.conformance.replaceAll('-',' ')}</b></div><div><span>Native materialization</span><b>{profile.native_materialization.join(' · ')}</b></div><div><span>Event versions</span><b>{profile.event_versions}</b></div></article>)}</div>{standardEvents.length>0&&<div className="ops-table-scroll"><table aria-label="Standard event registry"><thead><tr><th>Profile</th><th>Source</th><th>External call</th><th>Event</th><th>Revision</th><th>State</th><th>Received</th></tr></thead><tbody>{standardEvents.map(item=><tr key={item.sequence}><td>{item.profile_id}</td><td>{item.source_id}</td><td><small>{item.external_key}</small></td><td><small>{item.event_id}</small></td><td>v{item.revision}</td><td><span className={'connection-state '+(item.state==='materialized'?'active':'')}>{item.state.toUpperCase()}</span></td><td>{dateLabel(item.received_at)}</td></tr>)}</tbody></table></div>}</section>
    <div className="connection-grid">
      <section className="ops-panel connection-register"><header><div><span className="product-index">INBOUND REGISTRY</span><h2>Data source credentials</h2></div><b>{sources.length}</b></header>{sources.length?<div className="ops-table-scroll"><table aria-label="Data source registry"><thead><tr><th>Source</th><th>State</th><th>Allowed writes</th><th>Usage</th><th>Expires</th><th/></tr></thead><tbody>{sources.map(source=><tr key={source.id}><td><b>{source.name}</b><small>{source.id}</small></td><td><span className={'connection-state '+(source.active&&!source.expired?'active':'inactive')}>{source.active&&!source.expired?'ACTIVE':source.expired?'EXPIRED':'REVOKED'}</span></td><td><div className="connection-kind-pills">{source.allowed_kinds.map(kind=><span key={kind}>{kind}</span>)}</div>{source.standard_profiles.length>0&&<div className="connection-standard-pills">{source.standard_profiles.map(profile=><span key={profile}>{profile}</span>)}</div>}</td><td><b>{source.write_count} records</b><small>{source.last_used_at?'last '+dateLabel(source.last_used_at):'never used'}</small></td><td>{dateLabel(source.expires_at)}</td><td><div className="connection-row-actions">{source.active&&!source.expired&&<><button disabled={busy||!writable} onClick={()=>void mutate('/connections/sources/'+source.id+'/rotate?expires_in_hours=720','source',source.name)}>Rotate</button><button disabled={busy||!writable} onClick={()=>void mutate('/connections/sources/'+source.id+'/revoke','source',source.name)}>Revoke</button></>}</div></td></tr>)}</tbody></table></div>:<div className="ops-empty"><b>No inbound sources registered.</b><p>Manual records remain fully usable. Add a source only when you have a real system or feed to connect.</p></div>}</section>
      <section className="ops-panel connection-register"><header><div><span className="product-index">PARTNER PROJECTIONS</span><h2>Scoped external reads</h2></div><b>{grants.length}</b></header>{grants.length?<div className="ops-table-scroll"><table aria-label="Partner projection registry"><thead><tr><th>Projection</th><th>State</th><th>Scope</th><th>Fields</th><th>Usage</th><th/></tr></thead><tbody>{grants.map(grant=><tr key={grant.id}><td><b>{grant.name}</b><small>{grant.id}</small></td><td><span className={'connection-state '+(grant.active&&!grant.expired?'active':'inactive')}>{grant.active&&!grant.expired?'ACTIVE':grant.expired?'EXPIRED':'REVOKED'}</span></td><td><div className="connection-kind-pills">{grant.allowed_kinds.map(kind=><span key={kind}>{kind}</span>)}</div><small>{grant.call_ids.length?grant.call_ids.join(', '):'all allowed records'}</small></td><td><b>{Object.values(grant.fields).reduce((sum,fields)=>sum+fields.length,0)} fields</b><small>explicit allowlists</small></td><td><b>{grant.access_count} reads</b><small>{grant.last_used_at?'last '+dateLabel(grant.last_used_at):'never used'}</small></td><td><div className="connection-row-actions">{grant.active&&!grant.expired&&<><button disabled={busy||!writable} onClick={()=>void freezeDelivery(grant)}>Freeze delivery</button><button disabled={busy||!writable} onClick={()=>void mutate('/connections/partner-grants/'+grant.id+'/rotate?expires_in_hours=24','grant',grant.name)}>Rotate</button><button disabled={busy||!writable} onClick={()=>void mutate('/connections/partner-grants/'+grant.id+'/revoke','grant',grant.name)}>Revoke</button></>}</div></td></tr>)}</tbody></table></div>:<div className="ops-empty"><b>No partner projections active.</b><p>Do not share the whole workspace. Create a projection only for the record kinds and fields a partner actually needs.</p></div>}</section>
    </div>
    <section className="ops-panel connection-deliveries"><header><div><span className="product-index">DELIVERY LEDGER / IMMUTABLE PULL SNAPSHOTS</span><h2>What the partner actually received.</h2></div><b>{deliveries.length}</b></header>{deliveries.length?<div className="ops-table-scroll"><table aria-label="Partner delivery ledger"><thead><tr><th>Delivery</th><th>Grant</th><th>State</th><th>Records</th><th>Retrievals</th><th>Digest</th><th>Reconciliation</th><th/></tr></thead><tbody>{deliveries.map(delivery=>{const reconciliation=reconciliations[delivery.id];return <tr key={delivery.id}><td><b>{delivery.id}</b><small>{dateLabel(delivery.created_at)}</small></td><td>{delivery.grant_id}</td><td><span className={'connection-state '+(delivery.state==='acknowledged'?'active':'')}>{delivery.state.toUpperCase()}</span>{delivery.acknowledged_at&&<small>ack {dateLabel(delivery.acknowledged_at)}</small>}</td><td>{delivery.record_count}</td><td>{delivery.retrieval_count}</td><td><code>{delivery.payload_digest.slice(0,12)}…</code></td><td>{reconciliation?<><span className={'connection-state '+(reconciliation.state==='in_sync'?'active':'inactive')}>{reconciliation.state.replace('_',' ').toUpperCase()}</span>{reconciliation.state==='drifted'&&<small>{reconciliation.added.length} added · {reconciliation.removed.length} removed · {reconciliation.changed.length} changed</small>}</>:<small>{delivery.state==='acknowledged'?'not checked':'awaiting acknowledgement'}</small>}</td><td>{delivery.state==='acknowledged'&&<button disabled={busy} onClick={()=>void reconcile(delivery)}>Reconcile</button>}</td></tr>})}</tbody></table></div>:<div className="ops-empty"><b>No delivery snapshots yet.</b><p>Freeze an active partner projection to create an immutable pull snapshot. A partner retrieval and exact-digest acknowledgement are recorded separately.</p></div>}</section>
    <aside className="product-boundary"><b>Connection boundary.</b><p>This is scoped API access, not federated SSO or a claim that an external platform is integrated. Partner delivery is a durable pull queue with exact-digest acknowledgement, not a claim that Shorefront pushed data into a third-party system. Vendor contracts, live-feed entitlements and identity federation remain separate.</p></aside>
  </div>
}
