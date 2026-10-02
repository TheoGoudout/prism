import { createFileRoute } from "@tanstack/react-router"

import type { Platform } from "@/client"
import { InsightsPanel } from "@/components/Analytics/InsightsPanel"
import { MetricsTable } from "@/components/Analytics/MetricsTable"
import { TrendChart } from "@/components/Analytics/TrendChart"
import { KpiCards } from "@/components/Common/KpiCards"
import { SkeletonRows } from "@/components/Common/SkeletonRows"
import { PlatformIcon } from "@/components/Integrations/PlatformIcon"
import { PostLabel } from "@/components/Posts/PostLabel"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useCurrentWorkspace } from "@/contexts/WorkspaceContext"
import {
  useMetricsSummary,
  useMetricsTimeseries,
  useTopPosts,
} from "@/hooks/useMetrics"
import { lastDays } from "@/lib/format"
import { platformLabel } from "@/lib/platforms"

export const Route = createFileRoute("/_layout/analytics")({
  component: AnalyticsPage,
  head: () => ({
    meta: [{ title: "Analytics - Prism" }],
  }),
})

function AnalyticsPage() {
  const workspace = useCurrentWorkspace()
  const range = lastDays(30)
  const summary = useMetricsSummary(range)
  const timeseries = useMetricsTimeseries(range)
  const posts = useTopPosts(range)
  const byPlatform = Object.entries(summary.data?.by_platform ?? {})

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Analytics</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Last 30 days · {workspace.name}
        </p>
      </div>

      <KpiCards
        className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6"
        metrics={[
          "impressions",
          "reach",
          "views",
          "engagements",
          "clicks",
          "followers_count",
        ]}
        totals={summary.data?.totals}
        loading={summary.isLoading}
      />

      <InsightsPanel range={range} />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Trend</CardTitle>
        </CardHeader>
        <CardContent>
          <TrendChart
            points={timeseries.data ?? []}
            loading={timeseries.isLoading}
          />
        </CardContent>
      </Card>

      {byPlatform.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">By platform</CardTitle>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <MetricsTable
              labelHeader="Platform"
              valueHeaders={[
                "Impressions",
                "Views",
                "Reach",
                "Engagements",
                "Followers",
              ]}
              rows={byPlatform.map(([platform, totals]) => ({
                key: platform,
                label: (
                  <span className="flex items-center gap-2">
                    <PlatformIcon
                      platform={platform as Platform}
                      className="size-6"
                    />
                    {platformLabel(platform)}
                  </span>
                ),
                values: [
                  totals.impressions,
                  totals.views,
                  totals.reach,
                  totals.engagements,
                  totals.followers_count,
                ],
              }))}
            />
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Top posts</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          {posts.isLoading ? (
            <SkeletonRows count={5} className="h-10" />
          ) : !posts.data?.length ? (
            <p className="py-4 text-center text-sm text-muted-foreground">
              No posts found for this period.
            </p>
          ) : (
            <MetricsTable
              labelHeader="Content"
              valueHeaders={[
                "Impressions",
                "Views",
                "Engagements",
                "Likes",
                "Comments",
              ]}
              rows={posts.data.map((post) => ({
                key: post.id,
                label: <PostLabel post={post} />,
                values: [
                  post.impressions,
                  post.views,
                  post.engagements,
                  post.likes,
                  post.comments,
                ],
              }))}
            />
          )}
        </CardContent>
      </Card>
    </div>
  )
}
