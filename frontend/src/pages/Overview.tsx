import React, { useState } from "react"
import { useNavigate } from "react-router-dom"
import { StackedTokenChart } from "../components/charts/StackedTokenChart"
import { ModelBarChart } from "../components/charts/ModelBarChart"
import { TokenBreakdownPie } from "../components/charts/TokenBreakdownPie"
import { QuotaPanel, rollupGeminiQuotas, filterCopilotQuotas, filterClaudeQuotas, displayLabel } from "../components/ui/QuotaPanel"
import type { Range } from "../hooks/useDashboard"
import { useDashboard } from "../hooks/useDashboard"
import { useProjectUsage } from "../hooks/useProjectUsage"
import { useProviders } from "../contexts/ProvidersContext"
import type { ProviderId, QuotaRow } from "../types"
import { basename, formatLargeNumber, formatCost, formatRelative, latestQuotas } from "../utils"

const PROVIDER_IDS: ProviderId[] = ["gemini", "codex", "copilot", "claude"]

const PROVIDER_NAMES: Record<ProviderId, string> = {
  gemini: "Gemini",
  codex: "Codex",
  copilot: "Copilot",
  claude: "Claude",
}

const PROVIDER_LOGOS: Record<ProviderId, string> = {
  gemini: "/logos/gemini.png",
  codex: "/logos/codex.png",
  copilot: "/logos/copilot.png",
  claude: "/logos/claude-code.png",
}

const PROVIDER_COLOR_VARS: Record<ProviderId, string> = {
  gemini: "var(--gemini)",
  codex: "var(--codex)",
  copilot: "var(--copilot)",
  claude: "var(--claude)",
}

// Hex values for provider colors (for recharts which can't use CSS vars)
const PROVIDER_COLORS_HEX: Record<ProviderId, string> = {
  gemini: "#4F8DF7",
  codex: "#10B981",
  copilot: "#F59E0B",
  claude: "#D97757",
}

const PROJECT_PAGE_SIZE = 5
const SESSION_PAGE_SIZE = 5

function statusFor(pct: number): "crit" | "warn" | "ok" {
  if (pct >= 95) return "crit"
  if (pct >= 70) return "warn"
  return "ok"
}

// === Alert Ribbon ===
interface AlertItem {
  providerId: ProviderId
  quotaName: string
  pct: number
  resetsAt: string | null
}

