/**
 * Comparing the analytics period with another one in the past.
 *
 * The main period may be open-ended (no end date: it runs up to today). The
 * comparison period always has both dates. How their figures are compared
 * depends on their lengths (see `comparisonBasis`):
 *
 * - same length: totals as they are;
 * - open-ended main period shorter than the comparison period: the main
 *   period is projected to the comparison period's length, at its current
 *   pace (counts) or along its current trend (followers);
 * - otherwise: counts per day.
 *
 * Kept free of React and of runtime imports from `@/`, so that it can be
 * unit-tested on its own.
 */
import {
  addDays,
  differenceInCalendarDays,
  endOfMonth,
  format,
  parseISO,
  startOfMonth,
  subMonths,
  subYears,
} from "date-fns"

import type { MetricTotals, PlatformFollowers, TimeSeriesPoint } from "@/client"

/** A day as the API expects it: yyyy-MM-dd. */
export type Day = string

export interface Period {
  from: Day
  /** Missing: the period runs up to today. */
  to?: Day
}

export interface ClosedPeriod {
  from: Day
  to: Day
}

/** Below this many complete days, a projection would say little. */
export const MIN_PROJECTION_DAYS = 3

const DAY_PATTERN = /^\d{4}-\d{2}-\d{2}$/

export function isDay(value: unknown): value is Day {
  return (
    typeof value === "string" &&
    DAY_PATTERN.test(value) &&
    !Number.isNaN(parseISO(value).getTime())
  )
}

export function today(): Day {
  return format(new Date(), "yyyy-MM-dd")
}

export function shiftDay(day: Day, days: number): Day {
  return format(addDays(parseISO(day), days), "yyyy-MM-dd")
}

/** Days from `from` to `to`, both included. */
export function daysBetween(from: Day, to: Day): number {
  return differenceInCalendarDays(parseISO(to), parseISO(from)) + 1
}

export function periodEnd(period: Period, now: Day): Day {
  return period.to ?? now
}

export function periodLength(period: Period, now: Day): number {
  return daysBetween(period.from, periodEnd(period, now))
}

/** "Sep 1", with the year when it isn't the current one. */
export function formatDay(day: Day, now: Day, withYear = false): string {
  const year = withYear || day.slice(0, 4) !== now.slice(0, 4)
  return format(parseISO(day), year ? "MMM d, yyyy" : "MMM d")
}

/** "Sep 1 – Sep 30", with years when the period isn't in the current one. */
export function formatPeriod(period: Period, now: Day): string {
  const end = periodEnd(period, now)
  const withYear =
    period.from.slice(0, 4) !== now.slice(0, 4) ||
    end.slice(0, 4) !== now.slice(0, 4)
  const from = formatDay(period.from, now, withYear)
  return `${from} – ${period.to ? formatDay(period.to, now, withYear) : "today"}`
}

// ---------------------------------------------------------------------------
// Presets
// ---------------------------------------------------------------------------

/** The last `days` days, up to today (open-ended). */
export function lastDaysPeriod(days: number, now: Day): Period {
  return { from: shiftDay(now, -(days - 1)) }
}

/** The current month so far (open-ended). */
export function thisMonthPeriod(now: Day): Period {
  return { from: format(startOfMonth(parseISO(now)), "yyyy-MM-dd") }
}

/** The calendar month before the one `day` is in. */
export function monthBefore(day: Day): ClosedPeriod {
  const month = subMonths(startOfMonth(parseISO(day)), 1)
  return {
    from: format(month, "yyyy-MM-dd"),
    to: format(endOfMonth(month), "yyyy-MM-dd"),
  }
}

/** The period of the same length (so far) that ends the day before. */
export function previousPeriod(period: Period, now: Day): ClosedPeriod {
  const length = periodLength(period, now)
  return {
    from: shiftDay(period.from, -length),
    to: shiftDay(period.from, -1),
  }
}

/** The same dates a year earlier. */
export function yearBefore(period: Period, now: Day): ClosedPeriod {
  const shift = (d: Day) => format(subYears(parseISO(d), 1), "yyyy-MM-dd")
  return { from: shift(period.from), to: shift(periodEnd(period, now)) }
}

