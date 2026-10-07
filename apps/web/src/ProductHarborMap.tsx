import {useEffect, useMemo, useRef, useState} from 'react'
import * as maplibregl from 'maplibre-gl'
import type {Map, Marker} from 'maplibre-gl'
import mapWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import 'maplibre-gl/dist/maplibre-gl.css'
import {recordName, type Fact} from './productClient'

maplibregl.setWorkerUrl(mapWorkerUrl)

type Props = {
  facts: Fact[]
  focusedCallId: string
  writable: boolean
  onCreate: (kind:string, payload?:Fact['payload'])=>void
  onEdit: (record:Fact)=>void
}

type Point = {lon:number; lat:number}
const finite = (value:unknown): value is number => typeof value === 'number' && Number.isFinite(value)
const point = (record:Fact): Point | null => finite(record.payload.longitude) && finite(record.payload.latitude)
  ? {lon:record.payload.longitude, lat:record.payload.latitude} : null

export default function ProductHarborMap({facts,focusedCallId,writable,onCreate,onEdit}:Props) {
  const node = useRef<HTMLDivElement|null>(null)
  const mapRef = useRef<Map|null>(null)
  const markers = useRef<Marker[]>([])
  const [showBerths,setShowBerths]=useState(true)
  const [showCalls,setShowCalls]=useState(true)
  const [exceptionsOnly,setExceptionsOnly]=useState(false)
  const ports = useMemo(()=>facts.filter(f=>f.kind==='port'),[facts])
  const berths = useMemo(()=>facts.filter(f=>f.kind==='berth'),[facts])
  const calls = useMemo(()=>facts.filter(f=>f.kind==='call' && !['departed','cancelled'].includes(String(f.payload.status))),[facts])
  const vessels = useMemo(()=>facts.filter(f=>f.kind==='vessel'),[facts])
  const incidents = useMemo(()=>facts.filter(f=>f.kind==='incident' && f.payload.status!=='resolved'),[facts])
  const geoPorts = useMemo(()=>ports.filter(p=>point(p)),[ports])
  const geoBerths = useMemo(()=>berths.filter(b=>point(b)),[berths])
  const firstPort = ports[0]
  const firstUnmappedBerth = berths.find(b=>!point(b))
  const hasGeography = geoPorts.length>0 || geoBerths.length>0

  useEffect(()=>{
    if (!node.current || mapRef.current) return
    const map = new maplibregl.Map({
      container:node.current,
      center:[0,20], zoom:1.35, minZoom:1,
      dragRotate:false, pitchWithRotate:false,
      style:'https://tiles.openfreemap.org/styles/liberty',
    })
    map.addControl(new maplibregl.NavigationControl({showCompass:false}), 'bottom-right')
    mapRef.current=map
    return()=>{markers.current.forEach(marker=>marker.remove());markers.current=[];map.remove();mapRef.current=null}
  },[])

  useEffect(()=>{
    const map=mapRef.current
    if(!map || !node.current) return
    const sync=()=>{
      markers.current.forEach(marker=>marker.remove()); markers.current=[]
      const tokens=getComputedStyle(node.current!)
      const token=(name:string,fallback:string)=>tokens.getPropertyValue(name).trim() || fallback
      const points:Point[]=[]
      for (const port of geoPorts) {
        const location=point(port)!; points.push(location)
        const el=document.createElement('div'); el.className='product-map-port-marker'; el.title=`Port: ${recordName(port)}`
        const core=document.createElement('i'); const label=document.createElement('span'); label.textContent=recordName(port); el.append(core,label)
        markers.current.push(new maplibregl.Marker({element:el,anchor:'center'}).setLngLat([location.lon,location.lat]).addTo(map))
      }
      for (const berth of geoBerths) {
        const location=point(berth)!; points.push(location)
        if(showBerths){
          const berthEl=document.createElement('div'); berthEl.className='product-map-berth-marker'; berthEl.title=`Recorded berth: ${recordName(berth)}`
          const pin=document.createElement('i'); const label=document.createElement('span'); label.textContent=recordName(berth); berthEl.append(pin,label)
          markers.current.push(new maplibregl.Marker({element:berthEl,anchor:'bottom-left',offset:[8,-6]}).setLngLat([location.lon,location.lat]).addTo(map))
        }
        const linked=calls.filter(call=>call.payload.berth_id===berth.record_id)
        linked.forEach((call,index)=>{
          const vessel=vessels.find(v=>v.record_id===call.payload.vessel_id)
          const openIncidents=incidents.filter(incident=>incident.payload.call_id===call.record_id).length
          if(!showCalls || (exceptionsOnly && !openIncidents)) return
          const callEl=document.createElement('div')
          callEl.className=`product-map-call-marker coord-harbor-call${call.record_id===focusedCallId?' is-focused':''}${openIncidents?' has-incident':''}`
          callEl.style.setProperty('--call-stack',String(index))
          const name=document.createElement('b'); name.textContent=vessel?recordName(vessel):call.record_id
          const status=document.createElement('span'); status.textContent=`${String(call.payload.status)}${openIncidents?` · ${openIncidents} open incident${openIncidents===1?'':'s'}`:''}`
          callEl.append(name,status)
          markers.current.push(new maplibregl.Marker({element:callEl,anchor:'top-left',offset:[14,16+(index*46)]}).setLngLat([location.lon,location.lat]).addTo(map))
        })
      }
      if(points.length===0){map.jumpTo({center:[0,20],zoom:1.35})}
      else if(points.length===1){map.jumpTo({center:[points[0].lon,points[0].lat],zoom:13})}
      else {
        const bounds=new maplibregl.LngLatBounds()
        points.forEach(p=>bounds.extend([p.lon,p.lat]))
        map.fitBounds(bounds,{padding:90,maxZoom:13,duration:0})
      }
      map.resize()
      node.current!.style.setProperty('--map-marker',token('--teal','#2b7477'))
      node.current!.style.setProperty('--map-danger',token('--danger','#a84747'))
      node.current!.style.setProperty('--map-surface',token('--surface','#f6f3df'))
      node.current!.style.setProperty('--map-foreground',token('--foreground','#193033'))
    }
    // DOM markers and viewport focus do not depend on vector-style readiness.
    // Sync immediately so a coordination focus change cannot miss a one-shot
    // map load event while style resources are still settling.
    sync()
    const observer=new MutationObserver(sync)
    observer.observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']})
    return()=>observer.disconnect()
  },[geoPorts,geoBerths,calls,vessels,incidents,focusedCallId,showBerths,showCalls,exceptionsOnly])

  const setup = !hasGeography ? (
    <div className="product-map-setup">
      <b>Port geography is not configured.</b>
      <p>Add verified port or berth coordinates. Shorefront keeps the geographic base map visible, but it will not invent your terminal location.</p>
      <div className="product-actions">
        {!firstPort && <button type="button" disabled={!writable} onClick={()=>onCreate('port')}>Set up port geography</button>}
        {firstPort && <button type="button" disabled={!writable} onClick={()=>onEdit(firstPort)}>Add coordinates to {recordName(firstPort)}</button>}
        {firstPort && <button type="button" disabled={!writable} onClick={()=>firstUnmappedBerth?onEdit(firstUnmappedBerth):onCreate('berth',{port_id:firstPort.record_id})}>{firstUnmappedBerth?'Add berth coordinates':'Add mapped berth'}</button>}
      </div>
    </div>
  ) : geoBerths.length===0 ? (
    <div className="product-map-setup compact">
      <b>Port location recorded. No berth geometry yet.</b>
      <p>Add a berth coordinate to place berth-linked operational calls on the map.</p>
      <button type="button" disabled={!writable} onClick={()=>firstUnmappedBerth?onEdit(firstUnmappedBerth):firstPort&&onCreate('berth',{port_id:firstPort.record_id})}>Add berth coordinates</button>
    </div>
  ) : null

  return <section className="product-geographic-map" role="region" aria-label="Operational geographic harbor map">
    <div className="product-map-canvas" ref={node}/>
    <div className="product-map-layers" role="group" aria-label="Map layers">
      <span>LAYERS</span>
      <button type="button" aria-pressed={showBerths} onClick={()=>setShowBerths(value=>!value)}>Berths</button>
      <button type="button" aria-pressed={showCalls} onClick={()=>setShowCalls(value=>!value)}>Calls</button>
      <button type="button" aria-pressed={exceptionsOnly} disabled={!showCalls} onClick={()=>setExceptionsOnly(value=>!value)}>Exceptions only</button>
    </div>
    {setup}
    <div className="product-map-legend">
      <span><i className="port"/> Recorded port</span>
      <span><i className="berth"/> Recorded berth</span>
      <span><i className="call"/> Active call at berth</span>
      <strong>Berth-linked calls, not live AIS positions.</strong>
    </div>
  </section>
}
