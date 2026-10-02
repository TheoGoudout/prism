import type { MetricBenchmark, PostPerformanceReport } from "@/client"
import { formatCompact } from "@/lib/format"

/** Post metrics that can be benchmarked, in display order. */
export const POST_METRICS = {
  engagements: "Engagements",
  engagement_rate: "Eng. rate",
  impressions: "Impressions",
  reach: "Reach",
  views: "Views",
  likes: "Likes",
  comments: "Comments",
  shares: "Shares",
  clicks: "Clicks",
  saves: "Saves",
} as const

export type PostMetric = keyof typeof POST_METRICS

/** The metrics this platform reports on enough posts to benchmark. */
export function benchmarkedMetrics(
  report: PostPerformanceReport,
): PostMetric[] {
  return (Object.keys(POST_METRICS) as PostMetric[]).filter(
    (metric) => metric in report.benchmarks,
  )
}

/** Engagement rate as a percentage, everything else as a compact count. */
export function formatMetric(
  metric: PostMetric,
  value: number | null | undefined,
): string {
  if (value == null) return "—"
  if (metric === "engagement_rate") return `${(value * 100).toFixed(1)}%`
  return formatCompact(Math.round(value))
}

/** Where a value sits relative to the best (P95) and worst (P5) posts. */
export type Tier = "top" | "bottom" | "typical"

export function tier(
  value: number | null | undefined,
  benchmark: MetricBenchmark | undefined,
): Tier | null {
  if (value == null || !benchmark) return null
  // Every post performed the same: nothing stands out
  if (benchmark.p95 === benchmark.p5) return "typical"
  if (value >= benchmark.p95) return "top"
  if (value <= benchmark.p5) return "bottom"
  return "typical"
}
