import React from "react"
import type { Range } from "../../hooks/useDashboard"

const RANGES: Range[] = ["24h", "7d", "30d", "all"]

interface RangePickerProps {
  range: Range
  onRangeChange: (r: Range) => void
}

function pillClass(active: boolean): string {
  const base = "px-3 py-1.5 text-xs font-medium transition-colors"
  return active
    ? `${base} bg-violet-600 text-white`
    : `${base} bg-slate-800 text-slate-400 hover:text-slate-200`
}

export function RangePicker({
  range,
  onRangeChange,
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
    </div>
  )
}
