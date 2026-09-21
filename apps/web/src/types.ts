export type Risk = 'low' | 'medium' | 'high' | 'critical'
export type LinkMode = 'full' | 'degraded' | 'critical' | 'offline_edge'
export type IncidentType = 'pilot_delay' | 'tug_unavailable' | 'berth_overrun' | 'wind_restriction' | 'connectivity_loss'
export type ServiceKind = 'pilot' | 'tug' | 'berth' | 'crane' | 'cargo' | 'customs' | 'departure'
export type ServiceState = 'ready' | 'assigned' | 'delayed' | 'blocked' | 'completed'
export type ResourceStatus = 'available' | 'assigned' | 'delayed' | 'unavailable'
export type RecoveryActionType = 'reassign_resource' | 'move_berth' | 'shift_window'
export type OperatorRole = 'viewer' | 'operator' | 'supervisor'



export interface ScenarioAction {
  action_type: 'incident' | 'connectivity'
  incident_type?: IncidentType | null
  link_mode?: LinkMode | null
  target_port_call_id?: string | null
  impact_minutes?: number | null
}

export interface ScenarioFixture {
  id: string
  title: string
  description: string
  actions: ScenarioAction[]
}

export interface OperatorIdentity {
  operator_id: string
  display_name: string
  role: OperatorRole
}

export interface Coordinate { lat: number; lon: number }

export interface Vessel {
  id: string
  name: string
  imo: string
  vessel_type: string
  status: string
  position: Coordinate
  speed_knots: number
  heading_deg: number
  eta?: string | null
  assigned_berth_id?: string | null
  cargo_summary?: string | null
}

export interface Berth {
  id: string
  name: string
  terminal: string
  status: string
  max_length_m: number
  position: Coordinate
  vessel_id?: string | null
}

export interface Stage {
  code: string
  label: string
  planned_at: string
  actual_at?: string | null
  state: string
  dependency_codes: string[]
}

export interface PortCall {
  id: string
  vessel_id: string
  berth_id: string
  arrival_eta: string
  departure_eta: string
  stages: Stage[]
  delay_minutes: number
  risk: Risk
  estimated_cost_exposure_usd: number
}

export interface Incident {
  id: string
  incident_type: IncidentType
  status: 'active' | 'resolved'
  severity: Risk
  title: string
  started_at: string
  target_port_call_id?: string | null
  target_berth_id?: string | null
  impact_minutes: number
  details: string
  resolved_at?: string | null
}

export interface Event {
  id: string
  occurred_at: string
  category: string
  severity: Risk
  title: string
  message: string
  vessel_id?: string | null
  berth_id?: string | null
  port_call_id?: string | null
  incident_id?: string | null
}

export interface ServiceResource {
  id: string
  kind: ServiceKind
  name: string
  status: ResourceStatus
  capacity: number
  assigned_port_call_ids: string[]
  available_from?: string | null
}

export interface ServiceStep {
  id: string
  port_call_id: string
  kind: ServiceKind
  label: string
  planned_at: string
  state: ServiceState
  resource_id?: string | null
  dependency_step_ids: string[]
}

export interface HarborState {
  generated_at: string
  port_name: string
  center: Coordinate
  vessels: Vessel[]
  berths: Berth[]
  port_calls: PortCall[]
  weather: {
    observed_at: string
    wind_knots: number
    gust_knots: number
    visibility_km: number
    wave_height_m: number
    tide_m: number
    restriction_active: boolean
    restriction_reason?: string | null
  }
  connectivity: {
    mode: LinkMode
    primary_link: string
    fallback_link?: string | null
    bandwidth_kbps: number
    queued_events: number
    last_transition_at: string
  }
  incidents: Incident[]
  service_resources: ServiceResource[]
  service_steps: ServiceStep[]
  events: Event[]
  metrics: Record<string, number>
  data_disclaimer: string
}


export interface RecoveryAction {
  action_type: 'reassign_resource' | 'move_berth' | 'shift_window'
  port_call_id: string
  service_kind?: ServiceKind | null
  from_resource_id?: string | null
  to_resource_id?: string | null
  from_berth_id?: string | null
  to_berth_id?: string | null
  shift_minutes: number
}

export interface RecoveryProposal {
  id: string
  state_fingerprint: string
  title: string
  target_port_call_id: string
  incident_id?: string | null
  actions: RecoveryAction[]
  projected_total_delay_minutes: number
  projected_modeled_cost_usd: number
  projected_berth_conflicts: number
  projected_blocked_services: number
  projected_risk: Risk
  disruption_score: number
  rationale: string[]
  assumptions: string[]
  requires_approval: boolean
}


export interface RecoveryReceipt {
  proposal_id: string
  state_fingerprint: string
  applied_at: string
  target_port_call_id: string
  actions: RecoveryAction[]
  resulting_berth_conflicts: number
  resulting_blocked_services: number
  resulting_total_delay_minutes: number
  resulting_modeled_cost_usd: number
  approved_by: string
  approved_role: OperatorRole
  approved_display_name?: string | null
}
