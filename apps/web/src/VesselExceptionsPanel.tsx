import type {
  OperatorIdentity,
  VesselOperationalException,
} from './types'

const shortRef = (value: string) =>
  value.length <= 24
    ? value
    : value.slice(0, 18) + '…' + value.slice(-5)

export function VesselExceptionsPanel({
  exceptions,
  identity,
  busy,
  onRefresh,
}: {
  exceptions: VesselOperationalException[]
  identity: OperatorIdentity | null
  busy: boolean
  onRefresh: () => Promise<void>
}) {
  const activeCount = exceptions.filter(
    item => item.state !== 'resolved',
  ).length

  return (
    <div className="vessel-exceptions-panel">
      <div className="vessel-exceptions-head">
        <div>
          <span>VESSEL EXCEPTIONS</span>
          <b>Privacy-minimized operational state</b>
        </div>
        <div className="vessel-exceptions-actions">
          {identity ? (
            <small>{activeCount} ACTIVE · {exceptions.length} SHOWN</small>
          ) : (
            <small>OPERATOR SESSION REQUIRED</small>
          )}
          <button
            disabled={!identity || busy}
            onClick={() => void onRefresh()}
          >
            Refresh
          </button>
        </div>
      </div>

      {!identity ? (
        <div className="vessel-exceptions-empty">
          <b>Authenticate in Recovery Plans to inspect vessel exceptions.</b>
          <span>
            Machine integration credentials cannot read this human view.
          </span>
        </div>
      ) : exceptions.length === 0 ? (
        <div className="vessel-exceptions-empty">
          <b>No vessel operational exceptions are visible.</b>
          <span>
            Only validated privacy-minimized exception lifecycles appear here.
          </span>
        </div>
      ) : (
        <div className="vessel-exception-list">
          {exceptions.map(item => (
            <article
              className={'vessel-exception ' + item.state}
              key={item.exception_ref}
            >
              <div className="vessel-exception-main">
                <div className="vessel-exception-title">
                  <span className={'risk ' + item.risk}>
                    {item.risk.toUpperCase()}
                  </span>
                  <span className={'vessel-exception-status ' + item.state}>
                    {item.state.replace('_', ' ').toUpperCase()}
                  </span>
                  <b>{item.title}</b>
                </div>
                <p>{item.summary}</p>
                <div className="vessel-exception-meta">
                  <span>{item.vessel_id}</span>
                  <span>{item.port_call_id || 'NO PORT CALL'}</span>
                  <span>
                    SEQ {item.first_source_sequence} -&gt; {item.latest_source_sequence}
                  </span>
                  <span>{new Date(item.updated_at).toLocaleString()}</span>
                </div>
                <div
                  className="vessel-exception-history"
                  data-exception-history={item.exception_ref}
                  aria-label="Exception lifecycle"
                >
                  {item.history.map((entry, index) => (
                    <span
                      className={'vessel-exception-history-state ' + entry.state}
                      key={entry.source_sequence + ':' + entry.state}
                      title={new Date(entry.occurred_at).toLocaleString()}
                    >
                      <b data-exception-state={entry.state}>
                        {entry.state.replace('_', ' ').toUpperCase()}
                      </b>
                      <small>#{entry.source_sequence}</small>
                      {index < item.history.length - 1 && <i aria-hidden="true">→</i>}
                    </span>
                  ))}
                </div>
              </div>

              <div className="vessel-exception-proof">
                <span>VESSEL-SAFE REFERENCE</span>
                <b>{shortRef(item.exception_ref)}</b>
                <small>{item.lifecycle_event_count} LIFECYCLE EVENTS</small>
                <small>PRIVACY MINIMIZED · ADVISORY · NO ACTUATION</small>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  )
}
