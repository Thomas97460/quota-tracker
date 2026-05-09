export type ProviderId = "gemini" | "codex" | "copilot" | "claude"

export interface ProviderConfig {
  home_path: string
  // Deprecated — optional so older server shapes still parse
  active_probe_enabled?: boolean
  passive_sync_enabled?: boolean
  high_water_marks: Record<string, unknown>
  safe_options: Record<string, unknown>
}

export interface ProviderSummary {
  id: ProviderId
  enabled: boolean
  config: ProviderConfig
  updated_at: string
}

export interface QuotaRow {
  id: string
  provider_id: ProviderId
  quota_name: string
  source: string
  timestamp: string
  used_percent: number | null
  remaining_percent: number | null
  window_minutes: number | null
  resets_at: string | null
}

export interface SessionRow {
  id: string
  provider_id: ProviderId
  external_session_id: string
  model_name: string
  project_path: string | null
  project_name: string | null
  created_at: string
  last_seen_at: string
}

/** Returned by /api/token-usage — bucket depends on group_by param */
export interface UsageRow {
  bucket: string
  /** Client-side only: present when the UI merges per-provider responses. */
  provider_id?: ProviderId
  input_tokens: number
  output_tokens: number
  cached_tokens: number
  reasoning_tokens: number
  thoughts_tokens: number
  tool_tokens: number
  total_tokens: number
}

export interface ProjectUsageRow {
  project_path: string | null
  project_name: string | null
  total_tokens: number
  session_count: number
}

export interface ProjectUsageResponse {
  items: ProjectUsageRow[]
  total: number
}

export interface DaemonConfig {
  sync_interval_minutes: number
  // Deprecated — kept for back-compat with older server responses
  active_probe_interval_minutes?: number
  passive_sync_interval_minutes?: number
  web_host: string
  web_port: number
  database_path: string
  log_level: string
}

export interface ConfigShape {
  daemon: DaemonConfig
  gemini:  { enabled: boolean; home_path: string; active_probe_enabled?: boolean; passive_sync_enabled?: boolean; safe_options: Record<string, unknown> }
  codex:   { enabled: boolean; home_path: string; active_probe_enabled?: boolean; passive_sync_enabled?: boolean; safe_options: Record<string, unknown> }
  copilot: { enabled: boolean; home_path: string; active_probe_enabled?: boolean; passive_sync_enabled?: boolean; safe_options: Record<string, unknown> }
  claude:  { enabled: boolean; home_path: string; active_probe_enabled?: boolean; passive_sync_enabled?: boolean; safe_options: Record<string, unknown> }
}
