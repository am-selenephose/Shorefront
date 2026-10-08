import {useEffect,useState} from 'react'
import {dateLabel,productRequest,recordName,type Fact} from './productClient'

type NoaaResult = {
  status:'current'|'stale'|'unavailable'|'disabled'|'not_configured';
  provider:string;station_id:string|null;port_id:string;
  source_url?:string;retrieved_at?:string;scope:string;
  physical_execution_authorized:false;
  observation:{level_m:number;observed_at:string;datum:string;units:string;quality:string}|null;
  limitations:string[];
}

export default function ProductNoaaWaterLevel({ports}:{ports:Fact[]}) {
  const configured=ports.filter(port=>typeof port.payload.noaa_station_id==='string'&&port.payload.noaa_station_id.length===7)
  const [portId,setPortId]=useState('')
  const [nonce,setNonce]=useState(0)
  const [loading,setLoading]=useState(false)
  const [error,setError]=useState('')
  const [result,setResult]=useState<NoaaResult|null>(null)
  const selected=configured.find(port=>port.record_id===portId)??configured[0]??null
  useEffect(()=>{
    if(!selected){setResult(null);setError('');return}
    let active=true
    setLoading(true)
    setError('')
    setResult(null)
    productRequest<NoaaResult>('/environment/noaa?port_id='+encodeURIComponent(selected.record_id))
      .then(next=>{
        if(!active)return
        if(next.physical_execution_authorized!==false || next.port_id!==selected.record_id){
          throw new Error('External context did not match the recorded port.')
        }
        setResult(next)
      })
      .catch(err=>{if(active)setError(err instanceof Error?err.message:'NOAA observation unavailable')})
      .finally(()=>{if(active)setLoading(false)})
    return()=>{active=false}
  },[selected?.record_id,selected?.payload.noaa_station_id,nonce])

  return <section className="ops-panel noaa-context-panel" aria-label="External NOAA water level context">
    <header>
      <div><span className="product-index">EXTERNAL / OPERATOR-SELECTED STATION</span>
        <h2>NOAA water-level observations</h2>
      </div>
      <span className="noaa-source-pill">US CO-OPS / READ ONLY</span>
    </header>
    <div className="noaa-context-body">
      <p>Optional real station observation for situational context, not vessel clearance, weather forecast, berth approval or a water-depth calculation.</p>
      {!configured.length?<div className="ops-empty small"><b>No NOAA station configured.</b>
        <p>For eligible U.S. ports, edit the Port record and enter its verified 7-digit NOAA CO-OPS station ID. External access is disabled until an administrator explicitly enables it on the server.</p>
        </div>:<>
        <div className="noaa-controls">
          <label>Recorded port station
            <select value={selected?.record_id??''} onChange={event=>setPortId(event.target.value)}>
              {configured.map(port=><option value={port.record_id} key={port.record_id}>
                {recordName(port)} / {port.payload.noaa_station_id}
              </option>)}
            </select>
          </label>
          <button type="button" disabled={loading} onClick={()=>setNonce(value=>value+1)}>{loading?'Checking source...':'Refresh observation'}</button>
        </div>
        {error?<div className="product-boundary" role="alert">{error}. No external observation accepted.</div>
        :loading?<p role="status">Checking recorded NOAA station availability...</p>
        :result?<div className="noaa-observation" role="status">
          <div className="noaa-observation-top"><b className={'noaa-observation-status is-'+result.status}>{result.status.replaceAll('_',' ').toUpperCase()}</b><span>Station {result.station_id??'not configured'}</span></div>
          {result.observation?<div className="noaa-reading">
            <strong>{result.observation.level_m.toFixed(3)} m</strong>
            <div><span>Datum {result.observation.datum} / {result.observation.quality}</span>
              <small>Observed {dateLabel(result.observation.observed_at)}</small>
            </div>
          </div>:<p>No usable water-level observation is available. No measurement was inferred.</p>}
          {result.source_url&&<p><a href={result.source_url} target="_blank" rel="noreferrer">NOAA CO-OPS Data API documentation and source</a></p>}
          <ul>{(result.limitations??[]).map(item=><li key={item}>{item}</li>)}</ul>
          <small>PORT ASSOCIATION IS OPERATOR-CONFIGURED / PHYSICAL EXECUTION LOCKED</small>
        </div>:null}
      </>}
    </div>
  </section>
}
