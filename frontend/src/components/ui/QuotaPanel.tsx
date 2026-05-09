import React from "react"
import type { ProviderId, QuotaRow } from "../../types"
import { formatDate } from "../../utils"
import { ProgressBar } from "./ProgressBar"

interface QuotaPanelProps {
  providerId: ProviderId
  /** Already deduped to latest row per quota_name */
  latest: QuotaRow[]
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
      // Stamp a synthetic quota_name matching the family so displayLabel works simply.
      best[family] = { ...row, quota_name: family }
    }
  }
  return GEMINI_FAMILY_ORDER.flatMap((f) => (best[f] ? [best[f]!] : []))
}

/** Map raw quota_name to a human-friendly display label per provider. */
export function displayLabel(providerId: ProviderId, quotaName: string): string {
  if (providerId === "copilot") {
    if (quotaName.includes("premium_interactions") || quotaName.includes("premium-interactions")) return "Monthly"
    if (quotaName.includes("monthly")) return "Monthly"
    if (quotaName.includes("weekly")) return "Weekly"
    return quotaName
  }
  if (providerId === "codex") {
    if (quotaName === "primary") return "5 hours"
    if (quotaName === "secondary") return "Week"
    return quotaName
  }
  if (providerId === "gemini") {
    const label = GEMINI_FAMILY_LABEL[quotaName as GeminiFamily]
    return label ?? quotaName
  }
  return quotaName
}

export function QuotaPanel({
  providerId,
  latest,
}: QuotaPanelProps): React.JSX.Element {
  let visible: QuotaRow[]
  if (providerId === "copilot") {
    visible = filterCopilotQuotas(latest)
  } else if (providerId === "gemini") {
    visible = rollupGeminiQuotas(latest)
  } else {
    visible = latest
  }

  if (visible.length === 0) {
    return (
      <div className="flex flex-col gap-2">
        <p className="text-sm text-slate-500 py-2">No quota data</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      {visible.map((q) => (
        <div key={q.quota_name}>
          <div className="flex justify-between mb-1">
            <span className="text-xs font-medium text-slate-300">
              {displayLabel(providerId, q.quota_name)}
            </span>
          </div>
          <ProgressBar value={q.used_percent ?? 0} />
          <div className="flex justify-between mt-1">
            <span className="text-xs text-slate-500">
              {q.used_percent !== null ? `${q.used_percent.toFixed(1)}% used` : "n/a"}
            </span>
            {q.resets_at && (
              <span className="text-xs text-slate-600">
                resets {formatDate(q.resets_at)}
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
