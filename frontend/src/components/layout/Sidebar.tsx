import React, { useEffect, useState } from "react"
import { NavLink, useLocation } from "react-router-dom"
import { useProviders } from "../../contexts/ProvidersContext"
import { latestQuotas } from "../../utils"
import type { ProviderId } from "../../types"
import { rollupGeminiQuotas, filterCopilotQuotas, filterClaudeQuotas } from "../ui/QuotaPanel"

function useTheme(): [string, () => void] {
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

const PROVIDER_IDS: ProviderId[] = ["gemini", "codex", "copilot", "claude"]

const PROVIDER_NAMES: Record<ProviderId, string> = {
  gemini: "Gemini",
  codex: "Codex",
  copilot: "Copilot",
  claude: "Claude",
}

// Logo paths — claude uses claude-code.png
const PROVIDER_LOGOS: Record<ProviderId, string> = {
  gemini: "/logos/gemini.png",
  codex: "/logos/codex.png",
  copilot: "/logos/copilot.png",
  claude: "/logos/claude-code.png",
}

function LogoMark(): React.JSX.Element {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="white"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M12 4v8l5 3" />
      <circle cx="12" cy="12" r="9" />
    </svg>
  )
}

function statusFor(used: number): "crit" | "warn" | "ok" {
  if (used >= 95) return "crit"
  if (used >= 70) return "warn"
  return "ok"
}

export function Sidebar(): React.JSX.Element {
  const { providers, quotas } = useProviders()
  const location = useLocation()
  const latest = latestQuotas(quotas)
  const [theme, toggleTheme] = useTheme()

  const activeProviders = providers.filter((p) => p.enabled).length || providers.length

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="sidebar-brand-mark">
          <LogoMark />
        </div>
        <div>
          <div className="sidebar-brand-name">Quota Tracker</div>
          <div className="sidebar-brand-sub">{activeProviders} providers active</div>
        </div>
      </div>

      <div className="nav">
        <NavLink
          to="/overview"
          className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
        >
          <span className="nav-item-icon">
            <svg
              width="15"
              height="15"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <rect x="3" y="3" width="7" height="7" rx="1.5" />
              <rect x="14" y="3" width="7" height="7" rx="1.5" />
              <rect x="3" y="14" width="7" height="7" rx="1.5" />
              <rect x="14" y="14" width="7" height="7" rx="1.5" />
            </svg>
          </span>
          <span className="nav-item-label">Overview</span>
        </NavLink>
      </div>

      <div className="sidebar-section">
        <span>Providers</span>
      </div>
      <div className="nav">
        {PROVIDER_IDS.map((id) => {
          let providerQuotas = latest.filter((q) => q.provider_id === id)
          if (id === "claude") providerQuotas = filterClaudeQuotas(providerQuotas)
          else if (id === "copilot") providerQuotas = filterCopilotQuotas(providerQuotas)
          else if (id === "gemini") providerQuotas = rollupGeminiQuotas(providerQuotas)

          const worst =
            providerQuotas.length > 0
              ? Math.max(...providerQuotas.map((q) => q.used_percent ?? 0))
              : 0
          const status = statusFor(worst)
          const isActive = location.pathname === `/provider/${id}`
          return (
            <NavLink
              key={id}
              to={`/provider/${id}`}
              className={`nav-provider${isActive ? " active" : ""}`}
            >
              <span className="nav-provider-logo">
                <img
                  src={PROVIDER_LOGOS[id]}
                  width={18}
                  height={18}
                  alt={PROVIDER_NAMES[id]}
                />
              </span>
              <div className="nav-provider-body">
                <div className="nav-provider-name">
                  <span>{PROVIDER_NAMES[id]}</span>
                  {providerQuotas.length > 0 && (
                    <span
                      className={`nav-provider-pct${status === "crit" ? " crit" : status === "warn" ? " warn" : ""}`}
                    >
                      {worst.toFixed(0)}%
                    </span>
                  )}
                </div>
                {providerQuotas.length > 0 && (
                  <div
                    className={`nav-provider-bar${status === "crit" ? " crit" : status === "warn" ? " warn" : ""}`}
                    style={{ "--w": worst + "%" } as React.CSSProperties}
                  >
                    <i></i>
                  </div>
                )}
              </div>
            </NavLink>
          )
        })}
      </div>

      <div className="sidebar-section" style={{ marginTop: 6 }}>
        <span>Settings</span>
      </div>
      <div className="nav">
        <NavLink
          to="/settings"
          className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
        >
          <span className="nav-item-icon">
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 11-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 11-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 11-2.83-2.83l.06-.06A1.65 1.65 0 004.6 15a1.65 1.65 0 00-1.51-1H3a2 2 0 110-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 112.83-2.83l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 114 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 112.83 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9c.36.45.59 1 .59 1.51" />
            </svg>
          </span>
          <span className="nav-item-label">Settings</span>
        </NavLink>
      </div>

      <div className="sidebar-foot">
        <div className="sidebar-foot-avatar">QT</div>
        <div>
          <div className="sidebar-foot-name">Local Workspace</div>
          <div className="sidebar-foot-sub">Auto-sync enabled</div>
        </div>
        <button
          className="sidebar-foot-action"
          onClick={toggleTheme}
          title={theme === "light" ? "Switch to dark mode" : "Switch to light mode"}
        >
          {theme === "light" ? (
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
            </svg>
          ) : (
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="5"/>
              <line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/>
              <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
              <line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/>
              <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
            </svg>
          )}
        </button>
      </div>
    </aside>
  )
}