// ---------------------------------------------------------------------------
// How to compare
// ---------------------------------------------------------------------------

export type ComparisonBasis =
  /** Same lengths: totals as they are. */
  | { kind: "total" }
  /** The main period is projected to `length` days, ending on `end`. */
  | { kind: "projected"; length: number; completeDays: number; end: Day }
  /** Different lengths: counts per day. `tooEarly`: a projection is due, but
   * there aren't enough complete days for it yet. */
  | { kind: "perDay"; tooEarly: boolean }

export function comparisonBasis(
  main: Period,
  compare: ClosedPeriod,
  now: Day,
): ComparisonBasis {
  const mainLength = periodLength(main, now)
  const compareLength = periodLength(compare, now)
  if (main.to === undefined && mainLength < compareLength) {
    // Today is usually only partly synced: project from the days before it
    const completeDays = mainLength - 1
    if (completeDays < MIN_PROJECTION_DAYS) {
      return { kind: "perDay", tooEarly: true }
    }
    return {
      kind: "projected",
      length: compareLength,
      completeDays,
      end: shiftDay(main.from, compareLength - 1),
    }
  }
  if (mainLength === compareLength) return { kind: "total" }
  return { kind: "perDay", tooEarly: false }
}

// ---------------------------------------------------------------------------
// Daily series
// ---------------------------------------------------------------------------

export type CountMetric = "exposures" | "reach" | "engagements" | "clicks"
export type TrendMetric = CountMetric | "followers"

/** A count per day of the period, from its first day (0 for missing days). */
export function dailyCounts(
  points: TimeSeriesPoint[],
  metric: CountMetric,
  from: Day,
  days: number,
): number[] {
  const byDate = new Map(points.map((point) => [point.date, point]))
  return Array.from(
    { length: days },
    (_, i) => byDate.get(shiftDay(from, i))?.[metric] ?? 0,
  )
}

/** Each platform's follower counts, indexed by day of the period. */
function followerSeries(
  series: PlatformFollowers[],
  from: Day,
): Map<number, number>[] {
  return series.map(
    (platform) =>
      new Map(
        platform.points.map((point) => [
          daysBetween(from, point.date) - 1,
          point.followers,
        ]),
      ),
  )
}

/** Total followers per day of the period (null before any count). */
export function dailyFollowers(
  series: PlatformFollowers[],
  from: Day,
  days: number,
): (number | null)[] {
  const platforms = followerSeries(series, from)
  return Array.from({ length: days }, (_, i) => {
    const counts = platforms
      .map((platform) => platform.get(i))
      .filter((count) => count !== undefined)
    return counts.length ? counts.reduce((a, b) => a + b, 0) : null
  })
}

export function cumulative(values: number[]): number[] {
  let sum = 0
  return values.map((value) => {
    sum += value
    return sum
  })
}

// ---------------------------------------------------------------------------
// Projection
// ---------------------------------------------------------------------------

/**
 * A count's projected total over `length` days: its total over the
 * `completeDays` first days, continued at the same daily rate.
 */
export function projectCount(
  daily: number[],
  completeDays: number,
  length: number,
): number {
  const sum = daily.slice(0, completeDays).reduce((a, b) => a + b, 0)
  return (sum / completeDays) * length
}

/** Least-squares slope of the points, or 0 with fewer than two of them. */
function slope(points: [number, number][]): number {
  if (points.length < 2) return 0
  const meanX = points.reduce((s, [x]) => s + x, 0) / points.length
  const meanY = points.reduce((s, [, y]) => s + y, 0) / points.length
  let num = 0
  let den = 0
  for (const [x, y] of points) {
    num += (x - meanX) * (y - meanY)
    den += (x - meanX) ** 2
  }
  return den ? num / den : 0
}

/**
 * A level's projected value per day index: from each platform's latest
 * count among the complete days, along the straight line fitted through its
 * counts. Platforms are projected one by one, so a platform whose history
 * starts mid-period doesn't read as a jump. Null if there's no count at all.
 */
