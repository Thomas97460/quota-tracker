import React, { useMemo } from "react"
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import type { QuotaRow } from "../../types"
import { formatTimeBucket } from "../../utils"

interface QuotaHistoryChartProps {
  rows: QuotaRow[]
  className?: string
}

// Distinct colours for up to ~6 quota names
const LINE_COLORS = ["#8b5cf6", "#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#ec4899"]

export function QuotaHistoryChart({ rows, className = "" }: QuotaHistoryChartProps): React.JSX.Element {
  const { data, names } = useMemo(() => {
    // Group rows by timestamp, spread quota_name values as columns
    const allNames = [...new Set(rows.map((r) => r.quota_name))].sort()
    const byTs = new Map<string, Record<string, number | null>>()
    for (const r of rows) {
      if (!byTs.has(r.timestamp)) byTs.set(r.timestamp, {})
      byTs.get(r.timestamp)![r.quota_name] = r.used_percent
    }
    const data = [...byTs.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([ts, vals]) => ({ bucket: ts, ...vals }))
    return { data, names: allNames }
  }, [rows])

  if (data.length === 0) {
    return (
      <div className={`flex items-center justify-center h-56 text-slate-500 text-sm ${className}`}>
        No quota history data
      </div>
    )
  }

  return (
    <div className={`w-full h-56 ${className}`}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
          <XAxis
            dataKey="bucket"
            tick={{ fill: "#94a3b8", fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            interval="preserveStartEnd"
            tickFormatter={(v: string) => formatTimeBucket(v)}
          />
          <YAxis
            domain={[0, 100]}
            tick={{ fill: "#94a3b8", fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            width={36}
            tickFormatter={(v: number) => `${v}%`}
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
            labelFormatter={(v: string) => formatTimeBucket(v)}
            formatter={(value: number, name: string) => [`${value?.toFixed(1) ?? "n/a"}%`, name]}
          />
          <Legend wrapperStyle={{ fontSize: 11, color: "#94a3b8" }} />
          {names.map((name, i) => (
            <Line
              key={name}
              type="monotone"
              dataKey={name}
              stroke={LINE_COLORS[i % LINE_COLORS.length]}
              strokeWidth={2}
              dot={false}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
