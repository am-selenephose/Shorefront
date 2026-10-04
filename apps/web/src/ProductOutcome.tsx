import {useRef, useState, type FormEvent} from 'react'
import {dateLabel, productRequest, type Fact} from './productClient'

export default function ProductOutcome({decisionId, expected, existing, writable, onRefresh}: {decisionId:string; expected:{eta:string; etd:string}; existing:Fact|undefined; writable:boolean; onRefresh:()=>Promise<void>}) {
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const id = useRef(existing?.record_id ?? crypto.randomUUID())
  const attempt = useRef<{intent:string; key:string}|null>(null)
  async function save(event:FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!writable || busy) return
    setBusy(true); setError('')
    try {
      const data = new FormData(event.currentTarget)
      const command = {record_id:existing?.record_id ?? id.current, expected_revision:existing?.revision ?? 0, source:String(data.get('source')),
        payload:{decision_id:decisionId, actual_arrival:new Date(String(data.get('actual_arrival'))).toISOString(), actual_departure:new Date(String(data.get('actual_departure'))).toISOString(), note:String(data.get('note'))}}
      const intent = JSON.stringify(command)
      if (attempt.current?.intent !== intent) attempt.current = {intent,key:crypto.randomUUID()}
      await productRequest('/records/outcome', command, attempt.current.key)
      await onRefresh(); setEditing(false)
    } catch (failure) {setError(failure instanceof Error ? failure.message : 'Could not record the outcome.')}
    finally {setBusy(false)}
  }
  function local(value:unknown) {if (!value) return ''; const d=new Date(String(value)); return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16)}
  const arrival = existing ? new Date(String(existing.payload.actual_arrival)).getTime() : 0
  const departure = existing ? new Date(String(existing.payload.actual_departure)).getTime() : 0
  const plannedArrival = new Date(expected.eta).getTime(), plannedDeparture = new Date(expected.etd).getTime()
  const minutes = (ms:number) => Number((ms/60000).toFixed(2))
  return <section className="product-outcome"><h3>Observed outcome</h3><p>Record actual times from a named source. Deviations compare those observations with the approved plan; they do not measure causal savings or train a predictive model.</p>
    {existing && <div className="product-boundary"><p>Arrival {dateLabel(String(existing.payload.actual_arrival))} · departure {dateLabel(String(existing.payload.actual_departure))}</p><p>Arrival deviation: {minutes(arrival-plannedArrival)} minutes</p><p>Occupancy deviation: {minutes((departure-arrival)-(plannedDeparture-plannedArrival))} minutes</p><p>{existing.source}</p>{existing.payload.note && <p>{String(existing.payload.note)}</p>}<button disabled={!writable || busy} onClick={() => setEditing(!editing)}>{editing ? 'Cancel correction' : 'Correct outcome'}</button></div>}
    {(!existing || editing) && <form onSubmit={save} aria-busy={busy} key={existing?.revision ?? 0}><fieldset disabled={!writable || busy}><div className="product-form-grid">
      <label>Actual arrival (your local time)<input name="actual_arrival" type="datetime-local" required defaultValue={local(existing?.payload.actual_arrival)}/></label>
      <label>Actual departure (your local time)<input name="actual_departure" type="datetime-local" required defaultValue={local(existing?.payload.actual_departure)}/></label>
      <label>Observation source<input name="source" required maxLength={500} defaultValue={existing?.source ?? ''}/></label>
      <label>Observation note<input name="note" maxLength={2000} defaultValue={String(existing?.payload.note ?? '')}/></label>
    </div><button className="product-primary">{busy ? 'Recording outcome…' : existing ? 'Save outcome correction' : 'Record observed outcome'}</button></fieldset></form>}
    {error && <p role="alert" className="product-error">{error}</p>}
  </section>
}
