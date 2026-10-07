import {useEffect, useState} from 'react'
import {OperationalCalls, OperationalExceptions, OperationalPlan, OperationalPulse, type Conflict, type OperationalActions} from './ProductWorkspaces'
import {dateLabel, recordName, type Fact, type User, type Workspace} from './productClient'
import ProductCoordination, {type CoordinationItem} from './ProductCoordination'
import './product.css'

const views = ['Pulse','Plan','Calls','Exceptions','Coordination','Recovery','Evidence'] as const
type ShowcaseView = typeof views[number]
const demoUser:User = {id:'demo-operator',email:'demo@shorefront.invalid',name:'Demo Harbor Operator',role:'viewer',active:1}
const demoSupervisor:User = {id:'demo-supervisor',email:'supervisor@shorefront.invalid',name:'Demo Duty Supervisor',role:'supervisor',active:1}
const team=[demoUser,demoSupervisor]
const base=Date.now()
const iso=(hours:number)=>new Date(base+hours*3600000).toISOString()
let seq=0
const fact=(kind:string,record_id:string,payload:Fact['payload'],source='SIMULATED SOURCE'):Fact=>({sequence:++seq,kind,record_id,revision:1,valid_at:iso(-1),known_at:iso(-1),source,actor_id:'showcase-fixture',payload})

const records:Fact[]=[
  fact('port','demo-port',{name:'Northstar Container Harbor',timezone:'UTC',latitude:51.9509,longitude:4.1365}),
  fact('berth','north-quay',{name:'North Quay',port_id:'demo-port',max_length_m:320,latitude:51.9548,longitude:4.1279}),
  fact('berth','east-quay',{name:'East Quay',port_id:'demo-port',max_length_m:280,latitude:51.9473,longitude:4.1450}),
  fact('vessel','mv-aurora',{name:'MV Aurora',length_m:248}),
  fact('vessel','pacific-meridian',{name:'Pacific Meridian',length_m:272}),
  fact('vessel','northstar-atlas',{name:'Northstar Atlas',length_m:214}),
  fact('call','call-aurora',{vessel_id:'mv-aurora',berth_id:'north-quay',eta:iso(1),etd:iso(6),status:'planned'}),
  fact('call','call-meridian',{vessel_id:'pacific-meridian',berth_id:'north-quay',eta:iso(4),etd:iso(9),status:'planned'}),
  fact('call','call-atlas',{vessel_id:'northstar-atlas',berth_id:'east-quay',eta:iso(2),etd:iso(7),status:'planned'}),
  fact('resource','tug-14',{name:'Tug 14',resource_type:'tug',available:false}),
  fact('resource','tug-08',{name:'Tug 08',resource_type:'tug',available:true}),
  fact('resource','pilot-03',{name:'Pilot 03',resource_type:'pilot',available:true}),
  fact('incident','incident-tug-14',{title:'Tug 14 unavailable',detail:'Assigned assist tug reported unavailable before MV Aurora berth window.',severity:'high',status:'open',call_id:'call-aurora'}),
  fact('task','task-reassign',{title:'Confirm alternate tug assignment',status:'in_progress',due_at:iso(.5),assignee_id:'demo-operator',call_id:'call-aurora',incident_id:'incident-tug-14'}),
  fact('handoff','handoff-berth',{title:'Updated berth window handoff',status:'sent',due_at:iso(1),recipient_id:'demo-supervisor',call_id:'call-aurora',note:'Recipient confirmation still required.'}),
  fact('commitment','commitment-pilot',{title:'Pilot boarding commitment',status:'accepted',due_at:iso(.75),recipient_id:'demo-operator',call_id:'call-aurora',note:'Boarding window accepted subject to final movement authority.'}),
  fact('obligation','obligation-docs',{title:'Departure document review',status:'active',due_at:iso(5),assignee_id:'demo-supervisor',call_id:'call-aurora',note:'Evidence pack must be reviewed before departure handoff.'}),
]
const workspace:Workspace={runtime_mode:'operational',installation_id:'showcase-static',records,attention:records.filter(r=>r.kind==='task'),read_at:iso(0),user:demoUser}
const conflicts:Conflict[]=[{kind:'berth_overlap',record_ids:['call-aurora','call-meridian'],explanation:'MV Aurora and Pacific Meridian overlap on North Quay from the recorded call windows.'}]
const actions:OperationalActions={writable:false,onCreate:()=>{},onEdit:()=>{}}

function ThemeButton(){
  const [dark,setDark]=useState(document.documentElement.dataset.theme==='dark')
  return <button onClick={()=>{const next=dark?'light':'dark';document.documentElement.dataset.theme=next;setDark(!dark)}}>{dark?'Light mode':'Dark mode'}</button>
}
function readView():ShowcaseView{return views.find(v=>`#${v.toLowerCase()}`===location.hash)??'Pulse'}

const demoCoordinationItems:CoordinationItem[]=records
  .filter(record=>['handoff','commitment','obligation'].includes(record.kind))
  .map(record=>({record,creator_id:'demo-operator',actions:[]}))

function ShowcaseCoordination(){
  return <ProductCoordination facts={records} team={team} writable={false} onRefresh={async()=>{}} onCreate={()=>{}} onEdit={()=>{}} itemsOverride={demoCoordinationItems}/>
}

