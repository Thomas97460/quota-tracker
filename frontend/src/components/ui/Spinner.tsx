import React from "react"

type Size = "sm" | "md" | "lg"

interface SpinnerProps {
  size?: Size
  className?: string
}

const sizeClasses: Record<Size, string> = {
  sm: "h-3 w-3 border",
  md: "h-5 w-5 border-2",
  lg: "h-8 w-8 border-2",
}

export function Spinner({ size = "md", className = "" }: SpinnerProps): React.JSX.Element {
  return (
    <span
      className={`inline-block animate-spin rounded-full border-slate-600 border-t-violet-500 ${sizeClasses[size]} ${className}`}
      role="status"
      aria-label="Loading"
    />
  )
}
