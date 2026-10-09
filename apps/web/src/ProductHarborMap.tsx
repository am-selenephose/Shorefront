import {useEffect, useMemo, useRef, useState} from 'react'
import * as maplibregl from 'maplibre-gl'
import type {Map, Marker} from 'maplibre-gl'
import mapWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import 'maplibre-gl/dist/maplibre-gl.css'
import {recordName, type Fact} from './productClient'
import {CoordinationMapLoading} from './CoordinationMapLoading'

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
  const container = useRef<HTMLElement|null>(null)
  const node = useRef<HTMLDivElement|null>(null)
  const mapRef = useRef<Map|null>(null)
  const fittedGeography = useRef<string|null>(null)
  const markers = useRef<Marker[]>([])
  const [showBerths,setShowBerths]=useState(true)
  const [showCalls,setShowCalls]=useState(true)
  const [exceptionsOnly,setExceptionsOnly]=useState(false)
  const [mapUnavailable,setMapUnavailable]=useState<string|null>(null)
  const [mapReady,setMapReady]=useState(false)
  const [nativeFullscreen,setNativeFullscreen]=useState(false)
  const [fallbackFullscreen,setFallbackFullscreen]=useState(false)
  const expanded=nativeFullscreen||fallbackFullscreen

  // Keep the same MapLibre instance and geographic viewport when resizing.
  // The browser's Fullscreen API is preferred, with a fixed-viewport
  // fallback for browsers that do not expose it (including some mobile UAs).
  useEffect(()=>{
    let frame=0
    const resize=()=>{
      cancelAnimationFrame(frame)
      frame=requestAnimationFrame(()=>mapRef.current?.resize())
    }
    const onFullscreenChange=()=>{
      setNativeFullscreen(document.fullscreenElement===container.current)
      resize()
    }
    const onEscape=(event:KeyboardEvent)=>{
      if(event.key!=='Escape')return
      if(fallbackFullscreen){
        event.preventDefault()
        setFallbackFullscreen(false)
      }else if(document.fullscreenElement===container.current){
        // Also handle webviews that deliver Escape to the app.
        void document.exitFullscreen().catch(()=>{})
      }
    }
    const observer=new ResizeObserver(resize)
    if(container.current)observer.observe(container.current)
    if(node.current)observer.observe(node.current)
    document.addEventListener('fullscreenchange',onFullscreenChange)
    document.addEventListener('keydown',onEscape)
    window.addEventListener('resize',resize)
    resize()
    return()=>{
      cancelAnimationFrame(frame)
      observer.disconnect()
      document.removeEventListener('fullscreenchange',onFullscreenChange)
      document.removeEventListener('keydown',onEscape)
      window.removeEventListener('resize',resize)
    }
  },[fallbackFullscreen])

  useEffect(()=>{
    if(!fallbackFullscreen)return
    const previous=document.body.style.overflow
    document.body.style.overflow='hidden'
    return()=>{document.body.style.overflow=previous}
  },[fallbackFullscreen])

  async function toggleFullscreen(){
    if(document.fullscreenElement===container.current){
      await document.exitFullscreen()
      return
    }
    if(fallbackFullscreen){setFallbackFullscreen(false);return}
    if(container.current?.requestFullscreen){
      try {
        await container.current.requestFullscreen()
        return
      } catch {
        // Browser denied native fullscreen: use the accessible viewport mode.
      }
    }
    setFallbackFullscreen(true)
  }

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
  const needsSchematic = berths.length>0 && geoBerths.length===0
  const showSchematic = needsSchematic || Boolean(mapUnavailable&&berths.length)

  useEffect(()=>{
    if (!node.current || mapRef.current || mapUnavailable) return
    try {
      const probe=document.createElement('canvas')
      const webgl2=probe.getContext('webgl2')
      if(!webgl2){
        setMapUnavailable('WebGL2 is unavailable in this browser or graphics environment.')
        return
      }
      webgl2.getExtension('WEBGL_lose_context')?.loseContext()
      const map = new maplibregl.Map({
        container:node.current,
        center:[0,20], zoom:1.35, minZoom:1,
        dragRotate:false, pitchWithRotate:false,
        style:'https://tiles.openfreemap.org/styles/liberty',
      })
      map.addControl(new maplibregl.NavigationControl({showCompass:false}), 'bottom-right')
      map.on('load',()=>setMapReady(true))
      if(map.loaded()) setMapReady(true)
      mapRef.current=map
      return()=>{markers.current.forEach(marker=>marker.remove());markers.current=[];map.remove();mapRef.current=null;fittedGeography.current=null}
    } catch(error) {
      const detail=error instanceof Error&&error.message ? error.message : 'The map renderer could not start.'
      setMapUnavailable(detail)
    }
  },[mapUnavailable])

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
      // A call focus, record refresh, theme change or map layer toggle
      // must not overwrite the operator's current zoom/pan. Refit only when
      // verified geographic coordinates actually change.
      const geographyKey=[...geoPorts,...geoBerths]
        .map(record=>record.kind+':'+record.record_id+':'+record.payload.longitude+':'+record.payload.latitude)
        .sort().join('|')
      if(fittedGeography.current!==geographyKey){
        fittedGeography.current=geographyKey
        if(points.length===0){map.jumpTo({center:[0,20],zoom:1.35})}
        else if(points.length===1){map.jumpTo({center:[points[0].lon,points[0].lat],zoom:13})}
        else {
          const bounds=new maplibregl.LngLatBounds()
          points.forEach(p=>bounds.extend([p.lon,p.lat]))
          map.fitBounds(bounds,{padding:90,maxZoom:13,duration:0})
        }
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
    <div className={`product-map-setup${needsSchematic?' compact schematic-setup':''}`}>
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

  const schematic = showSchematic ? <div className="product-map-schematic" role="region" aria-label="Schematic berth digital twin">
    <header><div><span className="product-index">SCHEMATIC · NOT GEOGRAPHIC</span><b>Recorded berth relationships</b></div><small>{mapUnavailable?'Map renderer unavailable · recorded coordinates retained, positions not displayed':'Coordinates missing · no invented positions'}</small></header>
    <div className="product-map-schematic-grid">{berths.slice(0,8).map((berth,index)=>{
      const linked=calls.filter(call=>call.payload.berth_id===berth.record_id)
      return <div className={`product-map-schematic-lane${linked.some(call=>call.record_id===focusedCallId)?' is-focused':''}`} key={berth.record_id}>
        <div className="product-map-schematic-berth"><span>{String(index+1).padStart(2,'0')}</span><b>{recordName(berth)}</b><small>{berth.payload.max_length_m?`${berth.payload.max_length_m}m max`:'limits not recorded'}</small></div>
        <div className="product-map-schematic-track">{showCalls?linked.filter(call=>!exceptionsOnly||incidents.some(incident=>incident.payload.call_id===call.record_id)).map(call=>{
          const vessel=vessels.find(v=>v.record_id===call.payload.vessel_id)
          const openIncidents=incidents.filter(incident=>incident.payload.call_id===call.record_id).length
          return <div className={`product-map-schematic-call${call.record_id===focusedCallId?' is-focused':''}${openIncidents?' has-incident':''}`} key={call.record_id}><b>{vessel?recordName(vessel):call.record_id}</b><span>{String(call.payload.status)}</span><small>{openIncidents?`${openIncidents} open incident${openIncidents===1?'':'s'}`:'recorded call'}</small></div>
        }):null}{!linked.length&&<span className="product-map-schematic-empty">No active call</span>}</div>
      </div>
    })}</div>
  </div> : null

  return <section ref={container} className={'product-geographic-map'+(fallbackFullscreen?' is-map-expanded':'')} data-map-expanded={expanded?'true':'false'} role="region" aria-label="Operational geographic harbor map">
    <div className="product-map-fullscreen-header" aria-hidden={!expanded}>
      <div><span className="product-index">SHOREFRONT / HARBOR VISUALIZATION</span><strong>Harbor map</strong><small>Recorded berths and calls, never live AIS positions</small></div>
      <span className="product-map-fullscreen-hint">ESC TO EXIT</span>
    </div>
    <div className={'product-map-canvas'+(mapUnavailable?' is-unavailable':'')} ref={node}>
      {mapUnavailable&&<div className="product-map-unavailable" role="status" aria-label="Geographic map unavailable">
        <span className="product-index">GEOGRAPHIC MAP DEGRADED</span>
        <b>Live map rendering is unavailable in this browser.</b>
        <p>{mapUnavailable} Shorefront is keeping the recorded calls, berth horizon, coordination and evidence surfaces available instead of hiding operational context.</p>
        <small>No geographic position is being inferred or substituted.</small>
      </div>}
    </div>
    {!mapReady&&!mapUnavailable&&<div className="product-map-pending-overlay"><CoordinationMapLoading facts={facts} focusedCallId={focusedCallId}/></div>}
    {schematic}
    <div className="product-map-layers" role="group" aria-label="Map layers">
      <span>LAYERS</span>
      <button type="button" className="product-map-expand-toggle" aria-label={expanded?'Exit full screen map':'Full screen map'} aria-pressed={expanded} onClick={()=>void toggleFullscreen()}>
        <span aria-hidden="true">{expanded?'↙':'⛶'}</span>{expanded?'Exit full screen':'Full screen'}
      </button>
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
