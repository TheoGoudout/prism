import { Line, LineChart, Tooltip, YAxis } from "recharts"

import type {
  FollowersPoint,
  MetricTotals,
  Platform,
  PlatformFollowers,
} from "@/client"
import { PlatformIcon } from "@/components/Integrations/PlatformIcon"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { formatCompact, formatSigned, formatSignedPercent } from "@/lib/format"
import { platformLabel } from "@/lib/platforms"

/** A platform's follower count over the range, one series in one colour. */
function Sparkline({ points }: { points: FollowersPoint[] }) {
  if (points.length < 2) {
    return <span className="text-xs text-muted-foreground">Building up</span>
  }
  return (
    <LineChart
      width={120}
      height={32}
      data={points}
      margin={{ top: 4, right: 4, bottom: 4, left: 4 }}
      aria-label="Follower count over the period"
    >
      {/* Scaled to the series' own range: growth is a few percent at most */}
      <YAxis hide domain={["dataMin", "dataMax"]} />
      <Line
        type="monotone"
        dataKey="followers"
        stroke="var(--series-1)"
        strokeWidth={2}
        dot={false}
        isAnimationActive={false}
      />
      <Tooltip
        cursor={{ stroke: "var(--border)" }}
        formatter={(value) => [formatCompact(value as number), "Followers"]}
        labelFormatter={(_, payload) => payload?.[0]?.payload?.date ?? ""}
        contentStyle={{
          fontSize: 12,
          borderRadius: 6,
          background: "var(--popover)",
          borderColor: "var(--border)",
        }}
        labelStyle={{ color: "var(--muted-foreground)" }}
        itemStyle={{ color: "var(--popover-foreground)" }}
        wrapperStyle={{ zIndex: 10 }}
      />
    </LineChart>
  )
}

/**
 * Follower count and growth per platform. Platforms without followers
 * (Google Analytics) are left out.
 */
export function FollowersTable({
  byPlatform,
  series,
}: {
  byPlatform: Record<string, MetricTotals>
  series: PlatformFollowers[]
}) {
  const rows = Object.entries(byPlatform)
    .filter(([, totals]) => totals.followers_count != null)
    .sort(([, a], [, b]) => (b.followers_count ?? 0) - (a.followers_count ?? 0))

  if (rows.length === 0) {
    return (
      <p className="py-4 text-center text-sm text-muted-foreground">
        No follower data for this period.
      </p>
    )
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Platform</TableHead>
          <TableHead className="text-right">Followers</TableHead>
          <TableHead className="text-right">Growth</TableHead>
          <TableHead className="text-right">Growth rate</TableHead>
          <TableHead className="text-right">Trend</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map(([platform, totals]) => (
          <TableRow key={platform}>
            <TableCell>
              <span className="flex items-center gap-2">
                <PlatformIcon
                  platform={platform as Platform}
                  className="size-6"
                />
                {platformLabel(platform)}
              </span>
            </TableCell>
            <TableCell className="text-right">
              {formatCompact(totals.followers_count)}
            </TableCell>
            <TableCell className="text-right">
              {formatSigned(totals.followers_growth)}
            </TableCell>
            <TableCell className="text-right">
              {formatSignedPercent(totals.followers_growth_rate)}
            </TableCell>
            <TableCell>
              <div className="flex justify-end">
                <Sparkline
                  points={
                    series.find((s) => s.platform === platform)?.points ?? []
                  }
                />
              </div>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
