import { format, formatDistanceToNow, subDays } from "date-fns"

/** Compact number for dashboards: 1234 → "1.2K"; missing → "—". */
export function formatCompact(n: number | null | undefined): string {
  if (n == null) return "—"
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return n.toString()
}

/** "3 hours ago", or "Never" for a missing timestamp. */
export function formatRelative(timestamp: string | null | undefined): string {
  if (!timestamp) return "Never"
  return formatDistanceToNow(new Date(timestamp), { addSuffix: true })
}

export interface DateRange {
  dateFrom: string // yyyy-MM-dd, as the API expects
  dateTo: string
}

/** The last `days` days, today included. */
export function lastDays(days: number): DateRange {
  const today = new Date()
  return {
    dateFrom: format(subDays(today, days - 1), "yyyy-MM-dd"),
    dateTo: format(today, "yyyy-MM-dd"),
  }
}
