import { useMutation, useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { format, subDays } from "date-fns"
import {
  BarChart2,
  Download,
  Eye,
  Heart,
  Loader2,
  MousePointerClick,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Users,
} from "lucide-react"
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import type { Insight } from "@/client"
import { AiService, MetricsService } from "@/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useWorkspace } from "@/contexts/WorkspaceContext"

export const Route = createFileRoute("/_layout/analytics")({
  component: AnalyticsPage,
  head: () => ({
    meta: [{ title: "Analytics - Prism" }],
  }),
})

// ---- helpers ----------------------------------------------------------------

function fmt(n: number | undefined | null): string {
  if (n == null) return "—"
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return n.toString()
}

function defaultRange() {
  const to = new Date()
  const from = subDays(to, 29)
  return {
    dateFrom: format(from, "yyyy-MM-dd"),
    dateTo: format(to, "yyyy-MM-dd"),
  }
}

// ---- KPI Card ---------------------------------------------------------------

interface KpiCardProps {
  title: string
  value: string
  icon: React.ElementType
  loading?: boolean
}

function KpiCard({ title, value, icon: Icon, loading }: KpiCardProps) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {title}
        </CardTitle>
        <Icon className="size-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-7 w-24" />
        ) : (
          <p className="text-2xl font-bold">{value}</p>
        )}
      </CardContent>
    </Card>
  )
}

// ---- Insights panel ---------------------------------------------------------

function insightIcon(type: Insight["type"]) {
  if (type === "positive")
    return <TrendingUp className="size-4 text-green-500 shrink-0 mt-0.5" />
  if (type === "negative")
    return <TrendingDown className="size-4 text-destructive shrink-0 mt-0.5" />
  return <Sparkles className="size-4 text-muted-foreground shrink-0 mt-0.5" />
}

interface InsightsPanelProps {
  workspaceId: string
  dateFrom: string
  dateTo: string
}

