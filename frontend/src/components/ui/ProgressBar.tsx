import React from "react"

interface ProgressBarProps {
  value: number
  color?: string
  label?: string
  className?: string
}

export function ProgressBar({ value, color = "bg-violet-500", label, className = "" }: ProgressBarProps): React.JSX.Element {
  const clamped = Math.min(100, Math.max(0, value))
  const dangerColor = clamped >= 90 ? "bg-red-500" : clamped >= 70 ? "bg-amber-400" : color

  return (
    <div className={`w-full ${className}`}>
      {label && (
        <div className="flex justify-between mb-1">
          <span className="text-xs text-slate-400">{label}</span>
          <span className="text-xs text-slate-300 font-medium">{clamped.toFixed(0)}%</span>
        </div>
      )}
      <div className="h-1.5 w-full rounded-full bg-slate-700 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${dangerColor}`}
          style={{ width: `${clamped}%` }}
        />
      </div>
    </div>
  )
}
