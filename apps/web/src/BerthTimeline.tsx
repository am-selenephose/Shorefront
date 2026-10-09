import type { HarborState, PortCall } from './types'

const HOUR = 60 * 60 * 1000

function overlaps(a: PortCall, b: PortCall) {
  return a.berth_id === b.berth_id &&
    new Date(a.arrival_eta).getTime() < new Date(b.departure_eta).getTime() &&
    new Date(b.arrival_eta).getTime() < new Date(a.departure_eta).getTime()
}

function timeLabel(value: number) {
  return new Intl.DateTimeFormat('en', { hour: '2-digit', minute: '2-digit', hour12: false })
    .format(new Date(value))
}

export function BerthTimeline({ state }: { state: HarborState }) {
  const arrivals = state.port_calls.map(call => new Date(call.arrival_eta).getTime())
  const earliest = Math.min(...arrivals, new Date(state.generated_at).getTime())
  const horizonStart = Math.floor((earliest - 30 * 60 * 1000) / HOUR) * HOUR
  const horizonEnd = horizonStart + 16 * HOUR
  const horizon = horizonEnd - horizonStart

  const ticks = Array.from({ length: 9 }, (_, index) => horizonStart + index * 2 * HOUR)
  const callsByBerth = new Map<string, PortCall[]>()
  for (const call of state.port_calls) {
    const existing = callsByBerth.get(call.berth_id) || []
    existing.push(call)
    callsByBerth.set(call.berth_id, existing)
  }

  return (
    <div className="gantt">
      <div className="gantt-axis">
        <div className="gantt-berth-label">BERTH</div>
        <div className="gantt-axis-track">
          {ticks.map(tick => {
            const left = ((tick - horizonStart) / horizon) * 100
            return <div className="gantt-tick" key={tick} style={{ left: String(left) + '%' }}>
              <span>{timeLabel(tick)}</span>
            </div>
          })}
        </div>
      </div>

      {state.berths.map(berth => {
        const calls = (callsByBerth.get(berth.id) || []).sort(
          (a, b) => new Date(a.arrival_eta).getTime() - new Date(b.arrival_eta).getTime()
        )
        return (
          <div className="gantt-row" key={berth.id}>
            <div className="gantt-berth-label">
              <b>{berth.name}</b>
              <span>{berth.terminal}</span>
            </div>
            <div className="gantt-track">
              {ticks.map(tick => {
                const left = ((tick - horizonStart) / horizon) * 100
                return <i className="gantt-gridline" key={tick} style={{ left: String(left) + '%' }} />
              })}
              {calls.map((call, index) => {
                const rawStart = new Date(call.arrival_eta).getTime()
                const rawEnd = new Date(call.departure_eta).getTime()
                const start = Math.max(rawStart, horizonStart)
                const end = Math.min(rawEnd, horizonEnd)
                if (end <= horizonStart || start >= horizonEnd) return null

                const left = ((start - horizonStart) / horizon) * 100
                const width = Math.max(((end - start) / horizon) * 100, 2)
                const vessel = state.vessels.find(v => v.id === call.vessel_id)
                const conflict = state.port_calls.some(other => other.id !== call.id && overlaps(call, other))

                return (
                  <div
                    key={call.id}
                    className={'gantt-call ' + call.risk + (conflict ? ' conflict' : '')}
                    style={{
                      left: String(left) + '%',
                      width: String(width) + '%',
                      top: String(8 + (index % 2) * 42) + 'px',
                    }}
                    title={(vessel?.name || call.id) + ' · ' + call.delay_minutes + ' min delay'}
                  >
                    <span>{vessel?.name || call.id}</span>
                    <small>{timeLabel(rawStart)} → {timeLabel(rawEnd)}</small>
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}
