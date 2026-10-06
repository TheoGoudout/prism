import { createFileRoute } from "@tanstack/react-router"
import { useState } from "react"

import type { Platform, TopPostRanking } from "@/client"
import { FollowersTable } from "@/components/Analytics/FollowersTable"
import { InsightsPanel } from "@/components/Analytics/InsightsPanel"
import { MetricsTable } from "@/components/Analytics/MetricsTable"
import {
  PeriodControls,
  type PeriodSelection,
} from "@/components/Analytics/PeriodControls"
import { TrendChart } from "@/components/Analytics/TrendChart"
import { KpiCards, type KpiCardsProps } from "@/components/Common/KpiCards"
import { SkeletonRows } from "@/components/Common/SkeletonRows"
import { PlatformIcon } from "@/components/Integrations/PlatformIcon"
import { PostLabel } from "@/components/Posts/PostLabel"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useCurrentWorkspace } from "@/contexts/WorkspaceContext"
import {
  useFollowers,
  useMetricsSummary,
  useMetricsTimeseries,
  useTopPosts,
} from "@/hooks/useMetrics"
import {
  type ClosedPeriod,
  type ComparisonBasis,
  compareKpi,
  comparisonBasis,
  type Day,
  formatDay,
  formatPeriod,
  isDay,
  type KpiMetric,
  lastDaysPeriod,
  type Period,
  periodEnd,
  periodLength,
  projectTotals,
  today,
} from "@/lib/comparison"
import { type DateRange, formatPercent } from "@/lib/format"
import { platformLabel } from "@/lib/platforms"

/** The periods, in the URL so that a comparison can be shared. */
interface AnalyticsSearch {
  from?: Day
  to?: Day
  compareFrom?: Day
  compareTo?: Day
}

const KPI_METRICS: KpiMetric[] = [
  "exposures",
  "reach",
  "engagements",
  "engagement_rate",
  "followers_count",
  "followers_growth",
]

const day = (value: unknown) => (isDay(value) ? value : undefined)

export const Route = createFileRoute("/_layout/analytics")({
  component: AnalyticsPage,
  validateSearch: (search: Record<string, unknown>): AnalyticsSearch => ({
    from: day(search.from),
    to: day(search.to),
    compareFrom: day(search.compareFrom),
    compareTo: day(search.compareTo),
  }),
  head: () => ({
    meta: [{ title: "Analytics - Prism" }],
  }),
})

/** The periods the search params describe; an invalid end is dropped. */
function periods(search: AnalyticsSearch, now: Day) {
  const from = search.from && search.from <= now ? search.from : undefined
  const main: Period = from
    ? {
        from,
        to:
          search.to && search.to >= from && search.to < now
            ? search.to
            : undefined,
      }
    : lastDaysPeriod(30, now)
  let compare: ClosedPeriod | null = null
  if (search.compareFrom && search.compareTo) {
    const [start, end] = [search.compareFrom, search.compareTo].sort()
    compare = { from: start, to: end > now ? now : end }
  }
  return { main, compare }
}

function basisNote(
  basis: ComparisonBasis,
  main: Period,
  compare: ClosedPeriod,
  now: Day,
): string | null {
  const mainLabel = formatPeriod(main, now)
  const compareLabel = formatPeriod(compare, now)
  switch (basis.kind) {
    case "total":
      return null
    case "projected":
      return `${mainLabel} is projected at its current pace (from its ${basis.completeDays} complete days) to ${basis.length} days, the length of ${compareLabel}. Followers follow their current trend; rates aren't projected.`
    case "perDay":
      return basis.tooEarly
        ? `Too few complete days to project ${mainLabel} yet: counts are compared per day.`
        : "The periods have different lengths: counts are compared per day."
  }
}