function InsightsPanel({ workspaceId, dateFrom, dateTo }: InsightsPanelProps) {
  const insightsMut = useMutation({
    mutationFn: () =>
      AiService.generateInsights({
        requestBody: {
          workspace_id: workspaceId,
          date_from: dateFrom,
          date_to: dateTo,
        },
      }),
  })

  const reportMut = useMutation({
    mutationFn: () =>
      AiService.generateReport({
        requestBody: {
          workspace_id: workspaceId,
          date_from: dateFrom,
          date_to: dateTo,
        },
      }),
    onSuccess: (data) => {
      // Trigger a markdown file download
      const blob = new Blob([data.report], { type: "text/markdown" })
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `report-${dateFrom}-${dateTo}.md`
      a.click()
      URL.revokeObjectURL(url)
    },
  })

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base flex items-center gap-2">
          <Sparkles className="size-4" />
          AI Insights
        </CardTitle>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => insightsMut.mutate()}
            disabled={insightsMut.isPending || reportMut.isPending}
          >
            {insightsMut.isPending ? (
              <Loader2 className="mr-2 size-4 animate-spin" />
            ) : (
              <Sparkles className="mr-2 size-4" />
            )}
            Generate insights
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => reportMut.mutate()}
            disabled={insightsMut.isPending || reportMut.isPending}
          >
            {reportMut.isPending ? (
              <Loader2 className="mr-2 size-4 animate-spin" />
            ) : (
              <Download className="mr-2 size-4" />
            )}
            Download report
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {!insightsMut.data && !insightsMut.isPending && (
          <p className="text-sm text-muted-foreground text-center py-4">
            Click "Generate insights" to get AI-powered analysis of your
            metrics.
          </p>
        )}
        {insightsMut.isPending && (
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-14 w-full" />
            ))}
          </div>
        )}
        {insightsMut.isError && (
          <p className="text-sm text-destructive text-center py-4">
            Failed to generate insights. Please try again.
          </p>
        )}
        {insightsMut.data && (
          <ul className="space-y-3">
            {insightsMut.data.insights.map((insight, i) => (
              <li key={i} className="flex gap-3 text-sm">
                {insightIcon(insight.type)}
                <div>
                  <p className="font-medium">{insight.title}</p>
                  <p className="text-muted-foreground">{insight.body}</p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

// ---- Main page --------------------------------------------------------------

function AnalyticsPage() {
  const { currentWorkspace } = useWorkspace()
  const { dateFrom, dateTo } = defaultRange()

  const queryOpts = {
    enabled: !!currentWorkspace,
    workspaceId: currentWorkspace?.id ?? "",
    dateFrom,
    dateTo,
  }

  const summaryQ = useQuery({
    queryKey: ["metrics", "summary", currentWorkspace?.id, dateFrom, dateTo],
    queryFn: () => MetricsService.getSummary(queryOpts),
    enabled: !!currentWorkspace,
  })

  const timeseriesQ = useQuery({
    queryKey: ["metrics", "timeseries", currentWorkspace?.id, dateFrom, dateTo],
    queryFn: () => MetricsService.getTimeseries(queryOpts),
    enabled: !!currentWorkspace,
  })

  const postsQ = useQuery({
    queryKey: ["metrics", "posts", currentWorkspace?.id, dateFrom, dateTo],
    queryFn: () => MetricsService.getTopPosts({ ...queryOpts, limit: 10 }),
    enabled: !!currentWorkspace,
  })

  const totals = summaryQ.data?.totals
  const chartData =
    timeseriesQ.data?.data.map((p) => ({
      date: p.date.slice(5), // MM-DD
      impressions: p.impressions ?? 0,
      views: p.views ?? 0,
      engagements: p.engagements ?? 0,
      reach: p.reach ?? 0,
    })) ?? []

  if (!currentWorkspace) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-3 text-muted-foreground">
        <BarChart2 className="size-10" />
        <p>Select a workspace to view analytics.</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Analytics</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Last 30 days · {currentWorkspace.name}
        </p>
      </div>

      {/* KPI cards */}
      <div className="grid gap-4 grid-cols-2 md:grid-cols-3 lg:grid-cols-6">
        <KpiCard
          title="Impressions"
          value={fmt(totals?.impressions)}
          icon={Eye}
          loading={summaryQ.isLoading}
        />
        <KpiCard
          title="Reach"
          value={fmt(totals?.reach)}
          icon={TrendingUp}
          loading={summaryQ.isLoading}
        />
        <KpiCard
          title="Views"
          value={fmt(totals?.views)}
          icon={Eye}
          loading={summaryQ.isLoading}
        />
        <KpiCard
          title="Engagements"
          value={fmt(totals?.engagements)}
          icon={Heart}
          loading={summaryQ.isLoading}
        />
        <KpiCard
          title="Clicks"
          value={fmt(totals?.clicks)}
          icon={MousePointerClick}
          loading={summaryQ.isLoading}
        />
        <KpiCard
          title="Followers"
          value={fmt(totals?.followers_count)}
          icon={Users}
          loading={summaryQ.isLoading}
        />
      </div>

      {/* AI Insights */}
      <InsightsPanel
        workspaceId={currentWorkspace.id}
        dateFrom={dateFrom}
        dateTo={dateTo}
      />

      {/* Timeseries chart */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Trend</CardTitle>
        </CardHeader>
        <CardContent>
          {timeseriesQ.isLoading ? (
            <Skeleton className="h-64 w-full" />
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <LineChart
                data={chartData}
                margin={{ top: 4, right: 16, left: 0, bottom: 0 }}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  className="stroke-border"
                />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  tickFormatter={fmt}
                  tick={{ fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                  width={48}
                />
                <Tooltip
                  formatter={(v) => fmt(v as number)}
                  contentStyle={{
                    fontSize: 12,
                    borderRadius: 6,
                  }}
                />
                <Legend iconSize={10} wrapperStyle={{ fontSize: 12 }} />
                <Line
                  type="monotone"
                  dataKey="impressions"
                  stroke="hsl(var(--primary))"
                  dot={false}
                  strokeWidth={2}
                />
                <Line
                  type="monotone"
                  dataKey="views"
                  stroke="hsl(32 95% 44%)"
                  dot={false}
                  strokeWidth={2}
                />
                <Line
                  type="monotone"
                  dataKey="engagements"
                  stroke="hsl(221 83% 53%)"
                  dot={false}
                  strokeWidth={2}
                />
                <Line
                  type="monotone"
                  dataKey="reach"
                  stroke="hsl(142 76% 36%)"
                  dot={false}
                  strokeWidth={2}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      {/* Per-platform breakdown */}
      {summaryQ.data && Object.keys(summaryQ.data.by_platform).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">By platform</CardTitle>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Platform</TableHead>
                  <TableHead className="text-right">Impressions</TableHead>
                  <TableHead className="text-right">Views</TableHead>
                  <TableHead className="text-right">Reach</TableHead>
                  <TableHead className="text-right">Engagements</TableHead>
                  <TableHead className="text-right">Followers</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {Object.entries(summaryQ.data.by_platform).map(
                  ([platform, m]) => (
                    <TableRow key={platform}>
                      <TableCell>
                        <Badge variant="outline" className="capitalize">
                          {platform}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        {fmt(m.impressions)}
                      </TableCell>
                      <TableCell className="text-right">
                        {fmt(m.views)}
                      </TableCell>
                      <TableCell className="text-right">
                        {fmt(m.reach)}
                      </TableCell>
                      <TableCell className="text-right">
                        {fmt(m.engagements)}
                      </TableCell>
                      <TableCell className="text-right">
                        {fmt(m.followers_count)}
                      </TableCell>
                    </TableRow>
                  ),
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Top posts */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Top posts</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          {postsQ.isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : postsQ.data?.count === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">
              No posts found for this period.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Content</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead className="text-right">Impressions</TableHead>
                  <TableHead className="text-right">Views</TableHead>
                  <TableHead className="text-right">Engagements</TableHead>
                  <TableHead className="text-right">Likes</TableHead>
                  <TableHead className="text-right">Comments</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {postsQ.data?.data.map((post) => (
                  <TableRow key={post.id}>
                    <TableCell className="max-w-xs">
                      {post.permalink ? (
                        <a
                          href={post.permalink}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="truncate block text-sm hover:underline"
                        >
                          {post.text?.slice(0, 80) ?? post.external_id}
                        </a>
                      ) : (
                        <span className="truncate block text-sm text-muted-foreground">
                          {post.text?.slice(0, 80) ?? post.external_id}
                        </span>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary" className="capitalize text-xs">
                        {post.content_type}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      {fmt(post.impressions)}
                    </TableCell>
                    <TableCell className="text-right">
                      {fmt(post.views)}
                    </TableCell>
                    <TableCell className="text-right">
                      {fmt(post.engagements)}
                    </TableCell>
                    <TableCell className="text-right">
                      {fmt(post.likes)}
                    </TableCell>
                    <TableCell className="text-right">
                      {fmt(post.comments)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
