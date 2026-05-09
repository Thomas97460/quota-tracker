import { useEffect, useState } from "react"
import { apiGet } from "../api"
import type { ProjectUsageResponse, ProviderId } from "../types"
import type { Range } from "./useDashboard"

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

export function useProjectUsage(
  range: Range,
  provider: ProviderId | "all",
  page: number,
  pageSize: number,
): {
  items: ProjectUsageResponse["items"]
  total: number
  total_tokens: number
  loading: boolean
  error: string | null
} {
  const [items, setItems] = useState<ProjectUsageResponse["items"]>([])
  const [total, setTotal] = useState(0)
  const [totalTokens, setTotalTokens] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    const start = rangeStartIso(range) ?? undefined
    const offset = page * pageSize
    const provider_id = provider === "all" ? undefined : provider
    apiGet<ProjectUsageResponse>(
      `/api/token-usage/by-project${buildQuery({ provider_id, start, limit: pageSize, offset })}`,
    )
      .then((res) => {
        if (cancelled) return
        setItems(res.items)
        setTotal(res.total)
        setTotalTokens(res.total_tokens)
      })
      .catch((e: unknown) => {
        if (cancelled) return
        setItems([])
        setTotal(0)
        setTotalTokens(0)
        setError(e instanceof Error ? e.message : "Failed to load project usage")
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [range, provider, page, pageSize])

  return { items, total, total_tokens: totalTokens, loading, error }
}

