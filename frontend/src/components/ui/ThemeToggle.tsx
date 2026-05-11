import React from "react"
import { Moon, Sun } from "lucide-react"
import { useTheme } from "../../hooks/useTheme"

export function ThemeToggle(): React.JSX.Element {
  const [theme, toggleTheme] = useTheme()
  const isLight = theme === "light"

  return (
    <button
      className="theme-toggle"
      onClick={toggleTheme}
      title={isLight ? "Switch to dark mode" : "Switch to light mode"}
      aria-label={isLight ? "Switch to dark mode" : "Switch to light mode"}
    >
      {isLight ? <Moon size={18} strokeWidth={2.2} /> : <Sun size={18} strokeWidth={2.2} />}
    </button>
  )
}
