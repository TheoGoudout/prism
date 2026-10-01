import type { LucideIcon } from "lucide-react"
import {
  BarChart2,
  Eye,
  Heart,
  MousePointerClick,
  TrendingUp,
  Users,
} from "lucide-react"

import type { MetricTotals } from "@/client"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { formatCompact } from "@/lib/format"

type KpiMetric = keyof Pick<
  MetricTotals,
  | "impressions"
  | "views"
  | "reach"
  | "engagements"
  | "clicks"
  | "followers_count"
>

const KPIS: Record<KpiMetric, { title: string; icon: LucideIcon }> = {
  impressions: { title: "Impressions", icon: BarChart2 },
  views: { title: "Views", icon: Eye },
  reach: { title: "Reach", icon: TrendingUp },
  engagements: { title: "Engagements", icon: Heart },
  clicks: { title: "Clicks", icon: MousePointerClick },
  followers_count: { title: "Followers", icon: Users },
}

interface KpiCardsProps {
  metrics: KpiMetric[]
  totals: MetricTotals | undefined
  loading: boolean
  className?: string
}

/** One card per metric, e.g. "Impressions 12.3K". */
export function KpiCards({
  metrics,
  totals,
  loading,
  className,
}: KpiCardsProps) {
  return (
    <div className={className}>
      {metrics.map((metric) => {
        const { title, icon: Icon } = KPIS[metric]
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
                <p className="text-2xl font-bold">
                  {formatCompact(totals?.[metric])}
                </p>
              )}
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}