function AlertRibbon({ latest }: { latest: QuotaRow[] }): React.JSX.Element | null {
  const crit: AlertItem[] = []
  const warn: AlertItem[] = []

  for (const q of latest) {
    const pct = q.used_percent ?? 0
    const item: AlertItem = {
      providerId: q.provider_id,
      quotaName: q.quota_name,
      pct,
      resetsAt: q.resets_at,
    }
    if (pct >= 95) crit.push(item)
    else if (pct >= 70) warn.push(item)
  }

  const total = crit.length + warn.length
  if (total === 0) return null

  const isCrit = crit.length > 0
  const items = isCrit ? crit : warn
  const firstItem = items[0]

  return (
    <div className={`alert-ribbon${isCrit ? "" : " warn"}`}>
      <div className="alert-icon">
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
          <path d="M10.3 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
          <line x1="12" y1="9" x2="12" y2="13" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
      </div>
      <div className="alert-body">
        <div className="alert-title">
          {isCrit
            ? `${crit.length} quota${crit.length > 1 ? "s" : ""} hit · ${warn.length} approaching limit`
            : `${warn.length} quota${warn.length > 1 ? "s" : ""} approaching limit`}
        </div>
        <div className="alert-text">
          {items.slice(0, 3).map((it, i) => (
            <span key={i}>
              {i > 0 && <span className="dim"> · </span>}
              <span
                className="pill"
                style={{ color: PROVIDER_COLOR_VARS[it.providerId] }}
              >
                {PROVIDER_NAMES[it.providerId]}
              </span>
              <span> {displayLabel(it.providerId, it.quotaName)} </span>
              <strong>{it.pct.toFixed(1)}%</strong>
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}

export function Overview(): React.JSX.Element {
  const { range, setRange, quotas: contextQuotas } = useProviders()
  const navigate = useNavigate()

  const [pieProvider, setPieProvider] = useState<string>("all")
  const [chartMode, setChartMode] = useState<"tokens" | "cost">("tokens")
  const [topProjectsProvider, setTopProjectsProvider] = useState<ProviderId | "all">("all")
  const [topProjectsPage, setTopProjectsPage] = useState(0)
  const [sessionsProvider, setSessionsProvider] = useState<ProviderId | "all">("all")
  const [sessionsPage, setSessionsPage] = useState(0)

  const {
    providers,
    quotas,
    sessions,
    timeSeriesByProvider,
    timeSeriesGroupBy,
    modelUsage,
    providerTotals,
    loading,
    refresh,
  } = useDashboard(undefined, range)

  const {
    items: topProjects,
    total: topProjectsTotal,
    loading: topProjectsLoading,
  } = useProjectUsage(range, topProjectsProvider, topProjectsPage, PROJECT_PAGE_SIZE)

  const handleRange = (next: Range) => {
    setRange(next)
    setTopProjectsPage(0)
    setSessionsPage(0)
  }

  // Use context quotas for sidebar mini bars + alert ribbon (always-fresh latest)
  const latestCtx = latestQuotas(contextQuotas)
  // Rolled-up version for alert ribbon (same filtering as quota cards)
  const latestCtxAlert = PROVIDER_IDS.flatMap((id) => {
    const rows = latestCtx.filter((q) => q.provider_id === id)
    if (id === "gemini") return rollupGeminiQuotas(rows)
    if (id === "copilot") return filterCopilotQuotas(rows)
    if (id === "claude") return filterClaudeQuotas(rows)
    return rows
  })
  // Use dashboard quotas for per-provider quota cards
  const latest = latestQuotas(quotas)

  const totalTokens = providerTotals.reduce((s, r) => s + r.total_tokens, 0)
  const totalCost = providerTotals.reduce((s, r) => s + r.estimated_cost, 0)
  const enabledCount = providers.filter((p) => p.enabled).length || providers.length

  // Compute overall worst status for topbar badge
  const worstPct = latestCtxAlert.length > 0 ? Math.max(...latestCtxAlert.map((q) => q.used_percent ?? 0)) : 0
  const worstStatus = statusFor(worstPct)

  const allTimeSeries = [
    ...timeSeriesByProvider.gemini,
    ...timeSeriesByProvider.codex,
    ...timeSeriesByProvider.copilot,
    ...timeSeriesByProvider.claude,
  ]

  const sessionsFiltered =
    sessionsProvider === "all"
      ? sessions
      : sessions.filter((s) => s.provider_id === sessionsProvider)

  const sessionPageCount = Math.ceil(sessionsFiltered.length / SESSION_PAGE_SIZE)
  const pagedSessions = sessionsFiltered.slice(
    sessionsPage * SESSION_PAGE_SIZE,
    (sessionsPage + 1) * SESSION_PAGE_SIZE,
  )

  // Build per-provider visible quotas for quota cards
  const quotasByProvider = PROVIDER_IDS.map((id) => {
    const rows = latest.filter((q) => q.provider_id === id)
    let visible: QuotaRow[]
    if (id === "copilot") visible = filterCopilotQuotas(rows)
    else if (id === "gemini") visible = rollupGeminiQuotas(rows)
    else if (id === "claude") visible = filterClaudeQuotas(rows)
    else visible = rows
    const worst = visible.length > 0 ? Math.max(...visible.map((q) => q.used_percent ?? 0)) : 0
    return { id, visible, worst }
  })

  return (
    <>
      {/* Topbar */}
      <div className="topbar">
        <div className="topbar-crumb">
          <span className="crumb-title">Overview</span>
          {latestCtxAlert.length > 0 && (
            <span className={`crumb-status${worstStatus === "crit" ? " crit" : worstStatus === "warn" ? " warn" : ""}`}>
              <span className="dot" />
              {worstStatus === "crit" ? "Quota hit" : worstStatus === "warn" ? "Approaching" : "Healthy"}
            </span>
          )}
        </div>
        <div className="topbar-spacer" />
        <div className="range-tabs">
          {(["24h", "7d", "30d", "all"] as Range[]).map((r) => (
            <button
              key={r}
              className={`range-tab${range === r ? " active" : ""}`}
              onClick={() => handleRange(r)}
            >
              {r}
            </button>
          ))}
        </div>
        <button className="icon-btn" onClick={refresh}>
          <svg
            width="13"
            height="13"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
            style={loading ? { animation: "spin 1s linear infinite" } : undefined}
          >
            <polyline points="23 4 23 10 17 10" />
            <polyline points="1 20 1 14 7 14" />
            <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" />
          </svg>
          Refresh
        </button>
      </div>

      <div className="page">
        {/* Page head */}
        <div className="page-head">
          <div>
            <div className="page-title">Overview</div>
            <div className="page-sub">All providers · last {range}</div>
          </div>
        </div>

        {/* Alert ribbon */}
        <AlertRibbon latest={latestCtxAlert} />

        {/* KPI grid */}
        <div className="kpi-grid">
          {/* Active providers */}
          <div className="kpi">
            <div className="kpi-label">
              <span className="kpi-label-icon">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 3l9 5-9 5-9-5 9-5z"/><path d="M3 13l9 5 9-5"/><path d="M3 18l9 5 9-5"/>
                </svg>
              </span>
              Active providers
            </div>
            <div className="kpi-value">
              <span>{enabledCount}</span>
              <span className="kpi-unit">/ {Math.max(enabledCount, providers.length)}</span>
            </div>
            <div className="kpi-foot">
              <span>all enabled</span>
            </div>
          </div>

          {/* Sessions */}
          <div className="kpi">
            <div className="kpi-label">
              <span className="kpi-label-icon">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M22 12h-4l-3 9-6-18-3 9H2"/>
                </svg>
              </span>
              Sessions
            </div>
            <div className="kpi-value">
              <span>{sessions.length}</span>
            </div>
            <div className="kpi-foot">
              <span>in {range}</span>
            </div>
          </div>

          {/* Tokens (Combined) */}
          <div className="kpi" style={{ gridColumn: "span 2" }}>
            <div className="kpi-label">
              <span className="kpi-label-icon">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M13 2L3 14h7l-1 8 11-14h-8l1-6z"/>
                </svg>
              </span>
              Tokens
            </div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 16, marginTop: 6 }}>
              <div className="kpi-value" style={{ marginTop: 0 }}>
                <span>{formatLargeNumber(totalTokens)}</span>
              </div>
              {totalCost > 0 && (
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span className="tabular" style={{ fontSize: 24, fontWeight: 600, color: "var(--ok)", letterSpacing: "-0.02em" }}>
                    ~{formatCost(totalCost)}
                  </span>
                  <span className="info-tooltip-trigger" style={{ color: "var(--fg-3)", cursor: "help", display: "grid", placeItems: "center" }}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>
                    </svg>
                    <span className="info-tooltip-bubble">Estimated token cost, not necessarily what you actually paid.</span>
                  </span>
                </div>
              )}
            </div>
            <div className="kpi-foot" style={{ marginBottom: 12 }}>
              <span>{range} · all providers</span>
            </div>
            <div className="kpi-providers">
              {PROVIDER_IDS.map((id) => {
                const row = providerTotals.find((p) => p.bucket === id)
                const value = row?.total_tokens ?? 0
                const pct = totalTokens > 0 ? (value / totalTokens) * 100 : 0
                return (
                  <div
                    key={id}
                    className="kpi-providers-row"
                    style={{ ["--c" as string]: PROVIDER_COLOR_VARS[id], ["--w" as string]: pct + "%" }}
                  >
                    <span className="dot"></span>
                    <span className="name">{PROVIDER_NAMES[id]}</span>
                    <span className="bar"><i></i></span>
                    <span className="v" style={{ display: "flex", alignItems: "center", gap: 6, justifyContent: "flex-end" }}>
                      <span>{formatLargeNumber(value)}</span>
                      {row && row.estimated_cost > 0 && (
                        <span style={{ color: "var(--ok)" }}>(~{formatCost(row.estimated_cost)})</span>
                      )}
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
        </div>

        {/* Quotas section */}
        <div>
          <div className="section-row" style={{ marginBottom: 12 }}>
            <div className="section-title">Quotas — am I about to hit a wall?</div>
            <div className="section-rule"></div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
            {quotasByProvider
              .filter(({ visible }) => visible.length > 0)
              .map(({ id, visible, worst }) => {
                const cardStatus = statusFor(worst)
                const color = PROVIDER_COLOR_VARS[id]
                return (
                  <div
                    key={id}
                    className={`quota-card${cardStatus === "crit" ? " crit" : cardStatus === "warn" ? " warn" : ""}`}
                    style={{ ["--c" as string]: color, ["--c-soft" as string]: `${PROVIDER_COLORS_HEX[id]}22` }}
                  >
                    <div className="quota-card-head">
                      <div
                        className="quota-card-mark"
                        style={{ background: `${PROVIDER_COLORS_HEX[id]}18` }}
                      >
                        <img
                          src={PROVIDER_LOGOS[id]}
                          width={28}
                          height={28}
                          alt={PROVIDER_NAMES[id]}
                        />
                      </div>
                      <div>
                        <div className="quota-card-name">{PROVIDER_NAMES[id]}</div>
                        <div className="quota-card-sub">{visible.length} quota{visible.length > 1 ? "s" : ""}</div>
                      </div>
                      <button
                        className="quota-card-link"
                        onClick={() => navigate(`/provider/${id}`)}
                      >
                        Open
                        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                          <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>
                        </svg>
                      </button>
                    </div>
                    <QuotaPanel
                      providerId={id}
                      latest={latest.filter((q) => q.provider_id === id)}
                      providerColor={color}
                    />
                  </div>
                )
              })}
            {quotasByProvider.every(({ visible }) => visible.length === 0) && (
              <div style={{ color: "var(--fg-3)", fontSize: 13, gridColumn: "1 / -1", padding: "24px 0" }}>
                No quota data. Run a sync or wait for the next automatic sync.
              </div>
            )}
          </div>
        </div>

        {/* Tokens over time + Token types */}
        <div className="grid-2">
          <div className="card">
            <div className="card-head">
              <span className="card-title">Tokens over time</span>
              <span className="card-sub">by provider · {timeSeriesGroupBy}</span>
              <div className="card-actions">
                <div className="range-tabs" style={{ padding: 1 }}>
                  <button
                    className={`range-tab${chartMode === "tokens" ? " active" : ""}`}
                    onClick={() => setChartMode("tokens")}
                    style={{ padding: "3px 8px", fontSize: 12 }}
                  >
                    Tokens
                  </button>
                  <button
                    className={`range-tab${chartMode === "cost" ? " active" : ""}`}
                    onClick={() => setChartMode("cost")}
                    style={{ padding: "3px 8px", fontSize: 12 }}
                  >
                    Cost
                  </button>
                </div>
              </div>
            </div>
            <div className="card-body">
              <StackedTokenChart byProvider={timeSeriesByProvider} mode="provider" displayMode={chartMode} />
            </div>
          </div>
          <div className="card">
            <div className="card-head">
              <span className="card-title">Token types</span>
              <div className="card-actions">
                <select
                  className="select"
                  value={pieProvider}
                  onChange={(e) => setPieProvider(e.target.value)}
                >
                  <option value="all">All providers</option>
                  {PROVIDER_IDS.map((id) => (
                    <option key={id} value={id}>
                      {PROVIDER_NAMES[id]}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="card-body">
              <TokenBreakdownPie
                rows={
                  pieProvider === "all"
                    ? allTimeSeries
                    : timeSeriesByProvider[pieProvider as ProviderId]
                }
              />
            </div>
          </div>
        </div>

        {/* Top models */}
        <div className="card">
          <div className="card-head">
            <span className="card-title">Top models</span>
            <span className="card-sub">{range} · across providers</span>
          </div>
          <div className="card-body">
            <ModelBarChart data={modelUsage} />
          </div>
        </div>

        {/* Top projects + Provider status (2-col grid) */}
        <div className="grid-2">
          {/* Top projects */}
          <div className="card">
            <div className="card-head">
              <span className="card-title">Top projects</span>
              {topProjectsTotal > 0 && (
                <span className="card-sub">{topProjectsTotal} total</span>
              )}
              <div className="card-actions">
                <select
                  className="select"
                  value={topProjectsProvider}
                  onChange={(e) => {
                    setTopProjectsProvider(e.target.value as ProviderId | "all")
                    setTopProjectsPage(0)
                  }}
                >
                  <option value="all">All providers</option>
                  {PROVIDER_IDS.map((id) => (
                    <option key={id} value={id}>
                      {PROVIDER_NAMES[id]}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            {topProjectsLoading ? (
              <div style={{ padding: "24px 20px", color: "var(--fg-3)", fontSize: 13 }}>Loading…</div>
            ) : topProjectsTotal === 0 ? (
              <div style={{ padding: "24px 20px", color: "var(--fg-3)", fontSize: 13 }}>
                No projects in selected range
              </div>
            ) : (
              <>
                <table className="table">
                  <thead>
                    <tr>
                      <th>Project</th>
                      <th className="num">Sessions</th>
                      <th className="num">Tokens</th>
                      <th className="num">Share</th>
                    </tr>
                  </thead>
                  <tbody>
                    {topProjects.map((p, i) => {
                      const name = p.project_name ?? basename(p.project_path) ?? "unknown"
                      const totalProjTokens = topProjectsProvider === "all" ? totalTokens : providerTotals.find(t => t.bucket === topProjectsProvider)?.total_tokens ?? 0
                      const pct = totalProjTokens > 0 ? (p.total_tokens / totalProjTokens) * 100 : 0
                      return (
                        <tr key={i}>
                          <td>
                            <div
                              style={{ fontWeight: 500, color: "var(--fg-1)", maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                              title={p.project_path ?? undefined}
                            >
                              {name}
                            </div>
                          </td>
                          <td className="num">{p.session_count}</td>
                          <td className="num">{formatLargeNumber(p.total_tokens)}</td>
                          <td className="num">
                            <div style={{ display: "flex", alignItems: "center", gap: 8, justifyContent: "flex-end" }}>
                              <div
                                className="row-bar"
                                style={{ ["--w" as string]: pct + "%", ["--c" as string]: "var(--accent)" }}
                              >
                                <i></i>
                              </div>
                              <span style={{ minWidth: 36 }}>{pct.toFixed(0)}%</span>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
                <div className="pager">
                  <button
                    className="pager-btn"
                    disabled={topProjectsPage === 0}
                    onClick={() => setTopProjectsPage(topProjectsPage - 1)}
                  >
                    Prev
                  </button>
                  <span>
                    Page {topProjectsPage + 1} of {Math.max(1, Math.ceil(topProjectsTotal / PROJECT_PAGE_SIZE))}
                  </span>
                  <button
                    className="pager-btn"
                    disabled={(topProjectsPage + 1) * PROJECT_PAGE_SIZE >= topProjectsTotal}
                    onClick={() => setTopProjectsPage(topProjectsPage + 1)}
                  >
                    Next
                  </button>
                </div>
              </>
            )}
          </div>

          {/* Provider status */}
          <div className="card">
            <div className="card-head">
              <span className="card-title">Provider status</span>
            </div>
            <div className="card-body" style={{ padding: 0 }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>Provider</th>
                    <th>Status</th>
                    <th className="num">Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {providers.map((p) => {
                    const pQuotas = latest.filter((q) => q.provider_id === p.id)
                    const worst = pQuotas.length > 0
                      ? Math.max(...pQuotas.map((q) => q.used_percent ?? 0))
                      : 0
                    const status = statusFor(worst)
                    const color = PROVIDER_COLOR_VARS[p.id]
                    return (
                      <tr
                        key={p.id}
                        style={{ cursor: "pointer" }}
                        onClick={() => navigate(`/provider/${p.id}`)}
                      >
                        <td>
                          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                            <span
                              style={{
                                width: 6,
                                height: 6,
                                borderRadius: 99,
                                background: color,
                                boxShadow: `0 0 0 3px color-mix(in oklab, ${color} 18%, transparent)`,
                                flexShrink: 0,
                              }}
                            ></span>
                            <span style={{ color: "var(--fg-1)", fontWeight: 500 }}>
                              {PROVIDER_NAMES[p.id]}
                            </span>
                          </div>
                        </td>
                        <td>
                          <span
                            className={`tag${status === "crit" ? " crit" : status === "warn" ? " warn" : " ok"}`}
                          >
                            {status === "crit"
                              ? "Quota hit"
                              : status === "warn"
                                ? "Approaching"
                                : "Healthy"}
                          </span>
                        </td>
                        <td className="num dim">{formatRelative(p.updated_at)}</td>
                      </tr>
                    )
                  })}
                  {providers.length === 0 && (
                    <tr>
                      <td
                        colSpan={3}
                        style={{ textAlign: "center", color: "var(--fg-3)", padding: 24 }}
                      >
                        No providers
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Recent sessions */}
        <div className="card">
          <div className="card-head">
            <span className="card-title">Recent sessions</span>
            <span className="card-sub">
              {sessionsFiltered.length} total
            </span>
            <div className="card-actions">
              <select
                className="select"
                value={sessionsProvider}
                onChange={(e) => {
                  setSessionsProvider(e.target.value as ProviderId | "all")
                  setSessionsPage(0)
                }}
              >
                <option value="all">All providers</option>
                {PROVIDER_IDS.map((id) => (
                  <option key={id} value={id}>
                    {PROVIDER_NAMES[id]}
                  </option>
                ))}
              </select>
            </div>
          </div>
          {sessionsFiltered.length === 0 ? (
            <div style={{ padding: "24px 20px", color: "var(--fg-3)", fontSize: 13, textAlign: "center" }}>
              No sessions in selected range
            </div>
          ) : (
            <>
              <table className="table">
                <thead>
                  <tr>
                    <th>Provider</th>
                    <th>Project</th>
                    <th>Model</th>
                    <th className="num">Last seen</th>
                  </tr>
                </thead>
                <tbody>
                  {pagedSessions.map((s) => (
                    <tr key={s.id}>
                      <td>
                        <span className={`tag ${s.provider_id}`}>
                          {PROVIDER_NAMES[s.provider_id]}
                        </span>
                      </td>
                      <td style={{ color: "var(--fg-1)" }}>
                        <div
                          style={{ maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                          title={s.project_path ?? undefined}
                        >
                          {s.project_name ?? basename(s.project_path) ?? (
                            <span style={{ color: "var(--fg-4)" }}>unknown</span>
                          )}
                        </div>
                      </td>
                      <td className="mono dim">{s.model_name}</td>
                      <td className="num dim">{formatRelative(s.last_seen_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="pager">
                <button
                  className="pager-btn"
                  disabled={sessionsPage === 0}
                  onClick={() => setSessionsPage((p) => p - 1)}
                >
                  Prev
                </button>
                <span>
                  Page {sessionsPage + 1} of {Math.max(1, sessionPageCount)}
                </span>
                <button
                  className="pager-btn"
                  disabled={sessionsPage >= sessionPageCount - 1}
                  onClick={() => setSessionsPage((p) => p + 1)}
                >
                  Next
                </button>
                <div className="pager-spacer"></div>
                <span className="dim">
                  {sessionsFiltered.length} sessions · {range}
                </span>
              </div>
            </>
          )}
        </div>
      </div>

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </>
  )
}
