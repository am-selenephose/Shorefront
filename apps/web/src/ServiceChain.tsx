import type { HarborState, PortCall, ServiceStep } from './types'

const labels: Record<string, string> = {
  pilot: 'PILOT',
  tug: 'TUG',
  berth: 'BERTH',
  crane: 'CRANE',
  cargo: 'CARGO',
  customs: 'CUSTOMS',
  departure: 'DEPART',
}

export function ServiceChain({ call, state }: { call: PortCall; state: HarborState }) {
  const steps = state.service_steps
    .filter(step => step.port_call_id === call.id)
    .sort((a, b) => new Date(a.planned_at).getTime() - new Date(b.planned_at).getTime())

  if (!steps.length) return null

  return (
    <div className="service-chain">
      {steps.map((step: ServiceStep, index) => {
        const resource = state.service_resources.find(item => item.id === step.resource_id)
        return (
          <div className={'service-node ' + step.state} key={step.id}>
            <div className="service-line">
              <i />
              {index < steps.length - 1 && <span />}
            </div>
            <b>{labels[step.kind] || step.kind.toUpperCase()}</b>
            <small>{resource?.name || 'system'}</small>
          </div>
        )
      })}
    </div>
  )
}

export function ResourceBoard({ state }: { state: HarborState }) {
  return (
    <div className="resource-board">
      {state.service_resources.map(resource => (
        <div className="resource-row" key={resource.id}>
          <div>
            <b>{resource.name}</b>
            <span>
              {resource.kind} · cap {resource.capacity}
              {resource.available_from
                ? ' · free ' + new Intl.DateTimeFormat('en', {
                    hour: '2-digit',
                    minute: '2-digit',
                    hour12: false,
                  }).format(new Date(resource.available_from))
                : ''}
            </span>
          </div>
          <span className={'resource-status ' + resource.status}>{resource.status}</span>
        </div>
      ))}
    </div>
  )
}
