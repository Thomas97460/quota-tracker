import React from "react"
import type { ProviderId, QuotaRow } from "../../types"
import { formatDate } from "../../utils"

interface QuotaPanelProps {
  providerId: ProviderId
  /** Already deduped to latest row per quota_name */
  latest: QuotaRow[]
  /** CSS color value for the provider (e.g. "var(--gemini)") */
  providerColor?: string
}

function inferredWindowMinutes(providerId: ProviderId, quotaName: string): number | null {
  const lower = quotaName.toLowerCase()

  // Provider-specific known keys.
  if (providerId === "codex") {
    if (lower === "secondary") return 60 * 24 * 7 // weekly
    if (lower === "primary") return 60 * 5 // 5 hours
  }
  if (providerId === "copilot") {
    if (lower.includes("premium_interactions") || lower.includes("premium-interactions")) {
      return 60 * 24 * 30
    }
  }

  // Generic inference from quota name.
  if (lower.includes("month")) return 60 * 24 * 30
  if (lower.includes("week")) return 60 * 24 * 7
  if (lower.includes("day")) return 60 * 24
  if (lower.includes("hour") || lower.includes("hr")) return 60
  if (lower.includes("session")) return 0
  return null
}

function sortQuotasBiggestFirst(providerId: ProviderId, rows: QuotaRow[]): QuotaRow[] {
  const scored = rows.map((q, idx) => {
    const win =
      typeof q.window_minutes === "number"
        ? q.window_minutes
        : inferredWindowMinutes(providerId, q.quota_name)
    return { q, idx, win }
  })
  scored.sort((a, b) => {
    const aw = a.win ?? -1
    const bw = b.win ?? -1
    if (bw !== aw) return bw - aw
    return a.idx - b.idx
  })
  return scored.map((s) => s.q)
}

/** Filter Copilot quotas to only premium_interactions and weekly keys. */
export function filterCopilotQuotas(rows: QuotaRow[]): QuotaRow[] {
  return rows.filter(
    (q) =>
      q.quota_name.includes("premium-interactions") ||
      q.quota_name.includes("premium_interactions") ||
      q.quota_name.includes("weekly"),
  )
}

/** Filter Claude quotas to only "weekly" and "5h" for the card display. Weekly first. */
export function filterClaudeQuotas(rows: QuotaRow[]): QuotaRow[] {
  const ORDER: Record<string, number> = { weekly: 0, "5h": 1 }
  return rows
    .filter((q) => q.quota_name === "weekly" || q.quota_name === "5h")
    .sort((a, b) => (ORDER[a.quota_name] ?? 99) - (ORDER[b.quota_name] ?? 99))
}

// Gemini family order for display (most important first).
const GEMINI_FAMILY_ORDER = ["pro", "flash", "flash-lite"] as const
type GeminiFamily = (typeof GEMINI_FAMILY_ORDER)[number]

function geminiFamily(quotaName: string): GeminiFamily | null {
  const lower = quotaName.toLowerCase()
  if (lower.includes("flash-lite")) return "flash-lite"
  if (lower.includes("flash")) return "flash"
  if (lower.includes("pro")) return "pro"
  return null
}

const GEMINI_FAMILY_LABEL: Record<GeminiFamily, string> = {
  pro: "Pro",
  flash: "Flash",
  "flash-lite": "Flash-Lite",
}

/**
 * Collapse granular Gemini (model_id/token_type) rows into one representative
 * row per family (pro / flash / flash-lite), picking the most-restrictive bucket
 * (highest used_percent). Returns rows in fixed order: Pro, Flash, Flash-Lite.
 */
export function rollupGeminiQuotas(rows: QuotaRow[]): QuotaRow[] {
  const best: Partial<Record<GeminiFamily, QuotaRow>> = {}
  for (const row of rows) {
    const family = geminiFamily(row.quota_name)
    if (!family) continue
    const prev = best[family]
    const used = row.used_percent
    if (used === null) continue
    if (!prev || prev.used_percent === null || used > prev.used_percent) {
      best[family] = { ...row, quota_name: family }
    }
  }
  return GEMINI_FAMILY_ORDER.flatMap((f) => (best[f] ? [best[f]!] : []))
}

