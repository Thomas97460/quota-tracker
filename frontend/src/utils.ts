export function formatLargeNumber(value: number): string {
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)}B`
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`
  return String(value)
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "n/a"
  const d = new Date(value)
  if (isNaN(d.getTime())) return "n/a"
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(d)
}

export function formatRelative(value: string | null | undefined): string {
  if (!value) return "n/a"
  const d = new Date(value)
  if (isNaN(d.getTime())) return "n/a"
  const diffMs = Date.now() - d.getTime()
  const diffMins = Math.floor(diffMs / 60_000)
  if (diffMins < 1) return "just now"
  if (diffMins < 60) return `${diffMins}m ago`
  const diffHrs = Math.floor(diffMins / 60)
  if (diffHrs < 24) return `${diffHrs}h ago`
  const diffDays = Math.floor(diffHrs / 24)
  return `${diffDays}d ago`
}

const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

export function chartTickInterval(pointCount: number, maxTicks = 6): number | "preserveStartEnd" {
  if (pointCount <= maxTicks) return "preserveStartEnd"
  return Math.ceil(pointCount / maxTicks) - 1
}

/**
 * Format a time bucket for chart axes/tooltips.
 *
 * Supports buckets like:
 * - YYYY-MM-DD
 * - YYYY-MM-DDTHH
 * - YYYY-MM-DDTHH:MM
 * - full ISO timestamps (with Z or +00:00 and optional milliseconds)
 */
export function formatTimeBucket(bucket: string): string {
  if (!bucket) return ""

  // day: 2026-05-08
  if (/^\d{4}-\d{2}-\d{2}$/.test(bucket)) {
    const [, month, day] = bucket.split("-")
    const monthName = MONTH_NAMES[parseInt(month, 10) - 1]
    return `${monthName} ${day}`
  }

  // hour: 2026-05-08T22
  if (/^\d{4}-\d{2}-\d{2}T\d{2}$/.test(bucket)) {
    const [datePart, hour] = bucket.split("T")
    const [, month, day] = datePart.split("-")
    const monthName = MONTH_NAMES[parseInt(month, 10) - 1]
    return `${monthName} ${day} ${hour}h`
  }

  // minute: 2026-05-08T22:15
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(bucket)) {
    const [datePart, hm] = bucket.split("T")
    const [, month, day] = datePart.split("-")
    const monthName = MONTH_NAMES[parseInt(month, 10) - 1]
    return `${monthName} ${day} ${hm}`
  }

  // full ISO string -> local date formatting
  const d = new Date(bucket)
  if (!isNaN(d.getTime())) {
    const monthName = MONTH_NAMES[d.getMonth()]
    const day = String(d.getDate()).padStart(2, "0")
    const hh = String(d.getHours()).padStart(2, "0")
    const mm = String(d.getMinutes()).padStart(2, "0")
    return `${monthName} ${day} ${hh}:${mm}`
  }

  return bucket
}

/** Return the last path segment (works for both / and \ separators). */
export function basename(path: string | null | undefined): string | null {
  if (!path) return null
  const parts = path.replace(/\\/g, "/").split("/").filter(Boolean)
  return parts[parts.length - 1] ?? null
}

/** Keep only the most-recent quota row per provider+name combination */
export function latestQuotas<T extends { provider_id: string; quota_name: string; timestamp: string }>(rows: T[]): T[] {
  const byKey = new Map<string, T>()
  rows.forEach((row) => {
    const key = `${row.provider_id}:${row.quota_name}`
    const prev = byKey.get(key)
    if (!prev || prev.timestamp < row.timestamp) byKey.set(key, row)
  })
  return [...byKey.values()].sort((a, b) => a.provider_id.localeCompare(b.provider_id))
}
