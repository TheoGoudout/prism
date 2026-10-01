import { useQuery } from "@tanstack/react-query"

import { MetricsService } from "@/client"
import { useCurrentWorkspace } from "@/contexts/WorkspaceContext"
import type { DateRange } from "@/lib/format"

/** Metrics of the current workspace over a date range. */
function useMetricsParams(range: DateRange) {
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

export function useTopPosts(range: DateRange, limit = 10) {
  const params = { ...useMetricsParams(range), limit }
  return useQuery({
    queryKey: ["metrics", "posts", params],
    queryFn: () => MetricsService.getTopPosts(params),
  })
}
