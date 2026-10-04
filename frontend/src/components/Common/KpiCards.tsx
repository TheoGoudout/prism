import type { LucideIcon } from "lucide-react"
import {
  ArrowDown,
  ArrowUp,
  Eye,
  Heart,
  MousePointerClick,
  Percent,
  TrendingUp,
  UserPlus,
  Users,
} from "lucide-react"

import type { MetricTotals } from "@/client"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { formatChange, type KpiComparison } from "@/lib/comparison"
import { formatCompact, formatPercent, formatSigned } from "@/lib/format"
import { cn } from "@/lib/utils"

type KpiMetric = keyof Pick<
  MetricTotals,
  | "exposures"
  | "reach"
  | "engagements"
  | "engagement_rate"
  | "clicks"
  | "followers_count"
  | "followers_growth"
>

// The same definitions on every platform (see app.services.metrics)
const KPIS: Record<
  KpiMetric,
  {
    title: string
    hint: string
    icon: LucideIcon
    /** Accent colour; matches the metric's series in the trend chart. */
    tone: string
    format?: (value: number | null | undefined) => string
  }
> = {
  exposures: {
    tone: "var(--chart-1)",
    title: "Views",
    hint: "Or impressions, where a platform has no views",
    icon: Eye,
  },
  reach: {
    tone: "var(--chart-2)",
    title: "Reach",
    hint: "Unique people per day, summed",
    icon: TrendingUp,
  },
  engagements: {
    tone: "var(--chart-3)",
    title: "Engagements",
    hint: "Likes, comments, shares and saves",
    icon: Heart,
  },
  engagement_rate: {
    tone: "var(--chart-3)",
    title: "Engagement rate",
    hint: "Engagements per view",
    icon: Percent,
    format: formatPercent,
  },
  clicks: {
    tone: "var(--chart-4)",
    title: "Clicks",
    hint: "Link clicks and conversions",
    icon: MousePointerClick,
  },
  followers_count: {
    title: "Followers",
    hint: "Latest total",
    icon: Users,
    tone: "var(--chart-5)",
  },
  followers_growth: {
    tone: "var(--chart-5)",
    title: "Follower growth",
    hint: "Net change over the period",
    icon: UserPlus,
    format: formatSigned,
  },
}

export interface KpiCardsProps {
  metrics: KpiMetric[]
  totals: MetricTotals | undefined
  loading: boolean
  className?: string
  /** Each metric compared with another period, e.g. "+12% vs Sep 1 – Sep 30". */
  comparison?: {
    label: string
    /** Where projected figures end, e.g. "Oct 30". */
    projectedTo?: string
    metrics: Partial<Record<KpiMetric, KpiComparison>>
  }
}

function Change({
  comparison,
  label,
}: {
  comparison: KpiComparison
  label: string
}) {
  const { change, kind, perDay } = comparison
  const Arrow =
    change == null || change === 0 ? null : change > 0 ? ArrowUp : ArrowDown
  return (
    <p className="mt-1 flex flex-wrap items-center gap-x-1 text-xs text-muted-foreground">
      <span
        className={cn(
          "inline-flex items-center gap-0.5 font-medium tabular-nums",
          change != null && change > 0 && "text-success",
          change != null && change < 0 && "text-destructive",
        )}
      >
        {Arrow && <Arrow className="size-3" aria-hidden />}
        {formatChange(change, kind)}
      </span>
      {perDay && "per day "}vs {label}
    </p>
  )
}

/** One card per metric, e.g. "Views 12.3K". */
export function KpiCards({
  metrics,
  totals,
  loading,
  className,
  comparison,
}: KpiCardsProps) {
  return (
    <div className={className}>
      {metrics.map((metric) => {
        const {
          title,
          hint,
          icon: Icon,
          tone,
          format = formatCompact,
        } = KPIS[metric]
        const compared = comparison?.metrics[metric]
        return (
          <Card
            key={metric}
            className="relative overflow-hidden"
            style={{ boxShadow: `inset 0 3px 0 ${tone}` }}
          >
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                {title}
              </CardTitle>
              <span
                className="flex size-8 shrink-0 items-center justify-center rounded-lg"
                style={{
                  color: tone,
                  backgroundColor: `color-mix(in oklch, ${tone} 14%, transparent)`,
                }}
              >
                <Icon className="size-4" />
              </span>
            </CardHeader>
            <CardContent>
              {loading ? (
                <Skeleton className="h-7 w-20" />
              ) : (
                <p className="font-display text-3xl font-extrabold tracking-tight">
                  {format(totals?.[metric])}
                </p>
              )}
              {compared?.projected && !loading && (
                <p className="mt-1 text-xs text-muted-foreground">
                  ~
                  {format(
                    compared.current === null
                      ? null
                      : Math.round(compared.current),
                  )}{" "}
                  projected
                  {comparison?.projectedTo && ` by ${comparison.projectedTo}`}
                </p>
              )}
              {compared && comparison && !loading && (
                <Change comparison={compared} label={comparison.label} />
              )}
              <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}
