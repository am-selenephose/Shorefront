import type {Fact,Workspace} from '../productClient'
import {recordName} from '../productClient'
import type {WorldVessel} from './HarborWorld'
export type LivingCall={id:string;vesselId:string;name:string;berthId:string;berth:string;status:string;eta:string;etd:string;source:string;sourceAt:string}
const str=(value:unknown)=>typeof value==='string'?value:''
const anchors:[number,number][]=[[-23,-6],[-12,19],[-40,10],[3,-6]]
export function deriveLivingHarbor(workspace:Workspace, simulated=true){
 const records=workspace.records
 const by=(kind:string)=>records.filter(r=>r.kind===kind)
 const find=(kind:string,id:unknown)=>records.find(r=>r.kind===kind&&r.record_id===id)
 const calls:LivingCall[]=by('call').map(call=>{
   const vessel=find('vessel',call.payload.vessel_id),berth=find('berth',call.payload.berth_id)
   return {id:call.record_id,vesselId:str(call.payload.vessel_id),name:vessel?recordName(vessel):'Unknown vessel',berthId:str(call.payload.berth_id),berth:berth?recordName(berth):'Unassigned',status:str(call.payload.status)||'Unspecified',eta:str(call.payload.eta),etd:str(call.payload.etd),source:call.source,sourceAt:call.known_at}
 })
 const vessels:WorldVessel[]=calls.slice(0,4).map((call,index)=>({id:call.vesselId,name:call.name,status:call.status,x:anchors[index][0],z:anchors[index][1],kind:'cargo'}))
 // Two decorative support craft exist only in isolated fictional showcase.
 if(simulated)vessels.push({id:'demo-cosmetic-tug',name:'Harbor tug · illustration',status:'SIMULATED PATH',kind:'tug',x:-37,z:-28})
 if(simulated)vessels.push({id:'demo-cosmetic-pilot',name:'Pilot boat · illustration',status:'SIMULATED PATH',kind:'pilot',x:-14,z:32})
 const resources=by('resource')
 const incidents=by('incident').filter(r=>r.payload.status!=='resolved')
 return {calls,vessels,resources,incidents,berths:by('berth'),tasks:by('task'),records,
  port:by('port')[0],callsCount:calls.filter(c=>!['cancelled','departed'].includes(c.status)).length,
  openIncidents:incidents.length}
}
export function berthTimeline(call:LivingCall){
 const eta=Date.parse(call.eta),etd=Date.parse(call.etd)
 if(!Number.isFinite(eta)||!Number.isFinite(etd)||etd<=eta)return {start:0,width:0,valid:false}
 const horizonStart=Math.floor(Date.now()/3600000)*3600000
 const start=Math.min(100,Math.max(0,(eta-horizonStart)/86400000*100))
 const end=Math.min(100,Math.max(0,(etd-horizonStart)/86400000*100))
 return {start,width:Math.max(0,end-start),valid:true}
}
export function resourceStatus(facts:Fact[],type:string){
 const items=facts.filter(r=>r.kind==='resource'&&r.payload.resource_type===type)
 return {total:items.length,available:items.filter(r=>r.payload.available===true).length,unknown:items.length===0}
}
