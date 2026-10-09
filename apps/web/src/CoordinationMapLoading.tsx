import {recordName, type Fact} from './productClient'

type Props={facts:Fact[];focusedCallId:string}

// A semantic preview, never a geographic representation. This renders before
// the large WebGL map bundle or the remote basemap can finish loading.
export function CoordinationMapLoading({facts,focusedCallId}:Props){
  const berths=facts.filter(item=>item.kind==='berth')
  const calls=facts.filter(item=>item.kind==='call'&&!['departed','cancelled'].includes(String(item.payload.status)))
  const vessels=facts.filter(item=>item.kind==='vessel')
  const unmapped=berths.filter(item=>typeof item.payload.latitude!=='number'||typeof item.payload.longitude!=='number').length
  return <div className="coord-map-preview" role="status" aria-label="Harbor map loading preview">
    <div className="coord-map-preview-head"><span className="product-index">SCHEMATIC · NOT GEOGRAPHIC</span><b>Preparing harbor basemap</b><small>Recorded berth/call links remain visible while map tiles load.</small></div>
    <div className="coord-map-preview-list">{berths.length?berths.slice(0,5).map(berth=>{
      const linked=calls.filter(call=>call.payload.berth_id===berth.record_id)
      return <div className="coord-map-preview-row" key={berth.record_id}>
        <div><span className="product-index">BERTH</span><b>{recordName(berth)}</b></div>
        <div className="coord-map-preview-vessels">{linked.length?linked.map(call=>{
          const vessel=vessels.find(item=>item.record_id===call.payload.vessel_id)
          return <span className={call.record_id===focusedCallId?'is-focused':''} key={call.record_id}>{vessel?recordName(vessel):call.record_id}<small>{String(call.payload.status)}</small></span>
        }):<em>No active call recorded</em>}</div>
      </div>
    }):<div className="coord-map-preview-empty">No berths recorded. Add verified geography to display port positions.</div>}</div>
    <div className="coord-map-preview-foot"><span>{calls.length} active recorded call{calls.length===1?'':'s'}</span><span>{unmapped} berth{unmapped===1?'':'s'} without coordinates</span></div>
  </div>
}
