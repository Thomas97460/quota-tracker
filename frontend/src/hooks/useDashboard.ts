import { useCallback, useEffect, useState } from "react"
import { apiGet } from "../api"
import type { ProviderId, ProviderSummary, QuotaRow, SessionRow, UsageRow } from "../types"

export type Range = "24h" | "7d" | "30d" | "all"
export type Granularity = "hour" | "day"

interface DashboardState {
  providers: ProviderSummary[]
  quotas: QuotaRow[]
  sessions: SessionRow[]
  /** Time-series usage at the requested granularity, scoped to provider+range. */
  timeSeries: UsageRow[]
  /** Per-provider time-series at the requested granularity (Overview only). */
  timeSeriesByProvider: Record<ProviderId, UsageRow[]>
  /** Per-model usage totals, scoped to provider+range. */
  modelUsage: UsageRow[]
  /** Per-provider totals (always range-scoped, not provider-filtered). */
  providerTotals: UsageRow[]
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

export function useDashboard(
  providerId: ProviderId | undefined,
  range: Range,
  granularity: Granularity,
): DashboardState {
  const [providers, setProviders] = useState<ProviderSummary[]>([])
  const [quotas, setQuotas] = useState<QuotaRow[]>([])
  const [sessions, setSessions] = useState<SessionRow[]>([])
  const [timeSeries, setTimeSeries] = useState<UsageRow[]>([])
  const [timeSeriesByProvider, setTimeSeriesByProvider] = useState<
    Record<ProviderId, UsageRow[]>
  >({ gemini: [], codex: [], copilot: [] })
  const [modelUsage, setModelUsage] = useState<UsageRow[]>([])
  const [providerTotals, setProviderTotals] = useState<UsageRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tick, setTick] = useState(0)

  const refresh = useCallback(() => setTick((t) => t + 1), [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    const start = rangeStartIso(range) ?? undefined
    const scope = { provider_id: providerId, start }

    const calls: Promise<unknown>[] = [
      apiGet<{ providers: ProviderSummary[] }>("/api/providers"),
      apiGet<{ items: QuotaRow[] }>(
        `/api/quotas${buildQuery({ provider_id: providerId, limit: 200 })}`,
      ),
      apiGet<{ items: SessionRow[] }>(`/api/sessions${buildQuery(scope)}`),
      apiGet<{ items: UsageRow[] }>(
        `/api/token-usage${buildQuery({ ...scope, group_by: granularity })}`,
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
            `/api/token-usage${buildQuery({ provider_id: pid, start, group_by: granularity })}`,
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
          sessRes,
          tsRes,
          modelRes,
          providerRes,
          ...providerSeries
        ] = results as [
          { providers: ProviderSummary[] },
          { items: QuotaRow[] },
          { items: SessionRow[] },
          { items: UsageRow[] },
          { items: UsageRow[] },
          { items: UsageRow[] },
          ...{ items: UsageRow[] }[],
        ]
        setProviders(provRes.providers)
        setQuotas(quotaRes.items)
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
  }, [providerId, range, granularity, tick])

  return {
    providers,
    quotas,
    sessions,
    timeSeries,
    timeSeriesByProvider,
    modelUsage,
    providerTotals,
    loading,
    error,
    refresh,
  }
}
