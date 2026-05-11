import React, { useMemo } from "react"
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import type { UsageRow } from "../../types"
import { chartTickInterval, formatLargeNumber, formatTimeBucket } from "../../utils"

interface TokenLineChartProps {
  data: UsageRow[]
  className?: string
}

export function TokenLineChart({ data, className = "" }: TokenLineChartProps): React.JSX.Element {
  const chartData = useMemo(
    () => data.map((row) => ({ bucket: row.bucket, tokens: row.total_tokens })),
    [data]
  )

  if (chartData.length === 0) {
    return (
      <div className={`flex items-center justify-center h-48 text-slate-500 text-sm ${className}`}>
        No token usage data
      </div>
    )
  }

  return (
    <div className={`w-full h-48 ${className}`}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="tokenGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" vertical={false} />
          <XAxis
            dataKey="bucket"
            tick={{ fill: "#94a3b8", fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            interval={chartTickInterval(chartData.length, 8)}
            tickFormatter={(v: string) => formatTimeBucket(v)}
          />
          <YAxis
            tick={{ fill: "#94a3b8", fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v: number) => formatLargeNumber(v)}
            width={48}
          />
          <Tooltip
            contentStyle={{ backgroundColor: "#1e293b", border: "1px solid #334155", borderRadius: 8, color: "#f1f5f9", fontSize: 12 }}
            labelStyle={{ color: "#94a3b8" }}
            labelFormatter={(v: string) => formatTimeBucket(v)}
            formatter={(value: number) => [formatLargeNumber(value), "Tokens"]}
          />
          <Area
            type="monotone"
            dataKey="tokens"
            stroke="#8b5cf6"
            strokeWidth={2}
            fill="url(#tokenGradient)"
            dot={false}
            activeDot={{ r: 4, fill: "#8b5cf6" }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
