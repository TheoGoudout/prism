import { useQuery } from "@tanstack/react-query"

import type { AnalysisStatus } from "@/client"
import { AnalysesService } from "@/client"
import { useCurrentWorkspace } from "@/contexts/WorkspaceContext"

const POLL_MS = 4000

export const isUnfinished = (status: AnalysisStatus) =>
  status === "pending" || status === "running"

/** The workspace's analyses, refreshed while one of them is still running. */
export function useAnalyses() {
  const workspace = useCurrentWorkspace()
  return useQuery({
    queryKey: ["analyses", workspace.id],
    queryFn: () =>
      AnalysesService.listAnalyses({ workspaceId: workspace.id, limit: 50 }),
    refetchInterval: (query) =>
      query.state.data?.data.some((a) => isUnfinished(a.status))
        ? POLL_MS
        : false,
  })
}

/** One analysis with its result, polled until it completes or fails. */
export function useAnalysis(analysisId: string | undefined) {
  const workspace = useCurrentWorkspace()
  return useQuery({
    queryKey: ["analyses", workspace.id, analysisId],
    queryFn: () =>
      AnalysesService.readAnalysis({
        workspaceId: workspace.id,
        analysisId: analysisId as string,
      }),
    enabled: !!analysisId,
    refetchInterval: (query) =>
      query.state.data && isUnfinished(query.state.data.status)
        ? POLL_MS
        : false,
  })
}

export function useAnalysisSchedule() {
  const workspace = useCurrentWorkspace()
  return useQuery({
    queryKey: ["analysis-schedule", workspace.id],
    queryFn: () => AnalysesService.readSchedule({ workspaceId: workspace.id }),
  })
}
