import type { HarborState, RecoveryProposal, RecoveryReceipt } from './types'

// Validate transport structure before committing it to render state. These are
// presentation-safety checks, not replacements for Python's domain validation.
type Check = (value: unknown) => boolean
const text: Check = value => typeof value === 'string'
const number: Check = value => typeof value === 'number' && Number.isFinite(value)
const boolean: Check = value => typeof value === 'boolean'
const date: Check = value => typeof value === 'string' && Number.isFinite(Date.parse(value))
const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value)
const shape = (fields: Record<string, Check>): Check => value => record(value) && Object.entries(fields).every(([key, check]) => check(value[key]))
const list = (check: Check): Check => value => Array.isArray(value) && value.every(check)
const optional = (check: Check): Check => value => value == null || check(value)
const oneOf = (...values: string[]): Check => value => typeof value === 'string' && values.includes(value)
const strings = list(text)
const risk = oneOf('low', 'medium', 'high', 'critical')
const coordinate = shape({ lat: number, lon: number })
const source = shape({
  source_id: text, domain: text, mode: text, provider: text, health: text,
  observed_at: date, received_at: date, freshness_seconds: number,
  stale_after_seconds: number, stale: boolean, record_count: number,
  detail: optional(text), last_success_at: optional(date), last_attempt_at: optional(date),
  next_retry_at: optional(date), retry_delay_seconds: number, consecutive_errors: number, using_cached_records: boolean,
})
const call = shape({
  id: text, source_id: text, vessel_id: text, berth_id: text,
  arrival_eta: date, departure_eta: date, delay_minutes: number, risk, estimated_cost_exposure_usd: number,
  stages: list(shape({ code: text, label: text, planned_at: date, actual_at: optional(date), state: text, dependency_codes: strings })),
})
const harbor = shape({
  generated_at: date, decision_revision: text, port_name: text, center: coordinate, data_disclaimer: text,
  vessels: list(shape({ id: text, source_id: text, name: text, imo: text, vessel_type: text, status: text, position: coordinate,
    speed_knots: number, heading_deg: number, eta: optional(date), assigned_berth_id: optional(text), cargo_summary: optional(text) })),
  berths: list(shape({ id: text, source_id: text, name: text, terminal: text, status: text, max_length_m: number, position: coordinate, vessel_id: optional(text) })),
  port_calls: list(call),
  incidents: list(shape({ id: text, incident_type: text, status: text, severity: risk, title: text, started_at: date, impact_minutes: number, details: text,
    target_port_call_id: optional(text), target_berth_id: optional(text), target_resource_id: optional(text), resolved_at: optional(date) })),
  service_steps: list(shape({ id: text, port_call_id: text, kind: text, label: text, planned_at: date, duration_minutes: number, state: text,
    resource_id: optional(text), dependency_step_ids: strings })),
  service_resources: list(shape({ id: text, kind: text, name: text, status: text, capacity: number, assigned_port_call_ids: strings,
    available_from: optional(date), unavailable_windows: list(shape({ start_at: date, end_at: date, reason: text })) })),
  service_duration_calibrations: list(shape({ service_kind: text, duration_minutes: number, source_id: text, mode: text, provider: text, observed_at: date, detail: optional(text) })),
  events: list(shape({ id: text, occurred_at: date, category: text, severity: risk, title: text, message: text })),
  data_sources: list(source),
  weather: shape({ source_id: text, observed_at: date, wind_knots: number, gust_knots: number, visibility_km: number,
    wave_height_m: number, tide_m: number, restriction_active: boolean, restriction_reason: optional(text) }),
  connectivity: shape({ mode: text, primary_link: text, fallback_link: optional(text), bandwidth_kbps: number, queued_events: number, last_transition_at: date }),
  metrics: value => record(value) && Object.values(value).every(number) &&
    ['vessels_in_port_picture', 'berths_occupied', 'berths_total', 'port_calls_at_risk', 'average_delay_minutes', 'active_incidents',
      'berth_conflicts', 'blocked_services', 'delayed_services', 'queued_events', 'stale_data_sources'].every(key => number(value[key])),
})
const action = shape({ action_type: text, port_call_id: text, shift_minutes: number, service_kind: optional(text),
  from_resource_id: optional(text), to_resource_id: optional(text), from_berth_id: optional(text), to_berth_id: optional(text) })
const proposal = shape({
  id: text, state_fingerprint: text, title: text, target_port_call_id: text, incident_id: optional(text), incident_ids: strings,
  actions: list(action), projected_total_delay_minutes: number, projected_modeled_cost_usd: number,
  projected_berth_conflicts: number, projected_blocked_services: number, projected_risk: risk,
  disruption_score: number, decision_confidence: text, data_quality_warnings: strings, rationale: strings, assumptions: strings, requires_approval: boolean,
})

export function isHarborSnapshot(value: unknown): value is HarborState { return harbor(value) }
export function isRecoveryProposal(value: unknown): value is RecoveryProposal { return proposal(value) }

export type Comparison = {
  current: HarborState
  options: { proposal: RecoveryProposal; harbor: HarborState }[]
  model_notice: string
}
export function isComparison(value: unknown): value is Comparison {
  return shape({ read_only: flag => flag === true, current: harbor, options: list(shape({ proposal, harbor })), model_notice: text })(value)
}
export type Story = {
  baseline: HarborState
  disrupted: HarborState
  recovered: HarborState
  comparison: Comparison
  receipt: RecoveryReceipt
}
export function isStory(value: unknown): value is Story {
  if (!shape({
    synthetic: flag => flag === true, writes_operational_state: flag => flag === false, receipt_is_simulated: flag => flag === true,
    baseline: harbor, disrupted: harbor, recovered: harbor, comparison: isComparison,
    receipt: shape({ proposal_id: text, state_fingerprint: text, approved_by: text, resulting_total_delay_minutes: number }),
  })(value)) return false
  const story = value as Story
  return [story.baseline, story.disrupted, story.recovered].every(state => state.port_calls.some(item => item.id === 'pc-aurora'))
}
