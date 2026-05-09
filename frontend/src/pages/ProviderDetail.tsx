import { Activity, AlertCircle, RefreshCw, Zap } from "lucide-react"
import React, { useState } from "react"
import { useParams } from "react-router-dom"
import { ModelBarChart } from "../components/charts/ModelBarChart"
import { QuotaHistoryChart } from "../components/charts/QuotaHistoryChart"
import { StackedTokenChart } from "../components/charts/StackedTokenChart"
import { TokenBreakdownPie } from "../components/charts/TokenBreakdownPie"
import { Badge } from "../components/ui/Badge"
import { Button } from "../components/ui/Button"
import { Card } from "../components/ui/Card"
import { MetricCard } from "../components/ui/MetricCard"
import { QuotaPanel, rollupGeminiQuotas, displayLabel } from "../components/ui/QuotaPanel"
import { RangePicker } from "../components/ui/RangePicker"
import { Spinner } from "../components/ui/Spinner"
import type { Range } from "../hooks/useDashboard"
import { useDashboard } from "../hooks/useDashboard"
import type { ProviderId } from "../types"
import { basename, formatDate, formatLargeNumber, formatRelative, latestQuotas } from "../utils"

const providerLabels: Record<ProviderId, string> = {
  gemini: "Gemini",
  codex: "Codex",
  copilot: "Copilot",
}

const providerColors: Record<ProviderId, string> = {
  gemini: "text-blue-400",
  codex: "text-emerald-400",
  copilot: "text-orange-400",
}

const VALID_PROVIDERS: ProviderId[] = ["gemini", "codex", "copilot"]

const SESSION_PAGE_SIZE = 10

