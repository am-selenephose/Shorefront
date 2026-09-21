export type Risk = 'low' | 'medium' | 'high' | 'critical'
export type LinkMode = 'full' | 'degraded' | 'critical' | 'offline_edge'
export type IncidentType = 'pilot_delay' | 'tug_unavailable' | 'berth_overrun' | 'wind_restriction' | 'connectivity_loss'

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
  events: Event[]
  metrics: Record<string, number>
  data_disclaimer: string
}
