import {Suspense,lazy,useEffect,useMemo,useState} from 'react'
import {Waves,LayoutDashboard,Ship,CalendarRange,Anchor,ClipboardList,TriangleAlert,ChartNoAxesCombined,Settings2,Compass,Eye,Pause,Play,Maximize2,MapPinned,ArrowUpRight,X,ShieldCheck,FileClock,RefreshCw,Layers,Sun,CheckCircle2,AlertCircle,Route,SlidersHorizontal} from 'lucide-react'
import {OperationalCalls,OperationalPlan,OperationalPulse,OperationalExceptions} from '../ProductWorkspaces'
import ProductCoordination from '../ProductCoordination'
import {recordName,type Workspace,type User} from '../productClient'
import {showcaseWorkspace,showcaseTeam,showcaseActions,showcaseConflicts} from '../ShowcaseApp'
import {deriveLivingHarbor,berthTimeline,resourceStatus,type LivingCall} from './domain'
import './LivingHarbor.css'
const HarborWorld=lazy(()=>import('./HarborWorld'))
type View='Overview'|'Port Calls'|'Berth Planning'|'Resources'|'Operations'|'Incidents'|'Reports'|'Administration'
const views:View[]=['Overview','Port Calls','Berth Planning','Resources','Operations','Incidents','Reports','Administration']
const icons=[LayoutDashboard,Ship,CalendarRange,Anchor,ClipboardList,TriangleAlert,ChartNoAxesCombined,Settings2]
const fragments=['overview','port-calls','berth-planning','resources','operations','incidents','reports','administration']
const viewFromHash=():View=>views[fragments.indexOf(location.hash.slice(1))]??'Overview'
const formatTime=(value:string)=>{const t=Date.parse(value);return Number.isFinite(t)?new Date(t).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}):'Unspecified'}
const reduced=()=>typeof window.matchMedia==='function'&&window.matchMedia('(prefers-reduced-motion: reduce)').matches
const webgl=()=>{try{const c=document.createElement('canvas');return !!(c.getContext('webgl2')||c.getContext('webgl'))}catch{return false}}
function Heading({eyebrow,title,children}:{eyebrow:string;title:string;children?:React.ReactNode}){
 return <div className="lh-detail-heading"><span>{eyebrow}</span><h1>{title}</h1>{children&&<p>{children}</p>}</div>
}
function ResourceMeters({resources}:{resources:ReturnType<typeof deriveLivingHarbor>['resources']}){
 const types=[['tug','Tugs'],['pilot','Pilots'],['mooring','Mooring teams'],['equipment','Terminal equipment']]
 return <div className="lh-meter-list">{types.map(([type,name])=>{const r=resourceStatus(resources,type);const pct=r.total?r.available/r.total*100:0
 return <div className="lh-meter" key={type}><span>{name}</span><b>{r.unknown?'NO SOURCE':r.available+' / '+r.total+' available'}</b>
 <div className="lh-track"><div style={{width:pct+'%',background:type==='pilot'?'var(--lh-gold)':'var(--lh-mint)'}}/></div></div>})}</div>
}
function CallsList({calls,selected,onSelect}:{calls:LivingCall[];selected:string|null;onSelect:(id:string)=>void}){
 return <div className="lh-call-list">{calls.map((call,index)=><button type="button" key={call.id} className={'lh-call '+(selected===call.vesselId?'active':'')} onClick={()=>onSelect(call.vesselId)} aria-pressed={selected===call.vesselId}>
 <span className="lh-call-dot" data-tone={index%3===0?'mint':index%3===1?'blue':'gold'}/>
 <span className="lh-call-name">{call.name}<small>{call.berth}</small></span>
 <span className="lh-call-status">{call.status}</span>
 <time>ETA {formatTime(call.eta)}</time>
 </button>)}</div>
}
function Timeline({calls,selected,onSelect,preview}:{calls:LivingCall[];selected:string|null;onSelect:(id:string)=>void;preview:boolean}){
 const berths=[...new Set(calls.map(c=>c.berth))]
 return <div className="lh-timeline">
  <div className="lh-time-head"><span>BERTH / 24H HORIZON</span><div>{['00','04','08','12','16','20','24'].map(t=><small key={t}>{t}h</small>)}</div></div>
  {berths.map((berth,j)=><div className="lh-berth-row" key={berth}><strong>{berth}</strong><div className="lh-bars">{calls.filter(c=>c.berth===berth).map((call,index)=>{const pos=berthTimeline(call)
  return <button title={call.name+' · '+call.status} aria-label={call.name+' berth allocation'} onClick={()=>onSelect(call.vesselId)} key={call.id} className={'lh-timeline-block '+(selected===call.vesselId?'active':'')} data-tone={index===0&&j===0?'blue':index===1?'violet':j===1?'mint':'violet'} style={{left:pos.start+'%',width:Math.max(5,pos.width)+'%'}}>{call.name}</button>})}
  {preview&&j===1&&<div className="lh-timeline-ghost" title="Visual preview only; not an applied assignment">PROPOSED · NOT APPLIED</div>}</div></div>)}
  <div className="lh-timeline-foot">Recorded call windows only <span>•</span> Purple dashed = uncommitted visual proposal</div>
 </div>
}
function ResourceView({resources,isDemo}:{resources:ReturnType<typeof deriveLivingHarbor>['resources'];isDemo:boolean}){
 return <><Heading eyebrow="RESOURCES / DECLARED AVAILABILITY" title="The right resource, at the right berth.">{isDemo?"Every status comes from the fictional resource register—not scene animation.":"Resource availability comes from authorized operational records—not scene animation."}</Heading>
 <div className="lh-resource-cards">{resources.map(r=><article key={r.record_id}><span className="lh-small-label">{String(r.payload.resource_type??'Resource')}</span><h2>{recordName(r)}</h2><p>{r.payload.available===true?'Declared available':r.payload.available===false?'Declared unavailable':'No verified availability'}</p><small>Source: {r.source} · {formatTime(r.known_at)}</small></article>)}</div>
 <section className="lh-slab"><h2>Resource capacity</h2><ResourceMeters resources={resources}/></section></>
}
function ReportsView({data,isDemo}:{data:ReturnType<typeof deriveLivingHarbor>;isDemo:boolean}){
 const total=data.records.length,missing=data.records.filter(r=>!r.source).length
 return <><Heading eyebrow="REPORTS / TRACEABILITY" title="Follow the record, not just the animation.">{isDemo?"Every number is derived from isolated fictional records.":"Every number is derived from the authenticated operational record snapshot."}</Heading>
 <div className="lh-report-metrics"><article><span>RECORDED FACTS</span><strong>{total}</strong></article><article><span>PORT CALLS</span><strong>{data.calls.length}</strong></article><article><span>OPEN INCIDENTS</span><strong>{data.openIncidents}</strong></article><article><span>MISSING SOURCE</span><strong>{missing}</strong></article></div>
 <section className="lh-slab"><h2>Recent evidence records</h2>{data.records.slice(-9).reverse().map(r=><div className="lh-evidence-item" key={r.record_id}><span>{r.kind.toUpperCase()}</span><b>{recordName(r)}</b><small>{r.source} · rev {r.revision}</small></div>)}</section>
 <a className="lh-text-link" href={isDemo?"?showcase=1#evidence":"/#evidence"}>Open complete evidence and audit demonstration <ArrowUpRight size={16}/></a></>
}
function AdminView({isDemo}:{isDemo:boolean}){
 return <><Heading eyebrow="ADMINISTRATION / DEMO BOUNDARY" title="Trust is part of the interface.">{isDemo?"This public world contains no operational login or writable customer records.":"This read-only view uses your authenticated workspace. Return to the classic console for role-controlled changes."}</Heading>
 <div className="lh-admin-tiles"><article><ShieldCheck/><h2>Permission-bound operations</h2><p>The actual authenticated platform enforces roles and approvals on the server.</p></article><article><FileClock/><h2>Source and revision history</h2><p>Actions preserve provenance and effective/knowledge timestamps.</p></article><article><Layers/><h2>Isolated demonstration</h2><p>World movement is illustrative; real position requires sourced coordinates.</p></article></div>
 <a className="lh-text-link" href="/">Open operational console <ArrowUpRight size={16}/></a></>
}
export default function LivingHarborApp({operational}:{operational?:{workspace:Workspace;team:User[];fresh:boolean}}){
 const [view,setView]=useState<View>(viewFromHash)
 const [selected,setSelected]=useState<string|null>(null)
 const [preview,setPreview]=useState(false)
 const [quality,setQuality]=useState<'high'|'balanced'>('high')
 const [paused,setPaused]=useState(reduced)
 const [fallback,setFallback]=useState(()=>window.innerWidth<720||!webgl())
 const [visible,setVisible]=useState(!document.hidden)
 const [geo,setGeo]=useState(false)
 const isDemo=!operational
 const base=isDemo?'?showcase=1&living=1':'?living=1'
 const classic=isDemo?'?showcase=1#pulse':'/#pulse'
 const source=operational?.workspace??showcaseWorkspace
 const team=operational?.team??showcaseTeam
 const data=useMemo(()=>deriveLivingHarbor(source,isDemo),[source,isDemo])
 useEffect(()=>{const sync=()=>setView(viewFromHash());const visibility=()=>setVisible(!document.hidden);window.addEventListener('hashchange',sync);document.addEventListener('visibilitychange',visibility);return()=>{window.removeEventListener('hashchange',sync);document.removeEventListener('visibilitychange',visibility)}},[])
 const selectedCall=data.calls.find(c=>c.vesselId===selected)
 const select=(id:string)=>setSelected(s=>s===id?null:id)
 const coordinationItems=data.records.filter(r=>['handoff','commitment','obligation'].includes(r.kind)).map(record=>({record,creator_id:'demo-operator',actions:[]}))
 return <div className="lh-app" data-testid="living-harbor" data-theme="golden-hour">
  <aside className="lh-sidebar"><a className="lh-brand" href={base+'#overview'}><Waves size={31}/><span>Shorefront</span></a>
   <nav aria-label="Living Harbor workspaces">{views.map((item,index)=>{const Icon=icons[index];return <a key={item} href={base+'#'+fragments[index]} aria-current={item===view?'page':undefined}><Icon size={19}/>{item}</a>})}</nav>
   <div className="lh-sidebar-bottom"><span className="lh-indicator"/>ILLUSTRATIVE WORLD<br/><small>{isDemo?'READ ONLY · FICTIONAL':'REAL RECORDS · NO GEO POSITION'}</small><a href={classic} title="Return to the classic operator workspace" aria-label="Classic workspace">Classic workspace ↗</a></div>
  </aside>
  <main className="lh-main">
   <div className="lh-sky" aria-hidden="true"/>
   {!fallback&&!geo&&<Suspense fallback={<div className="lh-loading" role="status">Building living harbor…</div>}><HarborWorld vessels={data.vessels} selected={selected} onSelect={select} moving={!paused&&visible} proposal={preview} quality={quality} onWebGLError={()=>setFallback(true)}/></Suspense>}
   {(fallback||geo)&&<div className="lh-fallback"><div className="lh-fallback-water"><Waves size={70}/><h2>{geo?'Geo Truth / records':'Schematic fallback'}</h2><p>{geo?'Actual geographically attributed records are inspected in the standard operational map below.':'3D unavailable. Record controls remain usable.'}</p></div></div>}
   <div className="lh-scene-shade" aria-hidden="true"/>
   <div className="lh-topbar"><div className="lh-top-weather"><Sun size={25}/><div><b>GOLDEN HOUR</b><small>Illustrative environment</small></div></div><div className="lh-top-time"><b>{isDemo?'DEMO MODE':'OPERATOR RECORDS'}</b><small>{isDemo?'Scenario clock · fictional data':operational?.fresh?'Latest authenticated snapshot':'STALE / UNVERIFIED SNAPSHOT'}</small></div><div className="lh-top-profile"><span>{isDemo?"NO LIVE AIS":"POSITIONS ILLUSTRATIVE"}</span><div aria-hidden="true">S</div></div></div>
   {view==='Overview'&&!geo&&!fallback&&<section className="lh-hero"><h1>Shorefront</h1><p className="lh-hero-overline">MARITIME OPERATIONS<br/>INTELLIGENCE</p><span className="lh-cyan-rule"/><p className="lh-hero-meta">Vessels · Berths · Resources · Decisions</p></section>}
   {view==='Overview'&&<div className="lh-mode-rail" aria-label="Harbor world controls">
    <button onClick={()=>setGeo(g=>!g)} aria-pressed={geo}><MapPinned size={16}/>{geo?'Return to world':'Geo / records'}</button>
    <button onClick={()=>setPaused(p=>!p)} aria-pressed={paused}>{paused?<Play size={16}/>:<Pause size={16}/>} {paused?'Resume ambiance':'Pause ambiance'}</button>
    <button onClick={()=>setQuality(q=>q==='high'?'balanced':'high')}><SlidersHorizontal size={16}/>{quality==='high'?'High detail':'Balanced'}</button>
    <button onClick={()=>setPreview(p=>!p)} aria-pressed={preview}><Route size={16}/> {preview?'Close proposal':'Preview proposal'}</button>
   </div>}
   {view==='Overview'&&!geo&&!fallback&&<section className="lh-floating-calls lh-card" aria-label="Active port calls">
     <header><h2>Active Port Calls</h2><a href={base+'#port-calls'}>View All <ArrowUpRight size={16}/></a></header>
     <CallsList calls={data.calls} selected={selected} onSelect={select}/>
   </section>}
   {view==='Overview'&&!geo&&!fallback&&<div className="lh-bottom-deck">
     <section className="lh-card lh-timeline-card"><header><h2>Berth Timeline</h2><span>Recorded · next 24h</span></header><Timeline calls={data.calls} selected={selected} onSelect={select} preview={preview}/></section>
     <section className="lh-card lh-resources-card"><header><h2>Resource Status</h2><a href={base+'#resources'}>View All <ArrowUpRight size={16}/></a></header><ResourceMeters resources={data.resources}/></section>
   </div>}
   {selectedCall&&!geo&&!fallback&&<aside className="lh-inspector lh-card" aria-label={'Selected vessel '+selectedCall.name}>
     <header><span className="lh-small-label">SELECTED VESSEL</span><button aria-label="Close vessel inspector" onClick={()=>setSelected(null)}><X size={18}/></button></header>
     <h2>{selectedCall.name}</h2><span className="lh-state-pill">{selectedCall.status} · {selectedCall.berth}</span>
     <dl><div><dt>ETA</dt><dd>{formatTime(selectedCall.eta)}</dd></div><div><dt>ETD</dt><dd>{formatTime(selectedCall.etd)}</dd></div><div><dt>SOURCE</dt><dd>{selectedCall.source}</dd></div><div><dt>SCENE</dt><dd>Illustrative, not geolocated</dd></div></dl>
     <a href={base+'#port-calls'}>View call record <ArrowUpRight size={15}/></a>
   </aside>}
   {preview&&!geo&&<div className="lh-proposal-warning" role="status"><span/> VIOLET SCENARIO PREVIEW · VISUAL ONLY · NOT APPLIED</div>}
   {(view!=='Overview'||geo||fallback)&&<section className="lh-workspace-layer" aria-label={view+' operational workspace'}>
    <div className="lh-workspace-inner">
    {geo||fallback?<><Heading eyebrow="GEOGRAPHIC / RECORD TRUTH" title="Verify the actual recorded port picture.">This view deliberately avoids interpreting decorative animation as navigational telemetry.</Heading><OperationalPulse workspace={showcaseWorkspace} team={team} simulated {...showcaseActions}/></>:
    view==='Port Calls'?<><Heading eyebrow="VESSEL OPERATIONS / PORT CALLS" title="Every arrival connects to a decision.">Click a vessel, inspect its recorded berth and time window, and follow its source.</Heading><OperationalCalls workspace={showcaseWorkspace} {...showcaseActions}/></>:
    view==='Berth Planning'?<><Heading eyebrow="QUAY STRATEGY / BERTHS" title="See the horizon before you change it.">Violet marks uncommitted proposals; the operational plan remains read only.</Heading><OperationalPlan workspace={showcaseWorkspace} conflictsOverride={showcaseConflicts} {...showcaseActions}/></>:
    view==='Resources'?<ResourceView resources={data.resources} isDemo={isDemo}/>:
    view==='Operations'?<><Heading eyebrow="COORDINATION / COMMITMENTS" title="Keep every handoff accountable.">Operational work has an owner, evidence, and a recorded state.</Heading><ProductCoordination facts={data.records} team={team} writable={false} onRefresh={async()=>{}} onCreate={()=>{}} onEdit={()=>{}} itemsOverride={coordinationItems}/></>:
    view==='Incidents'?<><Heading eyebrow="INCIDENTS / HUMAN-REVIEWED RECOVERY" title="Find the disruption. Understand the impact.">A simulated disruption may have alternatives; none may be applied from this read-only view.</Heading><OperationalExceptions workspace={showcaseWorkspace} team={team} {...showcaseActions}/><a className="lh-text-link" href={isDemo?"?showcase=1#recovery":"/#recovery"}>Inspect full simulated recovery decision packet <ArrowUpRight size={16}/></a></>:
    view==='Reports'?<ReportsView data={data} isDemo={isDemo}/>:<AdminView isDemo={isDemo}/>}
    </div>
   </section>}
   <div className="lh-footer"><span><span className="lh-live-dot"/> {isDemo?"FICTIONAL HARBOR":"AUTHENTICATED RECORDS"} · ILLUSTRATIVE WORLD · READ ONLY</span><span>{data.callsCount} PLANNED CALLS · {data.openIncidents} OPEN INCIDENT</span><a href={isDemo?"?showcase=1#evidence":"/#evidence"}>Evidence <ArrowUpRight size={13}/></a></div>
  </main>
 </div>
}
