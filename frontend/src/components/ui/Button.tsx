import React from "react"
import { Spinner } from "./Spinner"

type Variant = "primary" | "ghost" | "danger"
type Size = "sm" | "md"

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  loading?: boolean
}

const variantClasses: Record<Variant, string> = {
  primary: "bg-violet-600 hover:bg-violet-500 text-white border-transparent",
  ghost:   "bg-transparent hover:bg-slate-700 text-slate-300 border-slate-600",
  danger:  "bg-red-900/40 hover:bg-red-800/60 text-red-400 border-red-700/40",
}

const sizeClasses: Record<Size, string> = {
  sm: "px-2.5 py-1 text-xs",
  md: "px-3.5 py-1.5 text-sm",
}

export function Button({
  variant = "ghost",
  size = "md",
  loading = false,
  disabled,
  children,
  className = "",
  ...rest
}: ButtonProps): React.JSX.Element {
  const isDisabled = disabled || loading
  return (
    <button
      {...rest}
      disabled={isDisabled}
      className={`inline-flex items-center gap-1.5 rounded-lg border font-medium transition-colors
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-500
        disabled:cursor-not-allowed disabled:opacity-50
        ${variantClasses[variant]} ${sizeClasses[size]} ${className}`}
    >
      {loading && <Spinner size="sm" />}
      {children}
    </button>
  )
}
