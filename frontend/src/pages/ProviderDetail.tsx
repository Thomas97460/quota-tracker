import { Activity, AlertCircle, RefreshCw, Zap } from "lucide-react"
import React, { useState } from "react"
import { useParams } from "react-router-dom"
import { ModelBarChart } from "../components/charts/ModelBarChart"
import { StackedTokenChart } from "../components/charts/StackedTokenChart"
import { Badge } from "../components/ui/Badge"
import { Button } from "../components/ui/Button"
import { Card } from "../components/ui/Card"
import { MetricCard } from "../components/ui/MetricCard"
import { ProgressBar } from "../components/ui/ProgressBar"
import { RangePicker } from "../components/ui/RangePicker"
import { Spinner } from "../components/ui/Spinner"
import { TokenBreakdown } from "../components/ui/TokenBreakdown"
import type { Granularity, Range } from "../hooks/useDashboard"
import { useDashboard } from "../hooks/useDashboard"
import type { ProviderId } from "../types"
import { formatDate, formatLargeNumber, formatRelative, latestQuotas } from "../utils"

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

function defaultGranularity(range: Range): Granularity {
  return range === "24h" ? "hour" : "day"
}

export function ProviderDetail(): React.JSX.Element {
  const { id } = useParams<{ id: string }>()
  const [range, setRange] = useState<Range>("7d")
  const [granularity, setGranularity] = useState<Granularity>(defaultGranularity("7d"))

  const providerId: ProviderId | null = VALID_PROVIDERS.includes(id as ProviderId)
    ? (id as ProviderId)
    : null

  const handleRange = (next: Range) => {
    setRange(next)
    setGranularity(defaultGranularity(next))
  }

  const {
    providers,
    quotas,
    sessions,
    timeSeries,
    modelUsage,
    loading,
    error,
    refresh,
  } = useDashboard(providerId ?? undefined, range, granularity)

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
  const latest = latestQuotas(quotas)
  const totalTokens = timeSeries.reduce((s, r) => s + r.total_tokens, 0)

  return (
    <div className="flex flex-col gap-6 p-6 min-h-0 overflow-y-auto">
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
            granularity={granularity}
            onRangeChange={handleRange}
            onGranularityChange={setGranularity}
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

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
        <MetricCard
          label="Sessions"
          value={sessions.length}
          icon={<Activity className="h-5 w-5" />}
        />
        <MetricCard
          label="Tokens"
          value={formatLargeNumber(totalTokens)}
          sub={`in range (${range})`}
          icon={<Zap className="h-5 w-5" />}
        />
        <MetricCard label="Active Quotas" value={latest.length} />
      </div>

      {provider && (
        <Card>
          <div className="flex flex-wrap gap-4">
            <div>
              <p className="text-xs text-slate-500 mb-1">Passive Sync</p>
              <Badge variant={provider.config.passive_sync_enabled ? "info" : "default"}>
                {provider.config.passive_sync_enabled ? "Enabled" : "Disabled"}
              </Badge>
            </div>
            <div>
              <p className="text-xs text-slate-500 mb-1">Active Probe</p>
              <Badge variant={provider.config.active_probe_enabled ? "info" : "default"}>
                {provider.config.active_probe_enabled ? "Enabled" : "Disabled"}
              </Badge>
            </div>
            <div>
              <p className="text-xs text-slate-500 mb-1">Home Path</p>
              <code className="text-xs text-slate-300 bg-slate-900 rounded px-2 py-0.5">
                {provider.config.home_path}
              </code>
            </div>
          </div>
        </Card>
      )}

      {latest.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-slate-300 mb-3">Quotas</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {latest.map((q) => (
              <Card key={q.quota_name}>
                <p className="text-xs font-medium text-slate-300 mb-1">{q.quota_name}</p>
                <p className="text-xs text-slate-500 mb-2">{q.source}</p>
                <ProgressBar value={q.used_percent ?? 0} />
                <div className="flex justify-between mt-2">
                  <span className="text-xs text-slate-500">
                    {q.used_percent !== null ? `${q.used_percent.toFixed(1)}% used` : "n/a"}
                  </span>
                  {q.resets_at && (
                    <span className="text-xs text-slate-600">
                      resets {formatDate(q.resets_at)}
                    </span>
                  )}
                </div>
              </Card>
            ))}
          </div>
        </section>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <h2 className="text-sm font-semibold text-slate-300 mb-3">
            Tokens over time
            <span className="ml-2 text-xs font-normal text-slate-500">
              by kind · {granularity}
            </span>
          </h2>
          <StackedTokenChart rows={timeSeries} mode="kind" />
        </Card>
        <Card>
          <h2 className="text-sm font-semibold text-slate-300 mb-3">Breakdown</h2>
          <TokenBreakdown rows={timeSeries} />
        </Card>
      </div>

      <Card>
        <h2 className="text-sm font-semibold text-slate-300 mb-3">Tokens by model</h2>
        <ModelBarChart data={modelUsage} />
      </Card>

      <Card>
        <h2 className="text-sm font-semibold text-slate-300 mb-3">
          Sessions
          <span className="ml-2 text-xs font-normal text-slate-500">({sessions.length})</span>
        </h2>
        {sessions.length === 0 ? (
          <p className="text-sm text-slate-500 py-4 text-center">No sessions in selected range</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700">
                  <th className="text-left py-2 px-3 text-xs font-medium text-slate-400">
                    Project
                  </th>
                  <th className="text-left py-2 px-3 text-xs font-medium text-slate-400">Model</th>
                  <th className="text-left py-2 px-3 text-xs font-medium text-slate-400">
                    Created
                  </th>
                  <th className="text-left py-2 px-3 text-xs font-medium text-slate-400">
                    Last seen
                  </th>
                </tr>
              </thead>
              <tbody>
                {sessions.map((s) => (
                  <tr
                    key={s.id}
                    className="border-b border-slate-800 hover:bg-slate-800/40 transition-colors"
                  >
                    <td
                      className="py-2.5 px-3 text-slate-300 max-w-[180px] truncate"
                      title={s.project_path ?? undefined}
                    >
                      {s.project_name ?? s.project_path ?? (
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
        )}
      </Card>
    </div>
  )
}
