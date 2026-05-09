import React, { useState } from "react"
import { Link, useParams } from "react-router-dom"
import { ModelBarChart } from "../components/charts/ModelBarChart"
import { QuotaHistoryChart } from "../components/charts/QuotaHistoryChart"
import { StackedTokenChart } from "../components/charts/StackedTokenChart"
import { TokenBreakdownPie } from "../components/charts/TokenBreakdownPie"
import { QuotaPanel, rollupGeminiQuotas, filterCopilotQuotas, filterClaudeQuotas, displayLabel } from "../components/ui/QuotaPanel"
import type { Range } from "../hooks/useDashboard"
import { useDashboard } from "../hooks/useDashboard"
import { useProviders } from "../contexts/ProvidersContext"
import type { ProviderId } from "../types"
import { basename, formatDate, formatLargeNumber, formatRelative, latestQuotas } from "../utils"

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

const PROVIDER_COLORS_HEX: Record<ProviderId, string> = {
  gemini: "#4F8DF7",
  codex: "#10B981",
  copilot: "#F59E0B",
  claude: "#D97757",
}

const VALID_PROVIDERS: ProviderId[] = ["gemini", "codex", "copilot", "claude"]
const SESSION_PAGE_SIZE = 10

function statusFor(pct: number): "crit" | "warn" | "ok" {
  if (pct >= 95) return "crit"
  if (pct >= 70) return "warn"
  return "ok"
}

