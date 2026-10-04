import { useState } from "react"
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  type TooltipContentProps,
  XAxis,
  YAxis,
} from "recharts"

import type { PlatformFollowers, TimeSeriesPoint } from "@/client"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  type ClosedPeriod,
  type ComparisonBasis,
  type Period,
  type TrendMetric,
  type TrendRow,
  trendRows,
} from "@/lib/comparison"
import { formatCompact } from "@/lib/format"

// Theme chart colours (defined in index.css; they adapt to dark mode), the
// same as each metric's KPI card
const METRICS: { key: TrendMetric; name: string; color: string }[] = [
  { key: "exposures", name: "Views", color: "var(--chart-1)" },
  { key: "reach", name: "Reach", color: "var(--chart-2)" },
  { key: "engagements", name: "Engagements", color: "var(--chart-3)" },
  { key: "followers", name: "Followers", color: "var(--chart-5)" },
]

type Mode = "daily" | "cumulative"

function TrendTooltip({
  active,
  payload,
  metricName,
}: TooltipContentProps<number, string> & { metricName: string }) {
  const row = payload?.[0]?.payload as TrendRow | undefined
  if (!active || !row) return null
  const lines = [
    { label: row.mainDate, value: row.main },
    { label: `${row.mainDate} (projected)`, value: row.projected },
    { label: row.compareDate, value: row.compare },
  ].filter((line) => line.label && line.value != null)
  return (
    <div className="rounded-md border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-sm">
      <p className="mb-1 text-muted-foreground">
        {metricName} · day {row.day}
      </p>
      {lines.map((line) => (
        <p key={line.label} className="flex justify-between gap-4">
          <span className="text-muted-foreground">{line.label}</span>
          <span className="font-medium tabular-nums">
            {formatCompact(Math.round(line.value!))}
          </span>
        </p>
      ))}
    </div>
  )
}

/**
 * One metric per day over the period. With a comparison period, that period
 * is drawn dashed and aligned on its first day; a projection of the main
 * period continues it dotted.
 */
export function TrendChart({
  main,
  mainPoints,
  mainFollowers,
  compare,
  comparePoints,
  compareFollowers,
  basis,
  now,
  loading,
}: {
  main: Period
  mainPoints: TimeSeriesPoint[]
  mainFollowers: PlatformFollowers[]
  compare: ClosedPeriod | null
  comparePoints: TimeSeriesPoint[]
  compareFollowers: PlatformFollowers[]
  basis: ComparisonBasis | null
  now: string
  loading: boolean
}) {
  const [metric, setMetric] = useState<TrendMetric>("exposures")
  const [mode, setMode] = useState<Mode | null>(null)
  // Running totals show best whether a period is ahead of the other one
  const effectiveMode: Mode = mode ?? (compare ? "cumulative" : "daily")
  // Followers are a level: a running total of them means nothing
  const cumulative = metric !== "followers" && effectiveMode === "cumulative"
  const { name, color } = METRICS.find((m) => m.key === metric)!

  const rows = trendRows({
    metric,
    cumulative,
    main,
    mainPoints,
    mainFollowers,
    compare,
    comparePoints,
    compareFollowers,
    basis,
    now,
  })
  const hasProjection = rows.some((row) => row.projected != null)

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Tabs
          value={metric}
          onValueChange={(value) => setMetric(value as TrendMetric)}
        >
          <TabsList>
            {METRICS.map((m) => (
              <TabsTrigger key={m.key} value={m.key}>
                {m.name}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        {metric !== "followers" && (
          <Tabs
            value={effectiveMode}
            onValueChange={(value) => setMode(value as Mode)}
          >
            <TabsList>
              <TabsTrigger value="daily">Daily</TabsTrigger>
              <TabsTrigger value="cumulative">Cumulative</TabsTrigger>
            </TabsList>
          </Tabs>
        )}
      </div>
      {loading ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <ResponsiveContainer width="100%" height={260}>
          <LineChart
            data={rows}
            margin={{ top: 4, right: 16, left: 0, bottom: 0 }}
          >
            <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
            <XAxis
              dataKey="mainDate"
              tickFormatter={(date: string) => date.slice(5)} // MM-DD
              tick={{ fontSize: 11 }}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              tickFormatter={formatCompact}
              tick={{ fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              width={48}
              domain={metric === "followers" ? ["auto", "auto"] : [0, "auto"]}
            />
            <Tooltip
              content={(props) => (
                <TrendTooltip
                  {...(props as TooltipContentProps<number, string>)}
                  metricName={name}
                />
              )}
            />
            <Legend iconSize={10} wrapperStyle={{ fontSize: 12 }} />
            <Line
              type="monotone"
              dataKey="main"
              name={name}
              stroke={color}
              dot={false}
              strokeWidth={2}
              connectNulls
            />
            {hasProjection && (
              <Line
                type="monotone"
                dataKey="projected"
                name="Projected"
                stroke={color}
                strokeDasharray="2 4"
                dot={false}
                strokeWidth={2}
              />
            )}
            {compare && (
              <Line
                type="monotone"
                dataKey="compare"
                name="Comparison period"
                stroke={color}
                strokeOpacity={0.45}
                strokeDasharray="6 4"
                dot={false}
                strokeWidth={2}
                connectNulls
              />
            )}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
