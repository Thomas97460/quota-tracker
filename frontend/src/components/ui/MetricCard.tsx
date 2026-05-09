import React from "react"

interface MetricCardProps {
  label: string
  value: string | number
  sub?: string
  icon?: React.ReactNode
  className?: string
}

export function MetricCard({
  label,
  value,
  sub,
  className = "",
}: MetricCardProps): React.JSX.Element {
  return (
    <div className={`kpi ${className}`}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">
        <span>{value}</span>
      </div>
      {sub && (
        <div className="kpi-foot">
          <span>{sub}</span>
        </div>
      )}
    </div>
  )
}
