import { formatDistanceToNow } from "date-fns"

import { shiftDay, today } from "./comparison"

/** Compact number for dashboards: 1234 → "1.2K"; missing → "—". */
export function formatCompact(n: number | null | undefined): string {
  if (n == null) return "—"
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return n.toString()
}

/** Compact number with its sign: 1234 → "+1.2K", -50 → "-50"; missing → "—". */
export function formatSigned(n: number | null | undefined): string {
  if (n == null) return "—"
  const sign = n > 0 ? "+" : n < 0 ? "-" : ""
  return sign + formatCompact(Math.abs(n))
}

/** Signed ratio as a percentage: 0.0123 → "+1.23%"; missing → "—". */
export function formatSignedPercent(ratio: number | null | undefined): string {
  if (ratio == null) return "—"
  return (ratio > 0 ? "+" : "") + formatPercent(ratio)
}

/** Ratio as a percentage: 0.0345 → "3.45%"; missing → "—". */
export function formatPercent(ratio: number | null | undefined): string {
  if (ratio == null) return "—"
  return `${(ratio * 100).toFixed(2)}%`
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
  const dateTo = today()
  return { dateFrom: shiftDay(dateTo, -(days - 1)), dateTo }
}

/** "1 post", "3 posts". */
export const plural = (count: number, noun: string) =>
  `${count} ${noun}${count === 1 ? "" : "s"}`
