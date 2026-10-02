import { format } from "date-fns"
import {
  CartesianGrid,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  type TooltipContentProps,
  XAxis,
  YAxis,
} from "recharts"

import type { PostPerformanceReport } from "@/client"
import { formatMetric, POST_METRICS, type PostMetric } from "./benchmarks"

interface Point {
  id: string
  time: number
  value: number
  text?: string | null
}

// The benchmark lines, labelled so they don't rely on colour alone
const BANDS = [
  {
    key: "p95",
    label: "P95",
    color: "oklch(0.627 0.194 149.214)" /* green-600 */,
    dash: "6 4",
  },
  {
    key: "p50",
    label: "Median",
    color: "var(--muted-foreground)",
    dash: "2 4",
  },
  { key: "p5", label: "P5", color: "var(--destructive)", dash: "6 4" },
] as const

function PointTooltip({
  active,
  payload,
  metric,
}: TooltipContentProps & { metric: PostMetric }) {
  const point = payload?.[0]?.payload as Point | undefined
  if (!active || !point) return null
  return (
    <div className="max-w-64 rounded-md border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-sm">
      <p className="text-muted-foreground">
        {format(point.time, "MMM d, yyyy")}
      </p>
      <p className="font-medium">
        {POST_METRICS[metric]}: {formatMetric(metric, point.value)}
      </p>
      {point.text && <p className="mt-1 line-clamp-2">{point.text}</p>}
    </div>
  )
}

/**
 * Every post of the history plotted over time for one metric, the latest
 * posts highlighted, against the P5 / median / P95 benchmark lines.
 */
export function PostHistoryChart({
  report,
  metric,
}: {
  report: PostPerformanceReport
  metric: PostMetric
}) {
  const latest = new Map(report.posts.map((post) => [post.id, post]))
  const earlier: Point[] = []
  const recent: Point[] = []
  for (const point of report.history) {
    const value = point[metric]
    if (value == null) continue
    const post = latest.get(point.id)
    const target = post ? recent : earlier
    target.push({
      id: point.id,
      time: Date.parse(point.published_at),
      value,
      text: post?.text,
    })
  }
  const benchmark = report.benchmarks[metric]

  return (
    <ResponsiveContainer width="100%" height={280}>
      <ScatterChart margin={{ top: 8, right: 56, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
        <XAxis
          type="number"
          dataKey="time"
          scale="time"
          domain={["dataMin", "dataMax"]}
          tickFormatter={(time: number) => format(time, "MMM d")}
          tick={{ fontSize: 11 }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          type="number"
          dataKey="value"
          tickFormatter={(value: number) => formatMetric(metric, value)}
          tick={{ fontSize: 11 }}
          tickLine={false}
          axisLine={false}
          width={52}
        />
        <Tooltip
          content={(props) => <PointTooltip {...props} metric={metric} />}
          cursor={false}
        />
        <Legend
          iconSize={10}
          wrapperStyle={{ fontSize: 12 }}
          formatter={(value) => (
            <span className="text-foreground">{value}</span>
          )}
        />
        {benchmark &&
          BANDS.map(({ key, label, color, dash }) => (
            <ReferenceLine
              key={key}
              y={benchmark[key]}
              stroke={color}
              strokeDasharray={dash}
              ifOverflow="extendDomain"
              label={{
                value: label,
                position: "right",
                fontSize: 11,
                fill: "var(--muted-foreground)",
              }}
            />
          ))}
        <Scatter
          name="Earlier posts"
          data={earlier}
          fill="var(--muted-foreground)"
          fillOpacity={0.35}
          isAnimationActive={false}
        />
        <Scatter
          name="Latest posts"
          data={recent}
          fill="var(--chart-1)"
          stroke="var(--background)"
          strokeWidth={2}
          isAnimationActive={false}
        />
      </ScatterChart>
    </ResponsiveContainer>
  )
}
