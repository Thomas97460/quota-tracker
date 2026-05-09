import React, { useMemo } from "react"
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts"
import type { UsageRow } from "../../types"
import { formatLargeNumber } from "../../utils"

interface TokenBreakdownPieProps {
  rows: UsageRow[]
  className?: string
}

interface Slice {
  label: string
  value: number
  color: string
  tailwind: string
}

function aggregate(rows: UsageRow[]): { total: number; slices: Slice[] } {
  const sums = rows.reduce(
    (acc, row) => ({
      input: acc.input + row.input_tokens,
      output: acc.output + row.output_tokens,
      cached: acc.cached + row.cached_tokens,
      reasoning: acc.reasoning + row.reasoning_tokens + row.thoughts_tokens,
      tool: acc.tool + row.tool_tokens,
    }),
    { input: 0, output: 0, cached: 0, reasoning: 0, tool: 0 },
  )
  const total = sums.input + sums.output + sums.cached + sums.reasoning + sums.tool
  return {
    total,
    slices: [
      { label: "Input",     value: sums.input,     color: "#8b5cf6", tailwind: "bg-violet-500" },
      { label: "Output",    value: sums.output,    color: "#3b82f6", tailwind: "bg-blue-500" },
      { label: "Cached",    value: sums.cached,    color: "#10b981", tailwind: "bg-emerald-500" },
      { label: "Reasoning", value: sums.reasoning, color: "#f59e0b", tailwind: "bg-amber-500" },
      { label: "Tool",      value: sums.tool,      color: "#ef4444", tailwind: "bg-red-500" },
    ],
  }
}

export function TokenBreakdownPie({ rows, className = "" }: TokenBreakdownPieProps): React.JSX.Element {
  const { total, slices } = useMemo(() => aggregate(rows), [rows])
  const visible = slices.filter((s) => s.value > 0)

  if (total === 0) {
    return (
      <div className={`text-sm text-slate-500 py-3 ${className}`}>
        No token data in selected range
      </div>
    )
  }

  return (
    <div className={`flex flex-col gap-3 ${className}`}>
      {/* Donut chart — innerRadius makes it a ring */}
      <div className="w-full h-40">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={visible}
              dataKey="value"
              nameKey="label"
              cx="50%"
              cy="50%"
              innerRadius="55%"
              outerRadius="80%"
              strokeWidth={0}
              minAngle={4}
            >
              {visible.map((s) => (
                <Cell key={s.label} fill={s.color} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{
                backgroundColor: "#1e293b",
                border: "1px solid #334155",
                borderRadius: 8,
                color: "#f1f5f9",
                fontSize: 12,
              }}
              formatter={(value: number, name: string) => [
                `${formatLargeNumber(value)} (${((value / total) * 100).toFixed(0)}%)`,
                name,
              ]}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
      {/* Legend grid — same style as TokenBreakdown */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs sm:grid-cols-3">
        {visible.map((s) => (
          <div key={s.label} className="flex items-center gap-2">
            <span className={`h-2 w-2 rounded-full ${s.tailwind} shrink-0`} />
            <span className="text-slate-400 truncate">{s.label}</span>
            <span className="ml-1 flex items-baseline gap-1">
              <span className="font-medium text-slate-200 tabular-nums">{formatLargeNumber(s.value)}</span>
              <span className="text-slate-600 text-[10px] tabular-nums">{((s.value / total) * 100).toFixed(0)}%</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
