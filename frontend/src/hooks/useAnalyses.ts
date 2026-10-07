import { useQuery } from "@tanstack/react-query"

import type { AnalysesPublic, AnalysisPublic } from "@/client"
import { AnalysesService } from "@/client"
import { useCurrentWorkspace } from "@/contexts/WorkspaceContext"
import { pollWhileUnfinished } from "@/lib/jobs"

/** The workspace's analyses, refreshed while one of them is still running. */
export function useAnalyses() {
  const workspace = useCurrentWorkspace()
  return useQuery({
    queryKey: ["analyses", workspace.id],
    queryFn: () =>
      AnalysesService.listAnalyses({ workspaceId: workspace.id, limit: 50 }),
    refetchInterval: pollWhileUnfinished((page: AnalysesPublic) =>
      page.data.map((a) => a.status),
    ),
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
    refetchInterval: pollWhileUnfinished((analysis: AnalysisPublic) => [
      analysis.status,
    ]),
  })
}

export function useAnalysisSchedule() {
  const workspace = useCurrentWorkspace()
  return useQuery({
    queryKey: ["analysis-schedule", workspace.id],
    queryFn: () => AnalysesService.readSchedule({ workspaceId: workspace.id }),
  })
}
