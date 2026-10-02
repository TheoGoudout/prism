import { createFileRoute } from "@tanstack/react-router"

import type { Platform, PostPublic } from "@/client"
import { InsightsPanel } from "@/components/Analytics/InsightsPanel"
import { MetricsTable } from "@/components/Analytics/MetricsTable"
import { TrendChart } from "@/components/Analytics/TrendChart"
import { KpiCards } from "@/components/Common/KpiCards"
import { SkeletonRows } from "@/components/Common/SkeletonRows"
import { PlatformIcon } from "@/components/Integrations/PlatformIcon"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useCurrentWorkspace } from "@/contexts/WorkspaceContext"
import {
  useMetricsSummary,
  useMetricsTimeseries,
  useTopPosts,
} from "@/hooks/useMetrics"
import { formatPercent, lastDays } from "@/lib/format"
import { platformLabel } from "@/lib/platforms"

export const Route = createFileRoute("/_layout/analytics")({
  component: AnalyticsPage,
  head: () => ({
    meta: [{ title: "Analytics - Prism" }],
  }),
})

function PostLabel({ post }: { post: PostPublic }) {
  const text = post.text?.slice(0, 80) ?? post.external_id
  return (
    <div className="flex items-center gap-2">
      <PlatformIcon platform={post.platform} className="size-5 shrink-0" />
      <Badge variant="secondary" className="shrink-0 text-xs capitalize">
        {post.content_type}
      </Badge>
      {post.permalink ? (
        <a
          href={post.permalink}
          target="_blank"
          rel="noopener noreferrer"
          className="block truncate text-sm hover:underline"
        >
          {text}
        </a>
      ) : (
        <span className="block truncate text-sm text-muted-foreground">
          {text}
        </span>
      )}
    </div>
  )
}

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
          "exposures",
          "reach",
          "engagements",
          "engagement_rate",
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
                "Views",
                "Reach",
                "Engagements",
                "Engagement rate",
                "Clicks",
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
                  totals.exposures,
                  totals.reach,
                  totals.engagements,
                  formatPercent(totals.engagement_rate),
                  totals.clicks,
                  totals.followers_count,
                ],
              }))}
            />
            <p className="mt-3 text-xs text-muted-foreground">
              Every platform uses the same definitions. Views are impressions
              where a platform has no views; engagements are likes, comments,
              shares and saves (engaged sessions for websites). Platforms
              without daily figures count each post on the day it was published.
            </p>
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
                "Views",
                "Engagements",
                "Engagement rate",
                "Likes",
                "Comments",
                "Shares",
              ]}
              rows={posts.data.map((post) => ({
                key: post.id,
                label: <PostLabel post={post} />,
                values: [
                  post.views ?? post.impressions,
                  post.engagements,
                  formatPercent(post.engagement_rate),
                  post.likes,
                  post.comments,
                  post.shares,
                ],
              }))}
            />
          )}
        </CardContent>
      </Card>
    </div>
  )
}