function AnalyticsPage() {
  const workspace = useCurrentWorkspace()
  const search = Route.useSearch()
  const navigate = Route.useNavigate()
  const now = today()
  const { main, compare } = periods(search, now)

  const range: DateRange = { dateFrom: main.from, dateTo: periodEnd(main, now) }
  const compareRange: DateRange | null = compare
    ? { dateFrom: compare.from, dateTo: compare.to }
    : null

  const summary = useMetricsSummary(range)
  const timeseries = useMetricsTimeseries(range)
  const [ranking, setRanking] = useState<TopPostRanking>("engagements")
  const posts = useTopPosts(range, ranking)
  const followers = useFollowers(range)
  const compareSummary = useMetricsSummary(compareRange)
  const compareTimeseries = useMetricsTimeseries(compareRange)
  const compareFollowers = useFollowers(compareRange)
  const byPlatform = Object.entries(summary.data?.by_platform ?? {})

  const basis = compare ? comparisonBasis(main, compare, now) : null

  let comparison: KpiCardsProps["comparison"]
  const projectionReady =
    basis?.kind !== "projected" || (timeseries.data && followers.data)
  if (
    compare &&
    basis &&
    summary.data &&
    compareSummary.data &&
    projectionReady
  ) {
    const projections =
      basis.kind === "projected"
        ? projectTotals(timeseries.data!, followers.data!, main.from, basis)
        : {}
    const context = {
      main: summary.data.totals,
      compare: compareSummary.data.totals,
      basis,
      projections,
      mainLength: periodLength(main, now),
      compareLength: periodLength(compare, now),
    }
    comparison = {
      label: formatPeriod(compare, now),
      projectedTo:
        basis.kind === "projected" ? formatDay(basis.end, now) : undefined,
      metrics: Object.fromEntries(
        KPI_METRICS.map((metric) => [metric, compareKpi(metric, context)]),
      ),
    }
  }

  const select = (selection: PeriodSelection) =>
    navigate({
      search: {
        from: selection.main.from,
        to: selection.main.to,
        compareFrom: selection.compareFrom,
        compareTo: selection.compareTo,
      },
      replace: true,
    })

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Analytics</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {formatPeriod(main, now)}
          {compare && ` vs ${formatPeriod(compare, now)}`} · {workspace.name}
        </p>
      </div>

      <PeriodControls
        now={now}
        selection={{
          main,
          compareFrom: search.compareFrom,
          compareTo: search.compareTo,
        }}
        onChange={select}
      />
      {compare && basis && basisNote(basis, main, compare, now) && (
        <p className="-mt-3 text-xs text-muted-foreground">
          {basisNote(basis, main, compare, now)}
        </p>
      )}

      <KpiCards
        className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6"
        metrics={KPI_METRICS}
        totals={summary.data?.totals}
        loading={summary.isLoading || (!!compare && compareSummary.isLoading)}
        comparison={comparison}
      />

      <InsightsPanel range={range} />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Trend</CardTitle>
        </CardHeader>
        <CardContent>
          <TrendChart
            main={main}
            mainPoints={timeseries.data ?? []}
            mainFollowers={followers.data ?? []}
            compare={compare}
            comparePoints={compareTimeseries.data ?? []}
            compareFollowers={compareFollowers.data ?? []}
            basis={basis}
            now={now}
            loading={
              timeseries.isLoading ||
              followers.isLoading ||
              (!!compare &&
                (compareTimeseries.isLoading || compareFollowers.isLoading))
            }
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

      {byPlatform.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Followers</CardTitle>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <FollowersTable
              byPlatform={summary.data?.by_platform ?? {}}
              series={followers.data ?? []}
            />
            <p className="mt-3 text-xs text-muted-foreground">
              Growth is the latest follower count minus the first one in the
              period. Most platforms only report today's total, so their history
              builds up from the first sync.
            </p>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-base">Top posts</CardTitle>
          <Tabs
            value={ranking}
            onValueChange={(value) => setRanking(value as TopPostRanking)}
          >
            <TabsList>
              <TabsTrigger value="engagements">Most engagements</TabsTrigger>
              <TabsTrigger value="account">Best for their account</TabsTrigger>
            </TabsList>
          </Tabs>
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
                "Vs account",
              ]}
              rows={posts.data.map((post) => ({
                key: post.id,
                label: <PostLabel post={post} showPlatform />,
                values: [
                  post.views ?? post.impressions,
                  post.engagements,
                  formatPercent(post.engagement_rate),
                  post.likes,
                  post.comments,
                  post.shares,
                  post.account_percentile == null
                    ? "–"
                    : `P${Math.round(post.account_percentile)}`,
                ],
              }))}
            />
          )}
          {!!posts.data?.length && (
            <p className="mt-3 text-xs text-muted-foreground">
              Vs account ranks a post's engagements among its own account's
              posts of the past year: P90 beats 90% of them. Ranking by it puts
              each account on the same footing, whatever the size of its
              audience.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
