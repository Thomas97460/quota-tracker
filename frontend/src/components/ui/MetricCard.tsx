import React from "react"
import { Card } from "./Card"

interface MetricCardProps {
  label: string
  value: string | number
  sub?: string
  icon?: React.ReactNode
  className?: string
}

export function MetricCard({ label, value, sub, icon, className = "" }: MetricCardProps): React.JSX.Element {
  return (
    <Card className={className}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wide">{label}</p>
          <p className="mt-1 text-2xl font-semibold text-slate-100 leading-none">{value}</p>
          {sub && <p className="mt-1 text-xs text-slate-500">{sub}</p>}
        </div>
        {icon && (
          <div className="shrink-0 text-slate-500">{icon}</div>
        )}
      </div>
    </Card>
  )
}
