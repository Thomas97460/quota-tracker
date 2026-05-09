import React from "react"
import type { UsageRow } from "../../types"
import { formatLargeNumber } from "../../utils"

interface TokenBreakdownProps {
  rows: UsageRow[]
  className?: string
}

interface Slice {
  label: string
  value: number
  color: string
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
      { label: "Input", value: sums.input, color: "bg-violet-500" },
      { label: "Output", value: sums.output, color: "bg-blue-500" },
      { label: "Cached", value: sums.cached, color: "bg-emerald-500" },
      { label: "Reasoning", value: sums.reasoning, color: "bg-amber-500" },
      { label: "Tool", value: sums.tool, color: "bg-red-500" },
    ],
  }
}

export function TokenBreakdown({ rows, className = "" }: TokenBreakdownProps): React.JSX.Element {
  const { total, slices } = aggregate(rows)
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
      <div className="flex h-2 w-full overflow-hidden rounded-full bg-slate-800">
        {visible.map((s) => (
          <div
            key={s.label}
            className={s.color}
            style={{ width: `${(s.value / total) * 100}%` }}
            title={`${s.label}: ${formatLargeNumber(s.value)}`}
          />
        ))}
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs sm:grid-cols-3">
        {visible.map((s) => (
          <div key={s.label} className="flex items-center gap-2">
            <span className={`h-2 w-2 rounded-full ${s.color} shrink-0`} />
            <span className="text-slate-400">{s.label}</span>
            <span className="ml-auto font-medium text-slate-200">{formatLargeNumber(s.value)}</span>
            <span className="text-slate-600">{((s.value / total) * 100).toFixed(0)}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}
