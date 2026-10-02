import { useQuery } from "@tanstack/react-query"

import { MetricsService } from "@/client"
import { useCurrentWorkspace } from "@/contexts/WorkspaceContext"
import type { DateRange } from "@/lib/format"

/** Query params selecting the current workspace's metrics over a date range. */
export function useMetricsParams(range: DateRange) {
  const workspace = useCurrentWorkspace()
  return { workspaceId: workspace.id, ...range }
}

export function useMetricsSummary(range: DateRange) {
  const params = useMetricsParams(range)
  return useQuery({
    queryKey: ["metrics", "summary", params],
    queryFn: () => MetricsService.getSummary(params),
  })
}

export function useMetricsTimeseries(range: DateRange) {
  const params = useMetricsParams(range)
  return useQuery({
    queryKey: ["metrics", "timeseries", params],
    queryFn: () => MetricsService.getTimeseries(params),
  })
}

export function useFollowers(range: DateRange) {
  const params = useMetricsParams(range)
  return useQuery({
    queryKey: ["metrics", "followers", params],
    queryFn: () => MetricsService.getFollowers(params),
  })
}

export function useTopPosts(range: DateRange, limit = 10) {
  const params = { ...useMetricsParams(range), limit }
  return useQuery({
    queryKey: ["metrics", "posts", params],
    queryFn: () => MetricsService.getTopPosts(params),
  })
}
