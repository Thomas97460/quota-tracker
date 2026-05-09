import React, { useMemo } from "react"
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts"
import type { UsageRow } from "../../types"
import { formatLargeNumber, formatCost } from "../../utils"

interface TokenBreakdownPieProps {
  rows: UsageRow[]
  className?: string
}

interface Slice {
  label: string
  value: number
  cost: number
  color: string
}

function aggregate(rows: UsageRow[]): { total: number; totalCost: number; slices: Slice[] } {
  const sums = rows.reduce(
    (acc, row) => ({
      input: acc.input + row.input_tokens,
      output: acc.output + row.output_tokens,
      cached: acc.cached + row.cached_tokens,
      reasoning: acc.reasoning + row.reasoning_tokens + row.thoughts_tokens,
      tool: acc.tool + row.tool_tokens,
      inputCost: acc.inputCost + (row.input_cost ?? 0),
      outputCost: acc.outputCost + (row.output_cost ?? 0),
      cachedCost: acc.cachedCost + (row.cached_cost ?? 0),
    }),
    { input: 0, output: 0, cached: 0, reasoning: 0, tool: 0, inputCost: 0, outputCost: 0, cachedCost: 0 },
  )
  const total = sums.input + sums.output + sums.cached + sums.reasoning + sums.tool
  const totalCost = sums.inputCost + sums.outputCost + sums.cachedCost
  return {
    total,
    totalCost,
    slices: [
      { label: "Input", value: sums.input, cost: sums.inputCost, color: "#8B5CF6" },
      { label: "Output", value: sums.output, cost: sums.outputCost, color: "#4F8DF7" },
      { label: "Cached", value: sums.cached, cost: sums.cachedCost, color: "#10B981" },
      { label: "Reasoning", value: sums.reasoning, cost: 0, color: "#F59E0B" },
      { label: "Tool", value: sums.tool, cost: 0, color: "#EC4899" },
    ],
  }
}

export function TokenBreakdownPie({
  rows,
  className = "",
}: TokenBreakdownPieProps): React.JSX.Element {
  const { total, totalCost, slices } = useMemo(() => aggregate(rows), [rows])
  const visible = slices.filter((s) => s.value > 0)

  if (total === 0) {
    return (
      <div
        className={className}
        style={{ color: "var(--fg-3)", fontSize: 13, padding: "12px 0" }}
      >
        No token data in selected range
      </div>
    )
  }

  return (
    <div className={className}>
      <div className="donut-layout">
        <div className="donut-wrap">
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
                  backgroundColor: "#14171F",
                  border: "1px solid #1F232E",
                  borderRadius: 8,
                  color: "#F4F5F8",
                  fontSize: 16,
                }}
                formatter={(value: number, name: string) => [
                  `${formatLargeNumber(value)} (${((value / total) * 100).toFixed(0)}%)`,
                  name,
                ]}
              />
            </PieChart>
          </ResponsiveContainer>
          <div className="donut-center">
            <div style={{ textAlign: "center" }}>
              <div className="v" style={{ fontSize: 15, fontWeight: 600, fontVariantNumeric: "tabular-nums", letterSpacing: "-0.02em" }}>
                {formatLargeNumber(total)}
              </div>
              <div className="l" style={{ fontSize: 10, color: "var(--fg-3)", textTransform: "uppercase", letterSpacing: "0.08em", marginTop: 2 }}>
                tokens
              </div>
              {totalCost > 0 && (
                <div style={{ marginTop: 2, fontSize: 12, color: "var(--ok)", fontWeight: 500 }}>
                  ~{formatCost(totalCost)}
                </div>
              )}
            </div>
          </div>
        </div>
        <div className="token-list">
          {visible.map((s) => (
            <div
              key={s.label}
              className="token-list-row"
              style={{ ["--c" as string]: s.color }}
            >
              <span className="dot"></span>
              <span className="name" style={{ textTransform: "capitalize" }}>
                {s.label}
              </span>
              <span className="v" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span>{formatLargeNumber(s.value)}</span>
                {s.cost > 0 && (
                  <span style={{ color: "var(--ok)", fontWeight: 500 }}>
                    (~{formatCost(s.cost)})
                  </span>
                )}
              </span>
              <span className="pct">{((s.value / total) * 100).toFixed(0)}%</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
