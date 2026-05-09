import { Gauge, LayoutDashboard, Settings } from "lucide-react"
import React from "react"
import { NavLink } from "react-router-dom"
import { useProviders } from "../../contexts/ProvidersContext"
import type { ProviderId } from "../../types"

const providerLabels: Record<ProviderId, string> = {
  gemini: "Gemini",
  codex: "Codex",
  copilot: "Copilot",
}

const providerColors: Record<ProviderId, string> = {
  gemini: "bg-blue-500",
  codex: "bg-emerald-500",
  copilot: "bg-orange-400",
}

const PROVIDER_IDS: ProviderId[] = ["gemini", "codex", "copilot"]

const activeLinkClass =
  "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium bg-slate-700 text-violet-400"
const inactiveLinkClass =
  "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors"

export function Sidebar(): React.JSX.Element {
  const { providers } = useProviders()
  const providerMap = Object.fromEntries(providers.map((p) => [p.id, p])) as Partial<Record<ProviderId, { enabled: boolean }>>

  return (
    <aside className="w-56 shrink-0 h-screen bg-slate-900 border-r border-slate-800 flex flex-col">
      {/* App title */}
      <div className="flex items-center gap-2 px-4 py-5 border-b border-slate-800">
        <Gauge className="h-5 w-5 text-violet-500 shrink-0" />
        <span className="text-sm font-semibold text-slate-100 tracking-wide">Quota Tracker</span>
      </div>

      {/* Navigation */}
      <nav className="flex flex-col gap-1 px-2 pt-4 flex-1 overflow-y-auto">
        <NavLink
          to="/overview"
          className={({ isActive }) => (isActive ? activeLinkClass : inactiveLinkClass)}
        >
          <LayoutDashboard className="h-4 w-4 shrink-0" />
          Overview
        </NavLink>

        <div className="mt-3 mb-1 px-3">
          <span className="text-[10px] font-semibold uppercase tracking-widest text-slate-600">
            Providers
          </span>
        </div>

        {PROVIDER_IDS.map((id) => {
          const p = providerMap[id]
          const enabled = p?.enabled ?? true
          return (
            <NavLink
              key={id}
              to={`/provider/${id}`}
              className={({ isActive }) => (isActive ? activeLinkClass : inactiveLinkClass)}
            >
              <span
                className={`h-2 w-2 rounded-full shrink-0 ${providerColors[id]}`}
                aria-hidden="true"
              />
              {providerLabels[id]}
              <span
                className={`ml-auto h-1.5 w-1.5 rounded-full shrink-0 ${enabled ? "bg-green-500" : "bg-red-500"}`}
                title={enabled ? "Enabled" : "Disabled"}
              />
            </NavLink>
          )
        })}

        <div className="flex-1" />

        <div className="border-t border-slate-800 pt-2 pb-3">
          <NavLink
            to="/settings"
            className={({ isActive }) => (isActive ? activeLinkClass : inactiveLinkClass)}
          >
            <Settings className="h-4 w-4 shrink-0" />
            Settings
          </NavLink>
        </div>
      </nav>
    </aside>
  )
}