export function ProviderDetail(): React.JSX.Element {
  const { id } = useParams<{ id: string }>()
  const [range, setRange] = useState<Range>("7d")
  // Client-side session paging
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
    modelUsage,
    projectUsage,
    projectUsageTotal,
    projectPage,
    projectPageSize,
    setProjectPage,
    loading,
    error,
    refresh,
  } = useDashboard(providerId ?? undefined, range, selectedModel)

  if (!providerId) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="flex flex-col items-center gap-2 text-slate-400">
          <AlertCircle className="h-8 w-8" />
          <p>Unknown provider: {id}</p>
        </div>
      </div>
    )
  }

  const provider = providers.find((p) => p.id === providerId)
  const latest = latestQuotas(quotas).filter((q) => q.provider_id === providerId)
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
  
  historyRows = historyRows.map(r => ({
    ...r,
    quota_name: displayLabel(r.provider_id, r.quota_name)
  }))

  // Session paging
  const sessionPageCount = Math.ceil(sessions.length / SESSION_PAGE_SIZE)
  const pagedSessions = sessions.slice(
    sessionPage * SESSION_PAGE_SIZE,
    (sessionPage + 1) * SESSION_PAGE_SIZE,
  )

  return (
    <div className="flex flex-col gap-6 p-6 min-h-0 overflow-y-auto">
      {/* Header */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h1 className={`text-xl font-semibold ${providerColors[providerId]}`}>
            {providerLabels[providerId]}
          </h1>
          <div className="flex items-center gap-2 mt-1">
            {provider && (
              <Badge variant={provider.enabled ? "success" : "error"}>
                {provider.enabled ? "Enabled" : "Disabled"}
              </Badge>
            )}
            {provider && (
              <span className="text-xs text-slate-500">
                Updated {formatRelative(provider.updated_at)}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <RangePicker
            range={range}
            onRangeChange={handleRange}
          />
          <Button variant="ghost" size="sm" loading={loading} onClick={refresh}>
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </Button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-700/40 bg-red-900/20 px-4 py-3 text-sm text-red-400">
          {error}
        </div>
      )}

      {loading && !providers.length && (
        <div className="flex items-center justify-center py-20">
          <Spinner size="lg" />
        </div>
      )}

      {/* Row 1: Quotas · Tokens · Sessions */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card>
          <h2 className="text-sm font-semibold text-slate-300 mb-3">Quotas</h2>
          <QuotaPanel
            providerId={providerId}
            latest={latest}
          />
        </Card>
        <MetricCard
          label="Tokens"
          value={formatLargeNumber(totalTokens)}
          sub={`in range (${range})`}
          icon={<Zap className="h-5 w-5" />}
        />
        <MetricCard
          label="Sessions"
          value={sessions.length}
          icon={<Activity className="h-5 w-5" />}
        />
      </div>

      {/* Row 2a: Quotas over time (full width) */}
      <Card>
        <h2 className="text-sm font-semibold text-slate-300 mb-3">
          Quotas over time
          <span className="ml-2 text-xs font-normal text-slate-500">used %</span>
        </h2>
        <QuotaHistoryChart rows={historyRows} />
      </Card>

      {/* Row 2b: Tokens over time (full width) */}
      <Card>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-slate-300">
            Tokens over time
            <span className="ml-2 text-xs font-normal text-slate-500">by kind · hour</span>
          </h2>
          <select
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
            className="text-xs bg-slate-800 border border-slate-700 text-slate-300 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-violet-500 focus:border-violet-500"
          >
            <option value="all">All models</option>
            {[...new Set(modelUsage.map((u) => u.bucket))].sort().map((model) => (
              <option key={model} value={model}>
                {model}
              </option>
            ))}
          </select>
        </div>
        <StackedTokenChart rows={timeSeries} mode="kind" />
      </Card>

      {/* Row 3: Pie breakdown + Tokens by model */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <h2 className="text-sm font-semibold text-slate-300 mb-3">Token types</h2>
          <TokenBreakdownPie rows={timeSeries} />
        </Card>
        <Card>
          <h2 className="text-sm font-semibold text-slate-300 mb-3">Tokens by model</h2>
          <ModelBarChart data={modelUsage} />
        </Card>
      </div>

      {/* Row 4: Top projects with paging */}
      {projectUsageTotal > 0 && (
        <Card>
          <h2 className="text-sm font-semibold text-slate-300 mb-3">
            Top projects
            <span className="ml-2 text-xs font-normal text-slate-500">
              ({projectUsageTotal} total)
            </span>
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700">
                  <th className="text-left py-2 px-3 text-xs font-medium text-slate-400">Project</th>
                  <th className="text-left py-2 px-3 text-xs font-medium text-slate-400">Sessions</th>
                  <th className="text-left py-2 px-3 text-xs font-medium text-slate-400">Tokens</th>
                </tr>
              </thead>
              <tbody>
                {projectUsage.map((p, i) => {
                  const name =
                    p.project_name ?? basename(p.project_path) ?? "unknown"
                  return (
                    <tr
                      key={i}
                      className="border-b border-slate-800 hover:bg-slate-800/40 transition-colors"
                    >
                      <td
                        className="py-2.5 px-3 text-slate-300 max-w-[220px] truncate"
                        title={p.project_path ?? undefined}
                      >
                        {name}
                      </td>
                      <td className="py-2.5 px-3 text-slate-400">{p.session_count}</td>
                      <td className="py-2.5 px-3 text-slate-400 font-mono text-xs">
                        {formatLargeNumber(p.total_tokens)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <div className="flex items-center gap-3 mt-3">
            <Button
              variant="ghost"
              size="sm"
              disabled={projectPage === 0}
              onClick={() => setProjectPage(projectPage - 1)}
            >
              Prev
            </Button>
            <span className="text-xs text-slate-500">Page {projectPage + 1}</span>
            <Button
              variant="ghost"
              size="sm"
              disabled={(projectPage + 1) * projectPageSize >= projectUsageTotal}
              onClick={() => setProjectPage(projectPage + 1)}
            >
              Next
            </Button>
          </div>
        </Card>
      )}

      {/* Row 5: Sessions with client-side paging */}
      <Card>
        <h2 className="text-sm font-semibold text-slate-300 mb-3">
          Sessions
          <span className="ml-2 text-xs font-normal text-slate-500">
            Page {sessionPage + 1} of {Math.max(1, sessionPageCount)} · {sessions.length} sessions
          </span>
        </h2>
        {sessions.length === 0 ? (
          <p className="text-sm text-slate-500 py-4 text-center">No sessions in selected range</p>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700">
                    <th className="text-left py-2 px-3 text-xs font-medium text-slate-400">Project</th>
                    <th className="text-left py-2 px-3 text-xs font-medium text-slate-400">Model</th>
                    <th className="text-left py-2 px-3 text-xs font-medium text-slate-400">Created</th>
                    <th className="text-left py-2 px-3 text-xs font-medium text-slate-400">Last seen</th>
                  </tr>
                </thead>
                <tbody>
                  {pagedSessions.map((s) => (
                    <tr
                      key={s.id}
                      className="border-b border-slate-800 hover:bg-slate-800/40 transition-colors"
                    >
                      <td
                        className="py-2.5 px-3 text-slate-300 max-w-[180px] truncate"
                        title={s.project_path ?? undefined}
                      >
                        {s.project_name ?? basename(s.project_path) ?? (
                          <span className="text-slate-600">unknown</span>
                        )}
                      </td>
                      <td className="py-2.5 px-3 text-slate-400 font-mono text-xs">
                        {s.model_name}
                      </td>
                      <td className="py-2.5 px-3 text-slate-500">{formatDate(s.created_at)}</td>
                      <td className="py-2.5 px-3 text-slate-500">{formatRelative(s.last_seen_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {sessionPageCount > 1 && (
              <div className="flex items-center gap-3 mt-3">
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={sessionPage === 0}
                  onClick={() => setSessionPage((p) => p - 1)}
                >
                  Prev
                </Button>
                <span className="text-xs text-slate-500">Page {sessionPage + 1}</span>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={sessionPage >= sessionPageCount - 1}
                  onClick={() => setSessionPage((p) => p + 1)}
                >
                  Next
                </Button>
              </div>
            )}
          </>
        )}
      </Card>
    </div>
  )
}
