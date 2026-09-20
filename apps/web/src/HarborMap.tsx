import {useEffect,useRef} from 'react'
import * as maplibregl from 'maplibre-gl'
import type {Map} from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type {HarborState} from './types'

export function HarborMap({state}:{state:HarborState}){
 const node=useRef<HTMLDivElement|null>(null), mapRef=useRef<Map|null>(null)
 useEffect(()=>{if(!node.current||mapRef.current)return
  const map=new maplibregl.Map({container:node.current,center:[state.center.lon,state.center.lat],zoom:9.9,attributionControl:false,style:{version:8,sources:{osm:{type:'raster',tiles:['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],tileSize:256,attribution:'© OpenStreetMap contributors'}},layers:[{id:'osm',type:'raster',source:'osm',paint:{'raster-saturation':-0.8,'raster-brightness-min':0.14,'raster-brightness-max':0.56,'raster-contrast':0.22}}]}})
  mapRef.current=map;return()=>{map.remove();mapRef.current=null}},[])
 useEffect(()=>{const map=mapRef.current;if(!map)return
  const sync=()=>{const vesselData={type:'FeatureCollection' as const,features:state.vessels.map(v=>({type:'Feature' as const,geometry:{type:'Point' as const,coordinates:[v.position.lon,v.position.lat]},properties:{name:v.name,status:v.status,type:v.vessel_type}}))}
   const berthData={type:'FeatureCollection' as const,features:state.berths.map(b=>({type:'Feature' as const,geometry:{type:'Point' as const,coordinates:[b.position.lon,b.position.lat]},properties:{name:b.name,status:b.status}}))}
   if(!map.getSource('vessels')){map.addSource('vessels',{type:'geojson',data:vesselData});map.addLayer({id:'vessels',type:'circle',source:'vessels',paint:{'circle-radius':7,'circle-color':'#69d4ff','circle-stroke-width':2,'circle-stroke-color':'#dff7ff'}});map.addLayer({id:'vessel-labels',type:'symbol',source:'vessels',layout:{'text-field':['get','name'],'text-offset':[0,1.35],'text-size':11},paint:{'text-color':'#eaf7ff','text-halo-color':'#07111d','text-halo-width':1.2}})}else{(map.getSource('vessels') as maplibregl.GeoJSONSource).setData(vesselData)}
   if(!map.getSource('berths')){map.addSource('berths',{type:'geojson',data:berthData});map.addLayer({id:'berths',type:'circle',source:'berths',paint:{'circle-radius':5,'circle-color':'#f8b65b','circle-stroke-width':1.5,'circle-stroke-color':'#ffe0a8'}})}else{(map.getSource('berths') as maplibregl.GeoJSONSource).setData(berthData)}}
  if(map.isStyleLoaded())sync();else map.once('load',sync)},[state])
 return <div className="harbor-map" ref={node}/>
}
