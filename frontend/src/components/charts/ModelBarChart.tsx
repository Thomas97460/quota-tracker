import React, { useMemo } from "react"
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import type { ProviderId, UsageRow } from "../../types"
import { formatLargeNumber } from "../../utils"

interface ModelBarChartProps {
  data: UsageRow[]
  /** Optional single color override (when on a provider detail page). */
  singleColor?: string
  className?: string
}

const PROVIDER_COLORS: Record<ProviderId, string> = {
  gemini: "#4F8DF7",
  codex: "#10B981",
  copilot: "#F59E0B",
  claude: "#D97757",
}

export function ModelBarChart({
  data,
  singleColor,
  className = "",
}: ModelBarChartProps): React.JSX.Element {
  const chartData = useMemo(() => {
    const sliced = [...data]
      .sort((a, b) => b.total_tokens - a.total_tokens)
      .slice(0, 15)
    const nameCounts = new Map<string, number>()
    for (const row of sliced) nameCounts.set(row.bucket, (nameCounts.get(row.bucket) ?? 0) + 1)
    return sliced.map((row) => ({
      name:
        row.provider_id && (nameCounts.get(row.bucket) ?? 0) > 1
          ? `${row.provider_id}: ${row.bucket}`
          : row.bucket,
      tokens: row.total_tokens,
      provider_id: row.provider_id,
    }))
  }, [data])

  if (chartData.length === 0) {
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
        No model usage data
      </div>
    )
  }

  return (
    <div className={className} style={{ width: "100%", height: 240 }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={chartData}
          layout="vertical"
          margin={{ top: 4, right: 16, left: 0, bottom: 4 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#1F232E" vertical horizontal={false} />
          <XAxis
            type="number"
            tick={{ fill: "#767B8A", fontSize: 14, fontFamily: "Geist, sans-serif" }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v: number) => formatLargeNumber(v)}
          />
          <YAxis
            type="category"
            dataKey="name"
            tick={{ fill: "#767B8A", fontSize: 14, fontFamily: "Geist, sans-serif" }}
            tickLine={false}
            axisLine={false}
            width={140}
            tickFormatter={(v: string) => (v.length > 18 ? `${v.slice(0, 16)}…` : v)}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#14171F",
              border: "1px solid #1F232E",
              borderRadius: 8,
              color: "#F4F5F8",
              fontSize: 16,
            }}
            formatter={(value: number) => [formatLargeNumber(value), "Tokens"]}
          />
          <Bar dataKey="tokens" radius={[0, 4, 4, 0]}>
            {chartData.map((entry, index) => (
              <Cell
                key={index}
                fill={
                  singleColor
                    ? singleColor
                    : entry.provider_id
                      ? PROVIDER_COLORS[entry.provider_id as ProviderId] ?? "#10B981"
                      : "#10B981"
                }
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
