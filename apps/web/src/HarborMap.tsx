import {useEffect,useRef} from 'react'
import * as maplibregl from 'maplibre-gl'
import type {Map} from 'maplibre-gl'
import mapWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import 'maplibre-gl/dist/maplibre-gl.css'
import type {HarborState} from './types'

// Emit the module worker and its imports as a real Vite asset. The library's
// relative worker URL otherwise points at a missing file after production build.
maplibregl.setWorkerUrl(mapWorkerUrl)

export function HarborMap({state,theme}:{state:HarborState;theme:'light'|'dark'}){
 const node=useRef<HTMLDivElement|null>(null), mapRef=useRef<Map|null>(null)
 useEffect(()=>{if(!node.current||mapRef.current)return
  const map=new maplibregl.Map({container:node.current,center:[state.center.lon,state.center.lat],zoom:9.9,attributionControl:false,style:{version:8,sources:{osm:{type:'raster',tiles:['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],tileSize:256,attribution:'© OpenStreetMap contributors'}},layers:[{id:'osm',type:'raster',source:'osm',paint:{'raster-saturation':-0.65,'raster-brightness-min':0.08,'raster-brightness-max':0.98,'raster-contrast':0.05}}]}})
  mapRef.current=map;return()=>{map.remove();mapRef.current=null}},[])
 useEffect(()=>{const map=mapRef.current;if(!map)return
  const sync=()=>{
   // MapLibre canvas paint reads the shell's semantic tokens instead of duplicating colors.
   const tokens=getComputedStyle(node.current!)
   const color=(name:string)=>tokens.getPropertyValue(name).trim()
   const vesselData={type:'FeatureCollection' as const,features:state.vessels.map(v=>({type:'Feature' as const,geometry:{type:'Point' as const,coordinates:[v.position.lon,v.position.lat]},properties:{name:v.name,status:v.status,type:v.vessel_type}}))}
   const berthData={type:'FeatureCollection' as const,features:state.berths.map(b=>({type:'Feature' as const,geometry:{type:'Point' as const,coordinates:[b.position.lon,b.position.lat]},properties:{name:b.name,status:b.status}}))}
   if(!map.getSource('vessels')){map.addSource('vessels',{type:'geojson',data:vesselData});map.addLayer({id:'vessels',type:'circle',source:'vessels',paint:{'circle-radius':7,'circle-color':color('--map-vessel'),'circle-stroke-width':2,'circle-stroke-color':color('--map-outline')}});map.addLayer({id:'vessel-labels',type:'symbol',source:'vessels',layout:{'text-field':['get','name'],'text-offset':[0,1.35],'text-size':11},paint:{'text-color':color('--map-label'),'text-halo-color':color('--map-label-halo'),'text-halo-width':1.2}})}else{(map.getSource('vessels') as maplibregl.GeoJSONSource).setData(vesselData)}
   if(!map.getSource('berths')){map.addSource('berths',{type:'geojson',data:berthData});map.addLayer({id:'berths',type:'circle',source:'berths',paint:{'circle-radius':5,'circle-color':color('--map-berth'),'circle-stroke-width':1.5,'circle-stroke-color':color('--map-outline')}})}else{(map.getSource('berths') as maplibregl.GeoJSONSource).setData(berthData)}
   // Repaint the existing canvas, retaining its viewport and live data sources.
   map.setPaintProperty('osm','raster-brightness-min',theme==='dark'?0.04:0.08)
   map.setPaintProperty('osm','raster-brightness-max',theme==='dark'?0.34:0.98)
   map.setPaintProperty('osm','raster-saturation',theme==='dark'?-0.85:-0.65)
   map.setPaintProperty('osm','raster-contrast',theme==='dark'?0.15:0.05)
   map.setPaintProperty('vessels','circle-color',color('--map-vessel'))
   map.setPaintProperty('vessels','circle-stroke-color',color('--map-outline'))
   map.setPaintProperty('berths','circle-color',color('--map-berth'))
   map.setPaintProperty('berths','circle-stroke-color',color('--map-outline'))
   map.setPaintProperty('vessel-labels','text-color',color('--map-label'))
   map.setPaintProperty('vessel-labels','text-halo-color',color('--map-label-halo'))
  }
  // The style can be ready while tiles are still loading; do not wait for a
  // one-shot load event that has already fired when only the theme changes.
  if(map.getLayer('osm'))sync();else map.once('load',sync)
  return()=>{map.off('load',sync)}
 },[state,theme])
 return <div className="harbor-map" ref={node}/>
}
