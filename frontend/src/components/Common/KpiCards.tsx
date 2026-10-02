import type { LucideIcon } from "lucide-react"
import {
  Eye,
  Heart,
  MousePointerClick,
  Percent,
  TrendingUp,
  Users,
} from "lucide-react"

import type { MetricTotals } from "@/client"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { formatCompact, formatPercent } from "@/lib/format"

type KpiMetric = keyof Pick<
  MetricTotals,
  | "exposures"
  | "reach"
  | "engagements"
  | "engagement_rate"
  | "clicks"
  | "followers_count"
>

// The same definitions on every platform (see app.services.metrics)
const KPIS: Record<
  KpiMetric,
  {
    title: string
    hint: string
    icon: LucideIcon
    format?: (value: number | null | undefined) => string
  }
> = {
  exposures: {
    title: "Views",
    hint: "Or impressions, where a platform has no views",
    icon: Eye,
  },
  reach: {
    title: "Reach",
    hint: "Unique people per day, summed",
    icon: TrendingUp,
  },
  engagements: {
    title: "Engagements",
    hint: "Likes, comments, shares and saves",
    icon: Heart,
  },
  engagement_rate: {
    title: "Engagement rate",
    hint: "Engagements per view",
    icon: Percent,
    format: formatPercent,
  },
  clicks: {
    title: "Clicks",
    hint: "Link clicks and conversions",
    icon: MousePointerClick,
  },
  followers_count: { title: "Followers", hint: "Latest total", icon: Users },
}

interface KpiCardsProps {
  metrics: KpiMetric[]
  totals: MetricTotals | undefined
  loading: boolean
  className?: string
}

/** One card per metric, e.g. "Views 12.3K". */
export function KpiCards({
  metrics,
  totals,
  loading,
  className,
}: KpiCardsProps) {
  return (
    <div className={className}>
      {metrics.map((metric) => {
        const { title, hint, icon: Icon, format = formatCompact } = KPIS[metric]
        return (
          <Card key={metric}>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                {title}
              </CardTitle>
              <Icon className="size-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              {loading ? (
                <Skeleton className="h-7 w-20" />
              ) : (
                <p className="text-2xl font-bold">{format(totals?.[metric])}</p>
              )}
              <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}
