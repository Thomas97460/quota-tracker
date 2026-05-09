import React, { useMemo } from "react"
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import type { ProviderId, UsageRow } from "../../types"
import { formatLargeNumber } from "../../utils"

export type StackMode = "provider" | "kind"

const PROVIDER_COLORS: Record<ProviderId, string> = {
  gemini: "#3b82f6",
  codex: "#10b981",
  copilot: "#f97316",
}

const KIND_COLORS: Record<string, string> = {
  input: "#8b5cf6",
  output: "#3b82f6",
  cached: "#10b981",
  reasoning: "#f59e0b",
  tool: "#ef4444",
}

interface StackedTokenChartProps {
  /** When mode === "provider": series keyed by provider id, sharing a time bucket. */
  byProvider?: Record<ProviderId, UsageRow[]>
  /** When mode === "kind": a single series; the chart splits into token-kind bands. */
  rows?: UsageRow[]
  mode: StackMode
  className?: string
}

function formatBucket(bucket: string): string {
  if (bucket.length === 13) {
    const [datePart, hour] = bucket.split("T")
    const [, month, day] = datePart.split("-")
    return `${month}/${day} ${hour}h`
  }
  if (bucket.length === 10) {
    const [, month, day] = bucket.split("-")
    return `${month}/${day}`
  }
  return bucket
}

function unionBuckets(rowsByKey: Record<string, UsageRow[]>): string[] {
  const set = new Set<string>()
  for (const list of Object.values(rowsByKey)) {
    for (const row of list) set.add(row.bucket)
  }
  return [...set].sort()
}

function buildProviderRows(byProvider: Record<ProviderId, UsageRow[]>) {
  const buckets = unionBuckets(byProvider)
  const indexed: Record<ProviderId, Map<string, number>> = {
    gemini: new Map(byProvider.gemini.map((r) => [r.bucket, r.total_tokens])),
    codex: new Map(byProvider.codex.map((r) => [r.bucket, r.total_tokens])),
    copilot: new Map(byProvider.copilot.map((r) => [r.bucket, r.total_tokens])),
  }
  return buckets.map((bucket) => ({
    label: formatBucket(bucket),
    gemini: indexed.gemini.get(bucket) ?? 0,
    codex: indexed.codex.get(bucket) ?? 0,
    copilot: indexed.copilot.get(bucket) ?? 0,
  }))
}

function buildKindRows(rows: UsageRow[]) {
  return [...rows]
    .sort((a, b) => a.bucket.localeCompare(b.bucket))
    .map((row) => ({
      label: formatBucket(row.bucket),
      input: row.input_tokens,
      output: row.output_tokens,
      cached: row.cached_tokens,
      reasoning: row.reasoning_tokens + row.thoughts_tokens,
      tool: row.tool_tokens,
    }))
}

export function StackedTokenChart({
  byProvider,
  rows,
  mode,
  className = "",
}: StackedTokenChartProps): React.JSX.Element {
  const data = useMemo(() => {
    if (mode === "provider" && byProvider) return buildProviderRows(byProvider)
    if (mode === "kind" && rows) return buildKindRows(rows)
    return []
  }, [mode, byProvider, rows])

  if (data.length === 0) {
    return (
      <div className={`flex items-center justify-center h-56 text-slate-500 text-sm ${className}`}>
        No token usage data
      </div>
    )
  }

  const series =
    mode === "provider"
      ? (["gemini", "codex", "copilot"] as ProviderId[]).map((id) => ({
          key: id,
          color: PROVIDER_COLORS[id],
        }))
      : ["input", "output", "cached", "reasoning", "tool"].map((key) => ({
          key,
          color: KIND_COLORS[key],
        }))

  return (
    <div className={`w-full h-56 ${className}`}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fill: "#94a3b8", fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fill: "#94a3b8", fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v: number) => formatLargeNumber(v)}
            width={48}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#1e293b",
              border: "1px solid #334155",
              borderRadius: 8,
              color: "#f1f5f9",
              fontSize: 12,
            }}
            labelStyle={{ color: "#94a3b8" }}
            formatter={(value: number, name: string) => [formatLargeNumber(value), name]}
          />
          <Legend wrapperStyle={{ fontSize: 11, color: "#94a3b8" }} />
          {series.map(({ key, color }) => (
            <Area
              key={key}
              type="monotone"
              dataKey={key}
              stackId="1"
              stroke={color}
              fill={color}
              fillOpacity={0.55}
              strokeWidth={1.5}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
