import { useQuery } from "@tanstack/react-query"

import { MetricsService, type TopPostRanking } from "@/client"
import { useCurrentWorkspace } from "@/contexts/WorkspaceContext"
import type { DateRange } from "@/lib/format"

/** Query params selecting the current workspace's metrics over a date range. */
export function useMetricsParams(range: DateRange | null) {
  const workspace = useCurrentWorkspace()
  return { workspaceId: workspace.id, ...range }
}

/** `null` range: nothing to fetch (e.g. no comparison period). */
export function useMetricsSummary(range: DateRange | null) {
  const params = useMetricsParams(range)
  return useQuery({
    queryKey: ["metrics", "summary", params],
    queryFn: () => MetricsService.getSummary(params),
    enabled: range !== null,
  })
}

export function useMetricsTimeseries(range: DateRange | null) {
  const params = useMetricsParams(range)
  return useQuery({
    queryKey: ["metrics", "timeseries", params],
    queryFn: () => MetricsService.getTimeseries(params),
    enabled: range !== null,
  })
}

export function useFollowers(range: DateRange | null) {
  const params = useMetricsParams(range)
  return useQuery({
    queryKey: ["metrics", "followers", params],
    queryFn: () => MetricsService.getFollowers(params),
    enabled: range !== null,
  })
}

export function useTopPosts(
  range: DateRange,
  ranking: TopPostRanking = "engagements",
  limit = 10,
) {
  const params = { ...useMetricsParams(range), ranking, limit }
  return useQuery({
    queryKey: ["metrics", "posts", params],
    queryFn: () => MetricsService.getTopPosts(params),
  })
}

/** Each account's latest posts, benchmarked against its post history. */
export function usePostPerformance(limit = 20) {
  const workspace = useCurrentWorkspace()
  const params = { workspaceId: workspace.id, limit }
  return useQuery({
    queryKey: ["metrics", "post-performance", params],
    queryFn: () => MetricsService.getPostPerformance(params),
  })
}
