import { createFileRoute, Link } from "@tanstack/react-router"
import { format, parseISO } from "date-fns"
import { useState } from "react"

import type { PostPerformanceReport } from "@/client"
import { PageHeader } from "@/components/Common/PageHeader"
import { SkeletonRows } from "@/components/Common/SkeletonRows"
import { PlatformIcon } from "@/components/Integrations/PlatformIcon"
import {
  benchmarkedMetrics,
  POST_METRICS,
  type PostMetric,
} from "@/components/Posts/benchmarks"
import { PostHistoryChart } from "@/components/Posts/PostHistoryChart"
import { PostPerformanceTable } from "@/components/Posts/PostPerformanceTable"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useCurrentWorkspace } from "@/contexts/WorkspaceContext"
import { usePostPerformance } from "@/hooks/useMetrics"
import { platformLabel } from "@/lib/platforms"
import { pageHead } from "@/lib/routing"

export const Route = createFileRoute("/_layout/posts")({
  component: PostsPage,
  validateSearch: (
    search: Record<string, unknown>,
  ): { account?: string; platform?: string } => ({
    account: typeof search.account === "string" ? search.account : undefined,
    platform: typeof search.platform === "string" ? search.platform : undefined,
  }),
  head: pageHead("Posts"),
})

function AccountReport({ report }: { report: PostPerformanceReport }) {
  const metrics = benchmarkedMetrics(report)
  const [selected, setSelected] = useState<PostMetric>()
  const chartMetric =
    selected && metrics.includes(selected) ? selected : metrics[0]
  const since = format(parseISO(report.history_from), "MMM d, yyyy")

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground">
        Compared with {report.history_size} posts published since {since}.
        Recent posts are still collecting engagement, so their rank can still
        rise.
      </p>

      {chartMetric ? (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-4 pb-2">
            <CardTitle className="text-base">Over time</CardTitle>
            <Select
              value={chartMetric}
              onValueChange={(v) => setSelected(v as PostMetric)}
            >
              <SelectTrigger className="w-40" aria-label="Metric">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {metrics.map((metric) => (
                  <SelectItem key={metric} value={metric}>
                    {POST_METRICS[metric]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </CardHeader>
          <CardContent>
            <PostHistoryChart report={report} metric={chartMetric} />
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="py-6 text-center text-sm text-muted-foreground">
            Not enough posts yet to benchmark: Prism needs at least 5 posts
            reporting a metric to compute its P5 and P95.
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Latest posts</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <PostPerformanceTable
            report={report}
            metrics={metrics}
            headline={
              metrics.includes("engagements") ? "engagements" : metrics[0]
            }
          />
        </CardContent>
      </Card>
    </div>
  )
}

function PostsPage() {
  const workspace = useCurrentWorkspace()
  const reports = usePostPerformance()
  const { account, platform } = Route.useSearch()
  const navigate = Route.useNavigate()
  const data = reports.data ?? []
  // An account, or else the first account of a platform (older links)
  const active = (
    data.find((r) => r.platform_account_id === account) ??
    data.find((r) => r.platform === platform) ??
    data[0]
  )?.platform_account_id
  // Name accounts only where a platform has several
  const platformCounts = new Map<string, number>()
  for (const r of data) {
    platformCounts.set(r.platform, (platformCounts.get(r.platform) ?? 0) + 1)
  }
  const tabLabel = (report: PostPerformanceReport) =>
    (platformCounts.get(report.platform) ?? 0) > 1
      ? report.account_name
      : platformLabel(report.platform)

  return (
    <div className="space-y-6">
      <PageHeader
        title="Posts"
        description={`Your latest posts against your best (P95) and worst (P5) posts of the last 12 months · ${workspace.name}`}
      />

      {reports.isLoading ? (
        <SkeletonRows count={6} className="h-12" />
      ) : data.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-10 text-center">
            <p className="text-sm text-muted-foreground">
              No posts yet. Connect Facebook, Instagram, Twitter / X, LinkedIn
              or TikTok to see how each post performs.
            </p>
            <Button asChild variant="outline" size="sm">
              <Link to="/integrations">Go to integrations</Link>
            </Button>
          </CardContent>
        </Card>
      ) : (
        <Tabs
          value={active}
          onValueChange={(value) =>
            navigate({ search: { account: value }, replace: true })
          }
        >
          <TabsList className="h-auto flex-wrap">
            {data.map((report) => (
              <TabsTrigger
                key={report.platform_account_id}
                value={report.platform_account_id}
              >
                <PlatformIcon
                  platform={report.platform}
                  className="size-5 rounded text-[9px]"
                />
                {tabLabel(report)}
              </TabsTrigger>
            ))}
          </TabsList>
          {data.map((report) => (
            <TabsContent
              key={report.platform_account_id}
              value={report.platform_account_id}
              className="mt-4"
            >
              <AccountReport report={report} />
            </TabsContent>
          ))}
        </Tabs>
      )}
    </div>
  )
}
