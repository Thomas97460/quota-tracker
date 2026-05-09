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
import { chartTickInterval, formatLargeNumber, formatTimeBucket } from "../../utils"

export type StackMode = "provider" | "kind"

const PROVIDER_COLORS: Record<ProviderId, string> = {
  gemini: "#4F8DF7",
  codex: "#10B981",
  copilot: "#F59E0B",
  claude: "#D97757",
}

const KIND_COLORS: Record<string, string> = {
  input: "#8B5CF6",
  output: "#4F8DF7",
  cached: "#10B981",
  reasoning: "#F59E0B",
  tool: "#EC4899",
}

interface StackedTokenChartProps {
  /** When mode === "provider": series keyed by provider id, sharing a time bucket. */
  byProvider?: Record<ProviderId, UsageRow[]>
  /** When mode === "kind": a single series; the chart splits into token-kind bands. */
  rows?: UsageRow[]
  mode: StackMode
  className?: string
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
    claude: new Map(byProvider.claude.map((r) => [r.bucket, r.total_tokens])),
  }
  return buckets.map((bucket) => ({
    bucket,
    gemini: indexed.gemini.get(bucket) ?? 0,
    codex: indexed.codex.get(bucket) ?? 0,
    copilot: indexed.copilot.get(bucket) ?? 0,
    claude: indexed.claude.get(bucket) ?? 0,
  }))
}

function buildKindRows(rows: UsageRow[]) {
  return [...rows]
    .sort((a, b) => a.bucket.localeCompare(b.bucket))
    .map((row) => ({
      bucket: row.bucket,
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
      <div
        className={className}
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: 240,
          color: "var(--fg-3)",
          fontSize: 13,
        }}
      >
        No token usage data
      </div>
    )
  }

  const series =
    mode === "provider"
      ? (["gemini", "codex", "copilot", "claude"] as ProviderId[]).map((id) => ({
          key: id,
          color: PROVIDER_COLORS[id],
        }))
      : ["input", "output", "cached", "reasoning", "tool"].map((key) => ({
          key,
          color: KIND_COLORS[key],
        }))

  return (
    <div className={className} style={{ width: "100%", height: 240 }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1F232E" vertical={false} />
          <XAxis
            dataKey="bucket"
            tick={{ fill: "#767B8A", fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            interval={chartTickInterval(data.length, 8)}
            tickFormatter={(v: string) => formatTimeBucket(v)}
          />
          <YAxis
            tick={{ fill: "#767B8A", fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v: number) => formatLargeNumber(v)}
            width={48}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#14171F",
              border: "1px solid #1F232E",
              borderRadius: 8,
              color: "#F4F5F8",
              fontSize: 12,
            }}
            labelStyle={{ color: "#767B8A" }}
            labelFormatter={(v: string) => formatTimeBucket(v)}
            formatter={(value: number, name: string) => [formatLargeNumber(value), name]}
          />
          <Legend wrapperStyle={{ fontSize: 11, color: "#767B8A" }} />
          {series.map(({ key, color }) => (
            <Area
              key={key}
              type="monotone"
              dataKey={key}
              stackId="1"
              stroke={color}
              fill={color}
              fillOpacity={0.45}
              strokeWidth={1.5}
              dot={false}
              activeDot={{ r: 4, fill: color }}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
