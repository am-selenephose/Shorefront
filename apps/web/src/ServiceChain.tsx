import type { HarborState, PortCall, ServiceStep } from './types'

const labels: Record<string, string> = {
  pilot: 'PILOT',
  tug: 'TUG',
  berth: 'BERTH',
  crane: 'CRANE',
  cargo: 'CARGO',
  bunker: 'BUNKER',
  stores: 'STORES',
  documents: 'DOCS',
  customs: 'CUSTOMS',
  gate: 'GATE',
  departure: 'DEPART',
}

function dependencyColumns(steps: ServiceStep[]) {
  const byId = new Map(steps.map(step => [step.id, step]))
  const memo = new Map<string, number>()
  const visiting = new Set<string>()

  function depth(step: ServiceStep): number {
    const cached = memo.get(step.id)
    if (cached !== undefined) return cached
    if (visiting.has(step.id)) return 0

    visiting.add(step.id)
    const dependencies = step.dependency_step_ids
      .map(id => byId.get(id))
      .filter((item): item is ServiceStep => Boolean(item))
    const value = dependencies.length === 0
      ? 0
      : Math.max(...dependencies.map(depth)) + 1
    visiting.delete(step.id)
    memo.set(step.id, value)
    return value
  }

  const columns = new Map<number, ServiceStep[]>()
  for (const step of steps) {
    const level = depth(step)
    const column = columns.get(level) || []
    column.push(step)
    columns.set(level, column)
  }

  return [...columns.entries()]
    .sort(([left], [right]) => left - right)
    .map(([level, column]) => ({
      level,
      steps: column.sort(
        (left, right) =>
          new Date(left.planned_at).getTime() - new Date(right.planned_at).getTime(),
      ),
    }))
}

export function ServiceChain({ call, state }: { call: PortCall; state: HarborState }) {
  const steps = state.service_steps.filter(step => step.port_call_id === call.id)
  if (!steps.length) return null

  const byId = new Map(steps.map(step => [step.id, step]))
  const columns = dependencyColumns(steps)

  return (
    <div className="service-dag" data-service-dag={call.id}>
      {columns.map(column => (
        <div className="service-dag-column" data-depth={column.level} key={column.level}>
          <span className="service-dag-depth">STAGE {column.level + 1}</span>
          {column.steps.map(step => {
            const resource = state.service_resources.find(item => item.id === step.resource_id)
            const upstream = step.dependency_step_ids
              .map(id => byId.get(id))
              .filter((item): item is ServiceStep => Boolean(item))
              .map(item => labels[item.kind] || item.kind.toUpperCase())

            return (
              <div
                className={'service-dag-node ' + step.state}
                data-service-kind={step.kind}
                key={step.id}
              >
                <div className="service-dag-node-head">
                  <i />
                  <b>{labels[step.kind] || step.kind.toUpperCase()}</b>
                </div>
                <small>{resource?.name || 'system'}</small>
                {upstream.length > 0 && <em>FROM {upstream.join(' + ')}</em>}
              </div>
            )
          })}
        </div>
      ))}
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