function ShowcaseRecovery(){
  const options=[
    {name:'Option A · Reassign Tug 08',delay:'11 min',conflicts:'0 new conflicts',exposure:'$9k modeled',confidence:'HIGH'},
    {name:'Option B · Shift Aurora to East Quay',delay:'20 min',conflicts:'1 resource conflict',exposure:'$17k modeled',confidence:'MEDIUM'},
    {name:'Option C · Hold current plan',delay:'42 min',conflicts:'2 downstream impacts',exposure:'$38k modeled',confidence:'HIGH'},
  ]
  return <div className="ops-workspace"><section className="ops-heading"><span className="product-index">RECOVERY / SIMULATED DECISION PACKET</span><h1>Compare recovery paths before a human decides.</h1><p>These values are fictional demo outputs. Operational Shorefront only records calculations backed by its configured decision inputs.</p></section><div className="showcase-recovery-baseline"><span>CURRENT STATE</span><b>MV Aurora · Tug 14 unavailable</b><p>42 min simulated delay · 2 downstream impacts · $38k simulated exposure</p></div><div className="showcase-recovery-grid">{options.map((option,index)=><article className={`showcase-option ${index===0?'preferred':''}`} key={option.name}><span className="product-index">{index===0?'PREFERRED SIMULATION':'SIMULATED ALTERNATIVE'}</span><h2>{option.name}</h2><dl><div><dt>PROJECTED DELAY</dt><dd>{option.delay}</dd></div><div><dt>CONFLICTS</dt><dd>{option.conflicts}</dd></div><div><dt>EXPOSURE</dt><dd>{option.exposure}</dd></div><div><dt>TRUST</dt><dd>{option.confidence}</dd></div></dl><button disabled>Human approval required</button></article>)}</div><aside className="product-boundary"><b>Demo only.</b><p>No option can mutate operational data from this showcase. There is no vessel actuation path.</p></aside></div>
}

function ShowcaseEvidence(){
  const evidence=[
    ['AIS position feed','SIMULATED SOURCE','observed 14s ago','healthy'],
    ['Tug availability board','SIMULATED SOURCE','received 22s ago','conflict detected'],
    ['Terminal berth plan','SIMULATED SOURCE','revision 7','healthy'],
    ['Pilot commitment','SIMULATED SOURCE','accepted','healthy'],
  ]
  return <div className="ops-workspace"><section className="ops-heading"><span className="product-index">EVIDENCE / SIMULATED CONTEXT</span><h1>Every demo decision keeps its context.</h1><p>Source, timing, conflict state and human authority remain visible instead of disappearing behind a recommendation.</p></section><section className="ops-panel"><header><div><span className="product-index">TRUST ENVELOPE</span><h2>Evidence used by the simulated recovery packet</h2></div><b>{evidence.length}</b></header><div className="showcase-evidence-list">{evidence.map(([name,source,age,state])=><article key={name}><div><b>{name}</b><span>{source}</span></div><div><span>{age}</span><em>{state}</em></div></article>)}</div></section><section className="ops-panel"><header><div><span className="product-index">TWO-CLOCK REPLAY</span><h2>What was known when the decision was reviewed?</h2></div></header><div className="showcase-timeline"><div><span>14:04</span><b>Tug availability conflict received</b><small>knowledge time</small></div><div><span>14:06</span><b>Recovery options generated</b><small>decision input snapshot</small></div><div><span>14:08</span><b>Duty supervisor review pending</b><small>human authority boundary</small></div></div></section></div>
}

export default function ShowcaseApp(){
  const [view,setView]=useState<ShowcaseView>(readView)
  useEffect(()=>{const sync=()=>setView(readView());window.addEventListener('hashchange',sync);return()=>window.removeEventListener('hashchange',sync)},[])
  return <div className="product-shell showcase-shell"><aside className="product-sidebar"><a href="?showcase=1#pulse" className="product-wordmark">SHOREFRONT<span>PUBLIC PRODUCT SHOWCASE</span></a><div className="showcase-badge">SIMULATED DEMO · READ ONLY</div><nav aria-label="Showcase workspaces">{views.map((item,index)=><a key={item} href={`?showcase=1#${item.toLowerCase()}`} aria-current={view===item?'page':undefined}><span aria-hidden="true">0{index+1}</span>{item}</a>)}</nav><div className="product-sidebar-foot"><span className="product-index">ISOLATED SHOWCASE</span><strong>Fictional harbor data</strong><small>No operational database access</small><a className="showcase-signin" href="/">Return to sign in</a></div></aside><main><header className="product-topbar"><span className="showcase-banner">SIMULATED DEMO · READ ONLY</span><div className="showcase-top-actions"><a href="/">Return to sign in</a><ThemeButton/></div></header><section className="showcase-contextline"><div><span className="product-index">FICTIONAL PORT / PRODUCT WALKTHROUGH</span><b>Northstar Container Harbor</b></div><p>Simulated disruption · isolated read-only data · no operational database access</p></section>
    {view==='Pulse'&&<OperationalPulse workspace={workspace} team={team} simulated {...actions}/>}
    {view==='Plan'&&<OperationalPlan workspace={workspace} conflictsOverride={conflicts} {...actions}/>}
    {view==='Calls'&&<OperationalCalls workspace={workspace} {...actions}/>}
    {view==='Exceptions'&&<OperationalExceptions workspace={workspace} team={team} {...actions}/>}
    {view==='Coordination'&&<ShowcaseCoordination/>}
    {view==='Recovery'&&<ShowcaseRecovery/>}
    {view==='Evidence'&&<ShowcaseEvidence/>}
  </main></div>
}