export function followersProjector(
  series: PlatformFollowers[],
  from: Day,
  completeDays: number,
): ((day: number) => number) | null {
  const lines = followerSeries(series, from)
    .map((platform) =>
      [...platform.entries()]
        .filter(([day]) => day >= 0 && day < completeDays)
        .sort(([a], [b]) => a - b),
    )
    .filter((points) => points.length > 0)
    .map((points) => {
      const [lastDay, lastCount] = points[points.length - 1]
      return { lastDay, lastCount, slope: slope(points), first: points[0][1] }
    })
  if (!lines.length) return null
  return (day) =>
    lines.reduce(
      (sum, line) =>
        sum + Math.max(0, line.lastCount + line.slope * (day - line.lastDay)),
      0,
    )
}

/** First total follower count of the complete days, for growth. */
function firstFollowers(
  series: PlatformFollowers[],
  from: Day,
  completeDays: number,
): number | null {
  const firsts = followerSeries(series, from)
    .map((platform) =>
      [...platform.entries()]
        .filter(([day]) => day >= 0 && day < completeDays)
        .sort(([a], [b]) => a - b),
    )
    .filter((points) => points.length > 0)
    .map((points) => points[0][1])
  return firsts.length ? firsts.reduce((a, b) => a + b, 0) : null
}

export type KpiMetric =
  | CountMetric
  | "engagement_rate"
  | "followers_count"
  | "followers_growth"

export type Projections = Partial<Record<KpiMetric, number | null>>

/** The main period's projected KPIs, at the end of the projection. */
export function projectTotals(
  points: TimeSeriesPoint[],
  followers: PlatformFollowers[],
  from: Day,
  basis: Extract<ComparisonBasis, { kind: "projected" }>,
): Projections {
  const { completeDays, length } = basis
  const projections: Projections = {}
  for (const metric of [
    "exposures",
    "reach",
    "engagements",
    "clicks",
  ] as const) {
    projections[metric] = projectCount(
      dailyCounts(points, metric, from, completeDays),
      completeDays,
      length,
    )
  }
  const projector = followersProjector(followers, from, completeDays)
  const first = firstFollowers(followers, from, completeDays)
  const end = projector ? projector(length - 1) : null
  projections.followers_count = end
  projections.followers_growth =
    end !== null && first !== null ? end - first : null
  return projections
}

// ---------------------------------------------------------------------------
// KPI comparison
// ---------------------------------------------------------------------------

export type ChangeKind = "relative" | "points" | "absolute"

export interface KpiComparison {
  /** The main period's figure that is compared (projected, per day...). */
  current: number | null
  previous: number | null
  /** Relative (0.12 = +12%), in rate points, or absolute. Null if unknown. */
  change: number | null
  kind: ChangeKind
  /** The figure is a projection, or a per-day average. */
  projected: boolean
  perDay: boolean
}

const CHANGE_KIND: Record<KpiMetric, ChangeKind> = {
  exposures: "relative",
  reach: "relative",
  engagements: "relative",
  clicks: "relative",
  engagement_rate: "points",
  followers_count: "absolute",
  followers_growth: "absolute",
}

// Flows, which a different length changes; levels and rates don't depend on it
const PER_DAY_METRICS: ReadonlySet<KpiMetric> = new Set([
  "exposures",
  "reach",
  "engagements",
  "clicks",
  "followers_growth",
])

export function compareKpi(
  metric: KpiMetric,
  {
    main,
    compare,
    basis,
    projections,
    mainLength,
    compareLength,
  }: {
    main: MetricTotals
    compare: MetricTotals
    basis: ComparisonBasis
    projections: Projections
    mainLength: number
    compareLength: number
  },
): KpiComparison {
  const kind = CHANGE_KIND[metric]
  let current = main[metric] ?? null
  let previous = compare[metric] ?? null
  const projected = basis.kind === "projected" && metric in projections
  const perDay = basis.kind === "perDay" && PER_DAY_METRICS.has(metric)
  if (projected) {
    current = projections[metric] ?? null
  } else if (perDay) {
    current = current === null ? null : current / mainLength
    previous = previous === null ? null : previous / compareLength
  }

  let change: number | null = null
  if (current !== null && previous !== null) {
    if (kind === "relative") {
      change = previous ? (current - previous) / previous : null
    } else {
      change = current - previous
    }
  }
  return { current, previous, change, kind, projected, perDay }
}