/** Map raw quota_name to a human-friendly display label per provider. */
export function displayLabel(providerId: ProviderId, quotaName: string): string {
  if (providerId === "copilot") {
    if (quotaName.includes("premium_interactions") || quotaName.includes("premium-interactions"))
      return "Monthly"
    if (quotaName.includes("monthly")) return "Monthly"
    if (quotaName.includes("weekly")) return "Weekly"
    return quotaName
  }
  if (providerId === "codex") {
    if (quotaName === "primary") return "5 hours"
    if (quotaName === "secondary") return "Weekly"
    return quotaName
  }
  if (providerId === "gemini") {
    const label = GEMINI_FAMILY_LABEL[quotaName as GeminiFamily]
    return label ?? quotaName
  }
  if (providerId === "claude") {
    if (quotaName === "seven_day_omelette") return "Claude Design"
    if (quotaName === "weekly") return "Weekly"
    if (quotaName === "5h") return "5h"
    return quotaName
  }
  return quotaName
}

function statusFor(pct: number): "crit" | "warn" | "ok" {
  if (pct >= 95) return "crit"
  if (pct >= 70) return "warn"
  return "ok"
}

export function formatRequestQuota(q: QuotaRow): string | null {
  const rd = q.raw_data || {}
  if (q.provider_id === "copilot" && rd.entitlement_requests !== undefined) {
    const limit = Number(rd.entitlement_requests)
    if (limit <= 0) return null
    const used = Math.round(limit * ((q.used_percent ?? 0) / 100))
    return `${used} / ${limit} requests`
  }
  return null
}

export function QuotaPanel({
  providerId,
  latest,
  providerColor,
}: QuotaPanelProps): React.JSX.Element {
  let visible: QuotaRow[]
  if (providerId === "copilot") {
    visible = sortQuotasBiggestFirst(providerId, filterCopilotQuotas(latest))
  } else if (providerId === "gemini") {
    visible = rollupGeminiQuotas(latest)
  } else if (providerId === "codex") {
    visible = sortQuotasBiggestFirst(providerId, latest)
  } else if (providerId === "claude") {
    visible = filterClaudeQuotas(latest)
  } else {
    visible = latest
  }

  if (visible.length === 0) {
    return (
      <div className="quota-card-body">
        <p style={{ color: "var(--fg-3)", fontSize: 12 }}>No quota data</p>
      </div>
    )
  }

  const color = providerColor ?? "var(--accent)"

  return (
    <div className="quota-card-body">
      {visible.map((q) => {
        const pct = q.used_percent ?? 0
        const status = statusFor(pct)
        const label = displayLabel(providerId, q.quota_name)
        const reqStr = formatRequestQuota(q)
        return (
          <div key={q.quota_name}>
            <div className="quota-row">
              <div className="quota-row-label">{label}</div>
              <div
                className={`qbar${status === "crit" ? " crit" : status === "warn" ? " warn" : ""}`}
                style={
                  {
                    "--w": pct + "%",
                    "--c": color,
                  } as React.CSSProperties
                }
              >
                <i></i>
              </div>
              <div
                className={`quota-row-pct${status === "crit" ? " crit" : status === "warn" ? " warn" : ""}`}
              >
                {q.used_percent !== null ? `${pct.toFixed(1)}%` : "n/a"}
              </div>
            </div>
            <div className="quota-meta" style={{ marginTop: 4 }}>
              <span>{reqStr || ""}</span>
              {q.resets_at && (
                <span
                  className={
                    status === "crit"
                      ? "quota-meta-crit"
                      : status === "warn"
                        ? "quota-meta-warn"
                        : ""
                  }
                >
                  resets {formatDate(q.resets_at)}
                </span>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
