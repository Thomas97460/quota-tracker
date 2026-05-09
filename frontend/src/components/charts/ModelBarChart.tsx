import React, { useMemo } from "react"
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import type { UsageRow } from "../../types"
import { formatLargeNumber } from "../../utils"

interface ModelBarChartProps {
  data: UsageRow[]
  className?: string
}

export function ModelBarChart({ data, className = "" }: ModelBarChartProps): React.JSX.Element {
  const chartData = useMemo(
    () =>
      [...data]
        .sort((a, b) => b.total_tokens - a.total_tokens)
        .slice(0, 15)
        .map((row) => ({
          name: row.bucket,
          tokens: row.total_tokens,
        })),
    [data]
  )

  if (chartData.length === 0) {
    return (
      <div className={`flex items-center justify-center h-56 text-slate-500 text-sm ${className}`}>
        No model usage data
      </div>
    )
  }

  return (
    <div className={`w-full h-56 ${className}`}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={chartData}
          layout="vertical"
          margin={{ top: 4, right: 16, left: 0, bottom: 4 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical horizontal={false} />
          <XAxis
            type="number"
            tick={{ fill: "#94a3b8", fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v: number) => formatLargeNumber(v)}
          />
          <YAxis
            type="category"
            dataKey="name"
            tick={{ fill: "#94a3b8", fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            width={140}
            tickFormatter={(v: string) => (v.length > 18 ? `${v.slice(0, 16)}…` : v)}
          />
          <Tooltip
            contentStyle={{ backgroundColor: "#1e293b", border: "1px solid #334155", borderRadius: 8, color: "#f1f5f9", fontSize: 12 }}
            formatter={(value: number) => [formatLargeNumber(value), "Tokens"]}
          />
          <Bar dataKey="tokens" fill="#10b981" radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