/** "+12.3%", "-0.42 pts", "+1.2K"; "—" when unknown. */
export function formatChange(change: number | null, kind: ChangeKind): string {
  if (change === null || !Number.isFinite(change)) return "—"
  const sign = change > 0 ? "+" : change < 0 ? "-" : ""
  const abs = Math.abs(change)
  if (kind === "relative") return `${sign}${(abs * 100).toFixed(1)}%`
  if (kind === "points") return `${sign}${(abs * 100).toFixed(2)} pts`
  if (abs >= 1_000_000) return `${sign}${(abs / 1_000_000).toFixed(1)}M`
  if (abs >= 1_000) return `${sign}${(abs / 1_000).toFixed(1)}K`
  return `${sign}${abs >= 10 ? Math.round(abs) : Math.round(abs * 10) / 10}`
}

// ---------------------------------------------------------------------------
// Trend chart rows
// ---------------------------------------------------------------------------

export interface TrendRow {
  /** 1-based day of the periods. */
  day: number
  mainDate: Day
  compareDate: Day | null
  main: number | null
  projected: number | null
  compare: number | null
}

/**
 * One row per day of the longest of: the main period, its projection and the
 * comparison period. The comparison period is aligned on its first day.
 */
export function trendRows({
  metric,
  cumulative: asCumulative,
  main,
  mainPoints,
  mainFollowers,
  compare,
  comparePoints,
  compareFollowers,
  basis,
  now,
}: {
  metric: TrendMetric
  cumulative: boolean
  main: Period
  mainPoints: TimeSeriesPoint[]
  mainFollowers: PlatformFollowers[]
  compare: ClosedPeriod | null
  comparePoints: TimeSeriesPoint[]
  compareFollowers: PlatformFollowers[]
  basis: ComparisonBasis | null
  now: Day
}): TrendRow[] {
  const mainLength = periodLength(main, now)
  const compareLength = compare ? periodLength(compare, now) : 0
  const projection = basis?.kind === "projected" ? basis : null
  const days = Math.max(mainLength, compareLength, projection?.length ?? 0)

  const series = (
    points: TimeSeriesPoint[],
    followers: PlatformFollowers[],
    from: Day,
    length: number,
  ): (number | null)[] => {
    if (metric === "followers") return dailyFollowers(followers, from, length)
    const daily = dailyCounts(points, metric, from, length)
    return asCumulative ? cumulative(daily) : daily
  }
  const mainValues = series(mainPoints, mainFollowers, main.from, mainLength)
  const compareValues = compare
    ? series(comparePoints, compareFollowers, compare.from, compareLength)
    : []

  let project: ((day: number) => number | null) | null = null
  if (projection) {
    const last = projection.completeDays - 1
    if (metric === "followers") {
      project = followersProjector(
        mainFollowers,
        main.from,
        projection.completeDays,
      )
    } else {
      const daily = dailyCounts(mainPoints, metric, main.from, mainLength)
      const total = cumulative(daily)[last]
      const rate = total / projection.completeDays
      // Starts on the last complete day, so that it continues the main line
      project = asCumulative
        ? (day) => total + rate * (day - last)
        : (day) => (day === last ? daily[last] : rate)
    }
  }

  return Array.from({ length: days }, (_, i) => ({
    day: i + 1,
    mainDate: shiftDay(main.from, i),
    compareDate:
      compare && i < compareLength ? shiftDay(compare.from, i) : null,
    main: i < mainLength ? mainValues[i] : null,
    projected:
      project && projection && i >= projection.completeDays - 1
        ? i < projection.length
          ? project(i)
          : null
        : null,
    compare: i < compareLength ? compareValues[i] : null,
  }))
}