export function ProviderDetail(): React.JSX.Element {
  const { id } = useParams<{ id: string }>()
  const { range, setRange } = useProviders()
  const [sessionPage, setSessionPage] = useState(0)
  const [selectedModel, setSelectedModel] = useState<string>("all")

  const providerId: ProviderId | null = VALID_PROVIDERS.includes(id as ProviderId)
    ? (id as ProviderId)
    : null

  const handleRange = (next: Range) => {
    setRange(next)
    setSessionPage(0)
  }

  const {
    providers,
    quotas,
    quotaHistory,
    sessions,
    timeSeries,
    timeSeriesGroupBy,
    modelUsage,
    projectUsage,
    projectUsageTotal,
    projectPage,
    projectPageSize,
    setProjectPage,
    loading,
    refresh,
  } = useDashboard(providerId ?? undefined, range, selectedModel)

  if (!providerId) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "60vh" }}>
        <div style={{ textAlign: "center", color: "var(--fg-3)" }}>
          <p style={{ fontSize: 18, fontWeight: 600, marginBottom: 8 }}>Unknown provider</p>
          <p style={{ fontSize: 14 }}>{id}</p>
        </div>
      </div>
    )
  }

  const providerColor = PROVIDER_COLOR_VARS[providerId]
  const providerColorHex = PROVIDER_COLORS_HEX[providerId]
  const provider = providers.find((p) => p.id === providerId)
  const latest = latestQuotas(quotas).filter((q) => q.provider_id === providerId)
  const visibleLatest =
    providerId === "claude"
      ? filterClaudeQuotas(latest)
      : providerId === "copilot"
        ? filterCopilotQuotas(latest)
        : providerId === "gemini"
          ? rollupGeminiQuotas(latest)
          : latest
  const totalTokens = timeSeries.reduce((s, r) => s + r.total_tokens, 0)

  let historyRows = quotaHistory.filter((q) => q.provider_id === providerId)
  if (providerId === "gemini") {
    const byTs = new Map<string, typeof historyRows>()
    for (const r of historyRows) {
      if (!byTs.has(r.timestamp)) byTs.set(r.timestamp, [])
      byTs.get(r.timestamp)!.push(r)
    }
    historyRows = []
    for (const group of byTs.values()) {
      historyRows.push(...rollupGeminiQuotas(group))
    }
  }

  if (providerId === "claude") {
    historyRows = historyRows.filter((r) => r.quota_name !== "extra_usage")
  }

  historyRows = historyRows.map((r) => ({
    ...r,
    quota_name: displayLabel(r.provider_id, r.quota_name),
  }))

  const sessionPageCount = Math.ceil(sessions.length / SESSION_PAGE_SIZE)
  const pagedSessions = sessions.slice(
    sessionPage * SESSION_PAGE_SIZE,
    (sessionPage + 1) * SESSION_PAGE_SIZE,
  )

  // Compute worst quota pct for status badge
  const worstPct = visibleLatest.length > 0 ? Math.max(...visibleLatest.map((q) => q.used_percent ?? 0)) : 0
  const worstStatus = statusFor(worstPct)
  const statusLabel =
    worstStatus === "crit" ? "Quota hit" : worstStatus === "warn" ? "Approaching limit" : "Healthy"

  return (
    <>
      {/* Topbar */}
      <div className="topbar">
        <div className="topbar-crumb">
          <Link to="/overview" className="crumb-pill">
            <svg
              width="12"
              height="12"
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
            Overview
          </Link>
          <span className="crumb-sep">/</span>
          <span className="crumb-title" style={{ color: providerColor }}>
            {PROVIDER_NAMES[providerId]}
          </span>
          <span
            className={`crumb-status${worstStatus === "crit" ? " crit" : worstStatus === "warn" ? " warn" : ""}`}
          >
            <span className="dot" />
            {statusLabel}
          </span>
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
        {/* Provider page head */}
        <div className="provider-page-head" style={{ ["--c" as string]: providerColor }}>
          <div
            className="provider-page-mark"
            style={{ background: `${providerColorHex}18` }}
          >
            <img
              src={PROVIDER_LOGOS[providerId]}
              alt={PROVIDER_NAMES[providerId]}
              style={{ width: 52, height: 52, objectFit: "contain" }}
            />
          </div>
          <div>
            <div className="provider-page-title">
              <span style={{ color: providerColor }}>{PROVIDER_NAMES[providerId]}</span>
              <span
                className={`crumb-status${worstStatus === "crit" ? " crit" : worstStatus === "warn" ? " warn" : ""}`}
              >
                <span className="dot"></span>
                {statusLabel}
              </span>
            </div>
            <div className="provider-page-sub">
              {provider && (
                <>
                  <span>Updated {formatRelative(provider.updated_at)}</span>
                  <span className="dim">·</span>
                </>
              )}
              <span>{visibleLatest.length} quota{visibleLatest.length !== 1 ? "s" : ""}</span>
              <span className="dim">·</span>
              <span>{[...new Set(modelUsage.map((u) => u.bucket))].length} models</span>
            </div>
          </div>
          <div className="provider-page-meta">
            <div className="meta-stat">
              <span className="meta-stat-label">Tokens · {range}</span>
              <span className="meta-stat-value">{formatLargeNumber(totalTokens)}</span>
            </div>
            <div className="meta-stat">
              <span className="meta-stat-label">Sessions · {range}</span>
              <span className="meta-stat-value">{sessions.length}</span>
            </div>
            <div className="meta-stat">
              <span className="meta-stat-label">Models · {range}</span>
              <span className="meta-stat-value">{[...new Set(modelUsage.map((u) => u.bucket))].length}</span>
            </div>
          </div>
        </div>

        {/* Hero: quotas (big meters) + KPI stats */}
        <div className="hero-provider">
          <div className="hero-quota" style={{ ["--c" as string]: providerColor }}>
            <div className="hero-quota-head">
              <span className="hero-quota-title">Quotas</span>
              <span className="hero-quota-sub">live · resets in local time</span>
            </div>
            <div className="hero-meters">
              {visibleLatest.length === 0 ? (
                <p style={{ color: "var(--fg-3)", fontSize: 13 }}>No quota data</p>
              ) : (
                visibleLatest.map((q) => {
                  const pct = q.used_percent ?? 0
                  const st = statusFor(pct)
                  const label = displayLabel(providerId, q.quota_name)
                  return (
                    <div key={q.quota_name} className="hero-meter">
                      <div className="hero-meter-head">
                        <span className="hero-meter-name">{label}</span>
                        <span
                          className={`hero-meter-pct${st === "crit" ? " crit" : st === "warn" ? " warn" : ""}`}
                        >
                          {pct.toFixed(1)}%
                        </span>
                      </div>
                      <div
                        className={`qbar${st === "crit" ? " crit" : st === "warn" ? " warn" : ""}`}
                        style={{
                          ["--w" as string]: pct + "%",
                          ["--c" as string]: providerColor,
                        } as React.CSSProperties}
                      >
                        <i></i>
                      </div>
                      <div className="hero-meter-foot">
                        <span>used</span>
                        {q.resets_at && <span>resets {formatDate(q.resets_at)}</span>}
                      </div>
                    </div>
                  )
                })
              )}
            </div>
          </div>
          <div className="hero-stats">
            <div className="kpi">
              <div className="kpi-label">
                <span className="kpi-label-icon">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M13 2L3 14h7l-1 8 11-14h-8l1-6z"/>
                  </svg>
                </span>
                Tokens
              </div>
              <div className="kpi-value">
                <span>{formatLargeNumber(totalTokens)}</span>
              </div>
              <div className="kpi-foot">
                <span>in {range}</span>
              </div>
            </div>
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
          </div>
        </div>

        {/* Quotas over time */}
        <div className="card">
          <div className="card-head">
            <span className="card-title">Quotas over time</span>
            <span className="card-sub">used %</span>
          </div>
          <div className="card-body">
            <QuotaHistoryChart rows={historyRows} />
          </div>
        </div>

        {/* Tokens over time (kind mode) */}
        <div className="card">
          <div className="card-head">
            <span className="card-title">Tokens over time</span>
            <span className="card-sub">by kind · {timeSeriesGroupBy}</span>
            <div className="card-actions">
              <select
                className="select"
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
              >
                <option value="all">All models</option>
                {[...new Set(modelUsage.map((u) => u.bucket))].sort().map((model) => (
                  <option key={model} value={model}>
                    {model}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="card-body">
            <StackedTokenChart rows={timeSeries} mode="kind" />
          </div>
        </div>

        {/* Token types donut + Tokens by model (2-col) */}
        <div className="grid-2eq">
          <div className="card">
            <div className="card-head">
              <span className="card-title">Token types</span>
            </div>
            <div className="card-body">
              <TokenBreakdownPie rows={timeSeries} />
            </div>
          </div>
          <div className="card">
            <div className="card-head">
              <span className="card-title">Tokens by model</span>
            </div>
            <div className="card-body">
              <ModelBarChart data={modelUsage} singleColor={providerColorHex} />
            </div>
          </div>
        </div>

        {/* Top projects */}
        {projectUsageTotal > 0 && (
          <div className="card">
            <div className="card-head">
              <span className="card-title">Top projects</span>
              <span className="card-sub">{projectUsageTotal} total</span>
            </div>
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
                {projectUsage.map((p, i) => {
                  const name = p.project_name ?? basename(p.project_path) ?? "unknown"
                  const totalProjTokens = projectUsage.reduce((s, x) => s + x.total_tokens, 0)
                  const pct = totalProjTokens > 0 ? (p.total_tokens / totalProjTokens) * 100 : 0
                  return (
                    <tr key={i}>
                      <td
                        style={{ color: "var(--fg-1)", fontWeight: 500 }}
                        title={p.project_path ?? undefined}
                      >
                        {name}
                      </td>
                      <td className="num">{p.session_count}</td>
                      <td className="num">{formatLargeNumber(p.total_tokens)}</td>
                      <td className="num">
                        <div style={{ display: "flex", alignItems: "center", gap: 8, justifyContent: "flex-end" }}>
                          <div
                            className="row-bar"
                            style={{
                              ["--w" as string]: pct + "%",
                              ["--c" as string]: providerColor,
                            }}
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
                disabled={projectPage === 0}
                onClick={() => setProjectPage(projectPage - 1)}
              >
                Prev
              </button>
              <span>Page {projectPage + 1}</span>
              <button
                className="pager-btn"
                disabled={(projectPage + 1) * projectPageSize >= projectUsageTotal}
                onClick={() => setProjectPage(projectPage + 1)}
              >
                Next
              </button>
            </div>
          </div>
        )}

        {/* Sessions */}
        <div className="card">
          <div className="card-head">
            <span className="card-title">Sessions</span>
            <span className="card-sub">
              Page {sessionPage + 1} of {Math.max(1, sessionPageCount)} · {sessions.length} sessions
            </span>
          </div>
          {sessions.length === 0 ? (
            <div style={{ padding: "24px 20px", textAlign: "center", color: "var(--fg-3)", fontSize: 13 }}>
              No sessions for {PROVIDER_NAMES[providerId]} in this range
            </div>
          ) : (
            <>
              <table className="table">
                <thead>
                  <tr>
                    <th>Project</th>
                    <th>Model</th>
                    <th>Created</th>
                    <th className="num">Last seen</th>
                  </tr>
                </thead>
                <tbody>
                  {pagedSessions.map((s) => (
                    <tr key={s.id}>
                      <td
                        style={{ color: "var(--fg-1)", fontWeight: 500, maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                        title={s.project_path ?? undefined}
                      >
                        {s.project_name ?? basename(s.project_path) ?? (
                          <span style={{ color: "var(--fg-4)" }}>unknown</span>
                        )}
                      </td>
                      <td className="mono dim">{s.model_name}</td>
                      <td className="dim">{formatDate(s.created_at)}</td>
                      <td className="num dim">{formatRelative(s.last_seen_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {sessionPageCount > 1 && (
                <div className="pager">
                  <button
                    className="pager-btn"
                    disabled={sessionPage === 0}
                    onClick={() => setSessionPage((p) => p - 1)}
                  >
                    Prev
                  </button>
                  <span>Page {sessionPage + 1} of {sessionPageCount}</span>
                  <button
                    className="pager-btn"
                    disabled={sessionPage >= sessionPageCount - 1}
                    onClick={() => setSessionPage((p) => p + 1)}
                  >
                    Next
                  </button>
                </div>
              )}
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
