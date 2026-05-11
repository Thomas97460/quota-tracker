import { useEffect, useState } from "react"

export function useTheme(): [string, () => void] {
  const [theme, setTheme] = useState<string>(() => {
    return localStorage.getItem("qt-theme") ?? "dark"
  })

  useEffect(() => {
    document.documentElement.dataset.theme = theme === "light" ? "light" : ""
    localStorage.setItem("qt-theme", theme)
  }, [theme])

  const toggle = () => setTheme((t) => (t === "light" ? "dark" : "light"))
  return [theme, toggle]
}
