import { ArrowDown, ArrowUp } from "lucide-react"

import type { PostPerformance, PostPerformanceReport } from "@/client"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { formatRelative } from "@/lib/format"
import { cn } from "@/lib/utils"
import {
  formatMetric,
  POST_METRICS,
  type PostMetric,
  type Tier,
  tier,
} from "./benchmarks"
import { PostLabel } from "./PostLabel"

const TIER_STYLES: Record<Tier, string> = {
  top: "text-green-600 dark:text-green-500 font-medium",
  bottom: "text-destructive font-medium",
  typical: "",
}

const BENCHMARK_ROWS = [
  { key: "p95", label: "Best 5% (P95)" },
  { key: "p50", label: "Median" },
  { key: "p5", label: "Worst 5% (P5)" },
] as const

/** "Top 5%" / "Bottom 5%" on the post's headline metric, if it stands out. */
function TierBadge({ value }: { value: Tier | null }) {
  if (value === "top")
    return (
      <Badge className="shrink-0 bg-green-600 text-white dark:bg-green-500">
        <ArrowUp /> Top 5%
      </Badge>
    )
  if (value === "bottom")
    return (
      <Badge variant="destructive" className="shrink-0">
        <ArrowDown /> Bottom 5%
      </Badge>
    )
  return null
}

function MetricCell({
  post,
  metric,
  report,
}: {
  post: PostPerformance
  metric: PostMetric
  report: PostPerformanceReport
}) {
  const value = post[metric]
  const rank = post.percentile_ranks[metric]
  const postTier = tier(value, report.benchmarks[metric])
  return (
    <TableCell className="text-right">
      <span
        className={cn(
          "inline-flex items-center gap-1",
          postTier && TIER_STYLES[postTier],
        )}
      >
        {postTier === "top" && <ArrowUp className="size-3" aria-hidden />}
        {postTier === "bottom" && <ArrowDown className="size-3" aria-hidden />}
        {formatMetric(metric, value)}
      </span>
      {rank != null && (
        <span
          className="block text-xs text-muted-foreground"
          title={`Better than ${Math.round(rank)}% of posts`}
        >
          P{Math.round(rank)}
        </span>
      )}
    </TableCell>
  )
}

/**
 * The latest posts, one column per benchmarked metric. Each value shows its
 * percentile rank, and values beyond the P95 / P5 benchmarks stand out.
 */
export function PostPerformanceTable({
  report,
  metrics,
  headline,
}: {
  report: PostPerformanceReport
  metrics: PostMetric[]
  headline: PostMetric | undefined
}) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Post</TableHead>
          <TableHead>Published</TableHead>
          {metrics.map((metric) => (
            <TableHead key={metric} className="text-right">
              {POST_METRICS[metric]}
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {BENCHMARK_ROWS.map(({ key, label }) => (
          <TableRow key={key} className="bg-muted/40 text-muted-foreground">
            <TableCell colSpan={2} className="text-xs font-medium">
              {label}
            </TableCell>
            {metrics.map((metric) => (
              <TableCell key={metric} className="text-right text-xs">
                {formatMetric(metric, report.benchmarks[metric]?.[key])}
              </TableCell>
            ))}
          </TableRow>
        ))}
        {report.posts.map((post) => (
          <TableRow key={post.id}>
            <TableCell className="max-w-xs">
              <div className="flex items-center gap-2">
                <div className="min-w-0">
                  <PostLabel post={post} />
                </div>
                {headline && (
                  <TierBadge
                    value={tier(post[headline], report.benchmarks[headline])}
                  />
                )}
              </div>
            </TableCell>
            <TableCell className="whitespace-nowrap text-sm text-muted-foreground">
              {formatRelative(post.published_at)}
            </TableCell>
            {metrics.map((metric) => (
              <MetricCell
                key={metric}
                post={post}
                metric={metric}
                report={report}
              />
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
