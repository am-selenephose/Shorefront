import type {
  AdapterSnapshot,
  DataSourceProvenance,
  OperatorIdentity,
} from './types'

function ageLabel(seconds: number) {
  if (seconds < 60) return seconds + 's'
  if (seconds < 3600) return Math.floor(seconds / 60) + 'm'
  return Math.floor(seconds / 3600) + 'h'
}

function domainLabel(domain: string) {
  if (domain === 'weather_tide') return 'WEATHER / TIDE'
  if (domain === 'berth_plan') return 'BERTH PLAN'
  return domain.toUpperCase()
}

function SourceCard({ source }: { source: DataSourceProvenance }) {
  return (
    <div className="source-card" data-source-id={source.source_id}>
      <div className="source-card-head">
        <div>
          <span>{domainLabel(source.domain)}</span>
          <b>{source.provider}</b>
        </div>
        <div className={'source-mode ' + source.mode}>{source.mode}</div>
      </div>
      <div className="source-meta">
        <span>{source.record_count} records</span>
        <span>{ageLabel(source.freshness_seconds)} old</span>
        <span className={'adapter-health ' + source.health}>{source.health}</span>
      </div>
      <small>{source.source_id}</small>
    </div>
  )
}

export function DataSourcesPanel({
  current,
  adapters,
  identity,
  busy,
  onIngest,
}: {
  current: DataSourceProvenance[]
  adapters: AdapterSnapshot[]
  identity: OperatorIdentity | null
  busy: boolean
  onIngest: (adapterId: string) => Promise<void>
}) {
  const canIngest = identity?.role === 'operator' || identity?.role === 'supervisor'
  const liveConfigured = adapters.some(adapter => adapter.provenance.mode === 'live')

  return (
    <div className="data-sources-panel">
      <div className="panel-title">
        <div>
          <span>DATA FEEDS</span>
          <b>Provenance, freshness, and adapter health</b>
        </div>
        <small>{liveConfigured ? 'LIVE ADAPTER CONFIGURED' : 'NO LIVE FEEDS CONFIGURED'}</small>
      </div>

      <div className="current-sources">
        <span className="section-kicker">CURRENT HARBOR SOURCES</span>
        <div className="source-grid">
          {current.map(source => <SourceCard source={source} key={source.source_id} />)}
        </div>
      </div>

      <div className="available-adapters">
        <span className="section-kicker">AVAILABLE ADAPTERS</span>
        <div className="adapter-list">
          {adapters.map(adapter => {
            const p = adapter.provenance
            const disabled = busy || !canIngest || p.stale || p.health !== 'healthy'
            return (
              <div className="adapter-row" data-adapter-id={adapter.adapter_id} key={adapter.adapter_id}>
                <div>
                  <b>{domainLabel(p.domain)} · {p.provider}</b>
                  <span>
                    {p.record_count} records · freshness {ageLabel(p.freshness_seconds)}
                    {' · '}stale after {ageLabel(p.stale_after_seconds)}
                  </span>
                  {(p.using_cached_records || p.consecutive_errors > 0) && (
                    <span className="adapter-resilience">
                      {p.using_cached_records ? 'LAST-KNOWN-GOOD CACHE' : 'LIVE FETCH FAILURE'}
                      {' · '}{p.consecutive_errors} consecutive error{p.consecutive_errors === 1 ? '' : 's'}
                    </span>
                  )}
                  <small>{p.detail}</small>
                </div>
                <div className="adapter-row-actions">
                  <span className={'adapter-health ' + p.health}>{p.health}</span>
                  <button
                    disabled={disabled}
                    onClick={() => onIngest(adapter.adapter_id)}
                  >
                    {p.using_cached_records
                      ? 'Cached preview'
                      : p.stale
                        ? 'Stale blocked'
                        : p.health === 'error'
                          ? 'Feed unavailable'
                          : !identity
                            ? 'Authenticate'
                            : canIngest
                              ? p.mode === 'live' ? 'Ingest live' : 'Ingest fixture'
                              : 'View only'}
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
