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
import type { QuotaRow } from "../../types"

interface QuotaBarChartProps {
  quotas: QuotaRow[]
  className?: string
}

function barColor(usedPct: number): string {
  if (usedPct >= 90) return "#ef4444"
  if (usedPct >= 70) return "#f59e0b"
  return "#8b5cf6"
}

export function QuotaBarChart({ quotas, className = "" }: QuotaBarChartProps): React.JSX.Element {
  const chartData = useMemo(
    () =>
      quotas
        .filter((q) => q.used_percent !== null)
        .map((q) => ({
          name: `${q.provider_id}/${q.quota_name}`,
          used: q.used_percent ?? 0,
        })),
    [quotas]
  )

  if (chartData.length === 0) {
    return (
      <div className={`flex items-center justify-center h-48 text-slate-500 text-sm ${className}`}>
        No quota data with usage percentages
      </div>
    )
  }

  return (
    <div className={`w-full h-48 ${className}`}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} margin={{ top: 8, right: 12, left: 0, bottom: 40 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" horizontal vertical={false} />
          <XAxis
            dataKey="name"
            tick={{ fill: "#94a3b8", fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            angle={-35}
            textAnchor="end"
          />
          <YAxis
            tick={{ fill: "#94a3b8", fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            domain={[0, 100]}
            tickFormatter={(v: number) => `${v}%`}
            width={40}
          />
          <Tooltip
            contentStyle={{ backgroundColor: "#1e293b", border: "1px solid #334155", borderRadius: 8, color: "#f1f5f9", fontSize: 12 }}
            formatter={(value: number) => [`${value.toFixed(1)}%`, "Used"]}
          />
          <Bar dataKey="used" radius={[4, 4, 0, 0]}>
            {chartData.map((entry, index) => (
              <Cell key={index} fill={barColor(entry.used)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
