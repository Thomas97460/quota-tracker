import React from "react"
import type { Granularity, Range } from "../../hooks/useDashboard"

const RANGES: Range[] = ["24h", "7d", "30d", "all"]
const GRANULARITIES: Granularity[] = ["hour", "day"]

interface RangePickerProps {
  range: Range
  granularity: Granularity
  onRangeChange: (r: Range) => void
  onGranularityChange: (g: Granularity) => void
}

function pillClass(active: boolean): string {
  const base = "px-3 py-1.5 text-xs font-medium transition-colors"
  return active
    ? `${base} bg-violet-600 text-white`
    : `${base} bg-slate-800 text-slate-400 hover:text-slate-200`
}

export function RangePicker({
  range,
  granularity,
  onRangeChange,
  onGranularityChange,
}: RangePickerProps): React.JSX.Element {
  return (
    <div className="flex items-center gap-2">
      <div className="flex overflow-hidden rounded-lg border border-slate-700">
        {RANGES.map((r) => (
          <button key={r} onClick={() => onRangeChange(r)} className={pillClass(range === r)}>
            {r}
          </button>
        ))}
      </div>
      <div className="flex overflow-hidden rounded-lg border border-slate-700">
        {GRANULARITIES.map((g) => (
          <button
            key={g}
            onClick={() => onGranularityChange(g)}
            className={pillClass(granularity === g)}
          >
            {g}
          </button>
        ))}
      </div>
    </div>
  )
}
