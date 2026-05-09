import { Activity, RefreshCw, Server, Zap } from "lucide-react"
import React, { useState } from "react"
import { Link } from "react-router-dom"
import { ModelBarChart } from "../components/charts/ModelBarChart"
import { StackedTokenChart } from "../components/charts/StackedTokenChart"
import { Badge } from "../components/ui/Badge"
import { Button } from "../components/ui/Button"
import { Card } from "../components/ui/Card"
import { MetricCard } from "../components/ui/MetricCard"
import { QuotaPanel } from "../components/ui/QuotaPanel"
import { RangePicker } from "../components/ui/RangePicker"
import { Spinner } from "../components/ui/Spinner"
import { TokenBreakdownPie } from "../components/charts/TokenBreakdownPie"
import type { Range } from "../hooks/useDashboard"
import { useDashboard } from "../hooks/useDashboard"
import type { ProviderId } from "../types"
import { formatLargeNumber, formatRelative, latestQuotas } from "../utils"

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

const PROVIDER_IDS: ProviderId[] = ["gemini", "codex", "copilot"]

export function Overview(): React.JSX.Element {
  const [range, setRange] = useState<Range>("7d")
  const {
    providers,
    quotas,
    sessions,
    timeSeriesByProvider,
    modelUsage,
    providerTotals,
    loading,
    error,
    refresh,
  } = useDashboard(undefined, range)

  const handleRange = (next: Range) => {
    setRange(next)
  }

  const latest = latestQuotas(quotas)
  const totalTokens = providerTotals.reduce((s, r) => s + r.total_tokens, 0)
  const enabledCount = providers.filter((p) => p.enabled).length

  const quotasByProvider = PROVIDER_IDS.map((id) => ({
    id,
    label: providerLabels[id],
    rows: latest.filter((q) => q.provider_id === id),
  }))

  const allTimeSeries = [
    ...timeSeriesByProvider.gemini,
    ...timeSeriesByProvider.codex,
    ...timeSeriesByProvider.copilot,
  ]

  return (
    <div className="flex flex-col gap-6 p-6 min-h-0 overflow-y-auto">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Overview</h1>
          <p className="text-sm text-slate-400 mt-0.5">All providers</p>
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

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          label="Active Providers"
          value={`${enabledCount} / ${providers.length}`}
          icon={<Server className="h-5 w-5" />}
        />
        <MetricCard
          label="Sessions"
          value={sessions.length}
          sub={`in ${range}`}
          icon={<Activity className="h-5 w-5" />}
        />
        <MetricCard
          label="Tokens"
          value={formatLargeNumber(totalTokens)}
          sub={`${range} · all providers`}
          icon={<Zap className="h-5 w-5" />}
        />
        <Card>
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wide">
            Per provider
          </p>
          <div className="mt-2 space-y-1.5">
            {PROVIDER_IDS.map((id) => {
              const row = providerTotals.find((p) => p.bucket === id)
              const value = row?.total_tokens ?? 0
              return (
                <div key={id} className="flex items-center justify-between text-xs">
                  <span className={providerColors[id]}>{providerLabels[id]}</span>
                  <span className="font-mono text-slate-300">{formatLargeNumber(value)}</span>
                </div>
              )
            })}
          </div>
        </Card>
      </div>

      {latest.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-slate-300 mb-3">Latest Quotas</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {quotasByProvider.map(({ id, label, rows }) => (
              <Card key={id}>
                <div className="flex items-center justify-between mb-3">
                  <span className={`text-sm font-semibold ${providerColors[id]}`}>{label}</span>
                  <Link
                    to={`/provider/${id}`}
                    className="text-xs text-slate-500 hover:text-violet-400 transition-colors"
                  >
                    Details &rarr;
                  </Link>
                </div>
                <QuotaPanel providerId={id} latest={rows} />
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
              by provider · hour
            </span>
          </h2>
          <StackedTokenChart byProvider={timeSeriesByProvider} mode="provider" />
        </Card>
        <Card>
          <h2 className="text-sm font-semibold text-slate-300 mb-3">Token types</h2>
          <TokenBreakdownPie rows={allTimeSeries} />
        </Card>
      </div>

      <Card>
        <h2 className="text-sm font-semibold text-slate-300 mb-3">Top models</h2>
        <ModelBarChart data={modelUsage} />
      </Card>

      <Card>
        <h2 className="text-sm font-semibold text-slate-300 mb-3">Provider Status</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-700">
                <th className="text-left py-2 px-3 text-xs font-medium text-slate-400">
                  Provider
                </th>
                <th className="text-left py-2 px-3 text-xs font-medium text-slate-400">Status</th>
                <th className="text-left py-2 px-3 text-xs font-medium text-slate-400">
                  Last updated
                </th>
              </tr>
            </thead>
            <tbody>
              {providers.map((p) => (
                <tr
                  key={p.id}
                  className="border-b border-slate-800 hover:bg-slate-800/40 transition-colors"
                >
                  <td className="py-2.5 px-3">
                    <Link
                      to={`/provider/${p.id}`}
                      className={`font-medium hover:underline ${providerColors[p.id]}`}
                    >
                      {providerLabels[p.id]}
                    </Link>
                  </td>
                  <td className="py-2.5 px-3">
                    <Badge variant={p.enabled ? "success" : "error"}>
                      {p.enabled ? "Enabled" : "Disabled"}
                    </Badge>
                  </td>
                  <td className="py-2.5 px-3 text-slate-400">{formatRelative(p.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
