import React from "react"

type Variant = "default" | "success" | "warning" | "error" | "info"

interface BadgeProps {
  variant?: Variant
  children: React.ReactNode
  className?: string
}

const variantClasses: Record<Variant, string> = {
  default: "bg-slate-700 text-slate-300",
  success: "bg-green-900/60 text-green-400 border border-green-700/40",
  warning: "bg-amber-900/60 text-amber-400 border border-amber-700/40",
  error:   "bg-red-900/60 text-red-400 border border-red-700/40",
  info:    "bg-violet-900/60 text-violet-400 border border-violet-700/40",
}

export function Badge({ variant = "default", children, className = "" }: BadgeProps): React.JSX.Element {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${variantClasses[variant]} ${className}`}
    >
      {children}
    </span>
  )
}
