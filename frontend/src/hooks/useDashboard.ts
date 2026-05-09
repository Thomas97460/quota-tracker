import { useCallback, useEffect, useState } from "react"
import { apiGet } from "../api"
import type { ProjectUsageRow, ProviderId, ProviderSummary, QuotaRow, SessionRow, UsageRow } from "../types"

export type Range = "24h" | "7d" | "30d" | "all"
export type Granularity = "hour" | "day" // Kept for backwards compatibility if needed, but not used in args

interface DashboardState {
  providers: ProviderSummary[]
  quotas: QuotaRow[]
  /** Chronological quota series for sparkline/history chart. */
  quotaHistory: QuotaRow[]
  sessions: SessionRow[]
  /** Time-series usage at the requested granularity, scoped to provider+range. */
  timeSeries: UsageRow[]
  /** Per-provider time-series at the requested granularity (Overview only). */
  timeSeriesByProvider: Record<ProviderId, UsageRow[]>
  /** Per-model usage totals, scoped to provider+range. */
  modelUsage: UsageRow[]
  /** Per-provider totals (always range-scoped, not provider-filtered). */
  providerTotals: UsageRow[]
  /** Top projects by token usage (only when providerId is set). */
  projectUsage: ProjectUsageRow[]
  projectUsageTotal: number
  projectPage: number
  projectPageSize: number
  setProjectPage: (n: number) => void
  loading: boolean
  error: string | null
  refresh: () => void
}

const RANGE_HOURS: Record<Range, number | null> = {
  "24h": 24,
  "7d": 24 * 7,
  "30d": 24 * 30,
  all: null,
}

function rangeStartIso(range: Range): string | null {
  const hours = RANGE_HOURS[range]
  if (hours === null) return null
  return new Date(Date.now() - hours * 3_600_000).toISOString()
}

function buildQuery(params: Record<string, string | number | undefined>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== "")
  if (entries.length === 0) return ""
  return `?${entries.map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&")}`
}

const PROVIDER_IDS: ProviderId[] = ["gemini", "codex", "copilot"]
const PROJECT_PAGE_SIZE = 5

export function useDashboard(
  providerId: ProviderId | undefined,
  range: Range,
  modelFilter?: string,
): DashboardState {
  const [providers, setProviders] = useState<ProviderSummary[]>([])
  const [quotas, setQuotas] = useState<QuotaRow[]>([])
  const [quotaHistory, setQuotaHistory] = useState<QuotaRow[]>([])
  const [sessions, setSessions] = useState<SessionRow[]>([])
  const [timeSeries, setTimeSeries] = useState<UsageRow[]>([])
  const [timeSeriesByProvider, setTimeSeriesByProvider] = useState<
    Record<ProviderId, UsageRow[]>
  >({ gemini: [], codex: [], copilot: [] })
  const [modelUsage, setModelUsage] = useState<UsageRow[]>([])
  const [providerTotals, setProviderTotals] = useState<UsageRow[]>([])
  const [projectUsage, setProjectUsage] = useState<ProjectUsageRow[]>([])
  const [projectUsageTotal, setProjectUsageTotal] = useState(0)
  const [projectPage, setProjectPage] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tick, setTick] = useState(0)

  const refresh = useCallback(() => setTick((t) => t + 1), [])

  // Main data fetch — re-runs when provider/range/granularity/tick changes.
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    const start = rangeStartIso(range) ?? undefined
    const scope = { provider_id: providerId, start }
    // Apply model filter only to the time-series fetch.
    const modelName = modelFilter && modelFilter !== "all" ? modelFilter : undefined

    const calls: Promise<unknown>[] = [
      apiGet<{ providers: ProviderSummary[] }>("/api/providers"),
      apiGet<{ items: QuotaRow[] }>(
        `/api/quotas${buildQuery({ provider_id: providerId, limit: 200 })}`,
      ),
      // Chronological history for the chart (asc order)
      apiGet<{ items: QuotaRow[] }>(
        `/api/quotas${buildQuery({ provider_id: providerId, start, order: "asc", limit: 1000 })}`,
      ),
      apiGet<{ items: SessionRow[] }>(`/api/sessions${buildQuery(scope)}`),
      apiGet<{ items: UsageRow[] }>(
        `/api/token-usage${buildQuery({ ...scope, model_name: modelName, group_by: "hour" })}`,
      ),
      apiGet<{ items: UsageRow[] }>(
        `/api/token-usage${buildQuery({ ...scope, group_by: "model" })}`,
      ),
      apiGet<{ items: UsageRow[] }>(
        `/api/token-usage${buildQuery({ start, group_by: "provider" })}`,
      ),
    ]

    // Per-provider series only for the all-providers (overview) view.
    if (!providerId) {
      for (const pid of PROVIDER_IDS) {
        calls.push(
          apiGet<{ items: UsageRow[] }>(
            `/api/token-usage${buildQuery({ provider_id: pid, start, group_by: "hour" })}`,
          ),
        )
      }
    }

    Promise.all(calls)
      .then((results) => {
        if (cancelled) return
        const [
          provRes,
          quotaRes,
          quotaHistRes,
          sessRes,
          tsRes,
          modelRes,
          providerRes,
          ...providerSeries
        ] = results as [
          { providers: ProviderSummary[] },
          { items: QuotaRow[] },
          { items: QuotaRow[] },
          { items: SessionRow[] },
          { items: UsageRow[] },
          { items: UsageRow[] },
          { items: UsageRow[] },
          ...{ items: UsageRow[] }[],
        ]
        setProviders(provRes.providers)
        setQuotas(quotaRes.items)
        setQuotaHistory(quotaHistRes.items)
        setSessions(sessRes.items)
        setTimeSeries(tsRes.items)
        setModelUsage(modelRes.items)
        setProviderTotals(providerRes.items)
        if (providerSeries.length === 3) {
          setTimeSeriesByProvider({
            gemini: providerSeries[0].items,
            codex: providerSeries[1].items,
            copilot: providerSeries[2].items,
          })
        } else {
          setTimeSeriesByProvider({ gemini: [], codex: [], copilot: [] })
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load data")
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [providerId, range, modelFilter, tick])

  // Project usage — only fetched when a specific provider is selected.
  useEffect(() => {
    if (!providerId) {
      setProjectUsage([])
      setProjectUsageTotal(0)
      return
    }
    let cancelled = false
    const start = rangeStartIso(range) ?? undefined
    const offset = projectPage * PROJECT_PAGE_SIZE
    apiGet<{ items: ProjectUsageRow[]; total: number }>(
      `/api/token-usage/by-project${buildQuery({
        provider_id: providerId,
        start,
        limit: PROJECT_PAGE_SIZE,
        offset,
      })}`,
    )
      .then((res) => {
        if (cancelled) return
        setProjectUsage(res.items)
        setProjectUsageTotal(res.total)
      })
      .catch(() => {
        if (!cancelled) {
          setProjectUsage([])
          setProjectUsageTotal(0)
        }
      })
    return () => {
      cancelled = true
    }
  }, [providerId, range, projectPage, tick])

  return {
    providers,
    quotas,
    quotaHistory,
    sessions,
    timeSeries,
    timeSeriesByProvider,
    modelUsage,
    providerTotals,
    projectUsage,
    projectUsageTotal,
    projectPage,
    projectPageSize: PROJECT_PAGE_SIZE,
    setProjectPage,
    loading,
    error,
    refresh,
  }
}
