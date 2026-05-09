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
import { chartTickInterval, formatTimeBucket } from "../../utils"

interface QuotaHistoryChartProps {
  rows: QuotaRow[]
  className?: string
}

// Distinct colours for up to ~6 quota names — using the design palette
const LINE_COLORS = ["#F59E0B", "#A78BFA", "#4F8DF7", "#10B981", "#EF4444", "#EC4899"]

export function QuotaHistoryChart({
  rows,
  className = "",
}: QuotaHistoryChartProps): React.JSX.Element {
  const { data, names } = useMemo(() => {
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
      <div
        className={className}
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: 220,
          color: "var(--fg-3)",
          fontSize: 13,
        }}
      >
        No quota history data
      </div>
    )
  }

  return (
    <div className={className} style={{ width: "100%", height: 220 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1F232E" vertical={false} />
          <XAxis
            dataKey="bucket"
            tick={{ fill: "#767B8A", fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            interval={chartTickInterval(data.length, 6)}
            tickFormatter={(v: string) => formatTimeBucket(v)}
          />
          <YAxis
            domain={[0, 100]}
            tick={{ fill: "#767B8A", fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            width={36}
            tickFormatter={(v: number) => `${v}%`}
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
            formatter={(value: number, name: string) => [
              `${value?.toFixed(1) ?? "n/a"}%`,
              name,
            ]}
          />
          <Legend wrapperStyle={{ fontSize: 11, color: "#767B8A" }} />
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
