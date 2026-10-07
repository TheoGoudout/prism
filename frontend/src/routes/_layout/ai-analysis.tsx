import { useMutation, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import {
  CalendarClock,
  CalendarRange,
  Loader2,
  Mail,
  Sparkles,
  Trash2,
  TriangleAlert,
} from "lucide-react"
import { useState } from "react"

import type { AnalysisPublic, AnalysisSummaryPublic } from "@/client"
import { AnalysesService } from "@/client"
import { AnalysisReport } from "@/components/AiAnalysis/AnalysisReport"
import { describeSchedule } from "@/components/AiAnalysis/labels"
import { RunAnalysisDialog } from "@/components/AiAnalysis/RunAnalysisDialog"
import { ScheduleDialog } from "@/components/AiAnalysis/ScheduleDialog"
import ConfirmDialog from "@/components/Common/ConfirmDialog"
import { PageHeader } from "@/components/Common/PageHeader"
import { SkeletonRows } from "@/components/Common/SkeletonRows"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { LoadingButton } from "@/components/ui/loading-button"
import { canManage } from "@/components/Workspaces/roles"
import { useCurrentWorkspace } from "@/contexts/WorkspaceContext"
import {
  useAnalyses,
  useAnalysis,
  useAnalysisSchedule,
} from "@/hooks/useAnalyses"
import useCustomToast from "@/hooks/useCustomToast"
import { formatRelative, plural } from "@/lib/format"
import { isUnfinished } from "@/lib/jobs"
import { pageHead } from "@/lib/routing"
import { cn } from "@/lib/utils"

export const Route = createFileRoute("/_layout/ai-analysis")({
  component: AiAnalysisPage,
  validateSearch: (search: Record<string, unknown>): { analysis?: string } => ({
    analysis: typeof search.analysis === "string" ? search.analysis : undefined,
  }),
  head: pageHead("AI Analysis"),
})

const formatDay = (day: string, withYear = false) =>
  new Date(`${day}T00:00:00`).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: withYear ? "numeric" : undefined,
  })

const spansYears = (a: AnalysisSummaryPublic) =>
  a.date_from.slice(0, 4) !== a.date_to.slice(0, 4)

/** "Sep 26 – Oct 2", or with years when the period spans two of them. */
const formatPeriod = (a: AnalysisSummaryPublic) =>
  `${formatDay(a.date_from, spansYears(a))} – ${formatDay(a.date_to, spansYears(a))}`

function StatusBadge({ analysis }: { analysis: AnalysisSummaryPublic }) {
  if (isUnfinished(analysis.status)) {
    return (
      <Badge variant="secondary">
        <Loader2 className="animate-spin" />
        Running
      </Badge>
    )
  }
  if (analysis.status === "failed") {
    return <Badge variant="destructive">Failed</Badge>
  }
  return null
}

function YearlyBadge() {
  return (
    <Badge variant="outline">
      <CalendarRange />
      Year in review
    </Badge>
  )
}

function History({
  analyses,
  selectedId,
  onSelect,
}: {
  analyses: AnalysisSummaryPublic[]
  selectedId: string | undefined
  onSelect: (id: string) => void
}) {
  return (
    <Card className="h-fit">
      <CardHeader>
        <CardTitle className="text-base">History</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1 px-2">
        {analyses.map((analysis) => (
          <button
            key={analysis.id}
            type="button"
            onClick={() => onSelect(analysis.id)}
            className={cn(
              "flex w-full flex-col gap-1 rounded-md px-3 py-2 text-left text-sm transition-colors hover:bg-accent",
              analysis.id === selectedId && "bg-accent",
            )}
          >
            <span className="flex flex-wrap items-center gap-2 font-medium">
              {formatPeriod(analysis)}
              {analysis.kind === "yearly" && <YearlyBadge />}
              <StatusBadge analysis={analysis} />
            </span>
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              {analysis.trigger === "scheduled" && (
                <CalendarClock className="size-3" />
              )}
              {formatRelative(analysis.created_at)}
              {analysis.status === "completed" &&
                ` · ${analysis.post_count} posts`}
            </span>
          </button>
        ))}
      </CardContent>
    </Card>
  )
}

function AnalysisView({
  analysis,
  onDeleted,
}: {
  analysis: AnalysisPublic
  onDeleted: () => void
}) {
  const workspace = useCurrentWorkspace()
  const queryClient = useQueryClient()
  const { showSuccessToast, showApiError } = useCustomToast()
  const [confirmDelete, setConfirmDelete] = useState(false)
  const ids = { workspaceId: workspace.id, analysisId: analysis.id }

  const emailMut = useMutation({
    mutationFn: () => AnalysesService.emailAnalysis(ids),
    onSuccess: () => showSuccessToast("The report was sent to your inbox"),
    onError: showApiError,
  })
  const deleteMut = useMutation({
    mutationFn: () => AnalysesService.deleteAnalysis(ids),
    onSuccess: () => {
      showSuccessToast("Analysis deleted")
      setConfirmDelete(false)
      queryClient.invalidateQueries({ queryKey: ["analyses", workspace.id] })
      onDeleted()
    },
    onError: showApiError,
  })

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            {formatPeriod(analysis)}
            {!spansYears(analysis) && `, ${analysis.date_to.slice(0, 4)}`}
            {analysis.kind === "yearly" && <YearlyBadge />}
          </h2>
          <p className="text-sm text-muted-foreground">
            {analysis.trigger === "scheduled" ? "Scheduled" : "Manual"} analysis
            · {formatRelative(analysis.created_at)}
            {analysis.status === "completed" &&
              ` · ${analysis.post_count} posts analyzed`}
            {analysis.emailed_at
              ? " · emailed"
              : analysis.email_recipients?.length &&
                  isUnfinished(analysis.status)
                ? ` · will be emailed to ${plural(analysis.email_recipients.length, "recipient")}`
                : ""}
          </p>
        </div>
        <div className="flex gap-2">
          {analysis.status === "completed" && (
            <LoadingButton
              variant="outline"
              size="sm"
              icon={Mail}
              loading={emailMut.isPending}
              onClick={() => emailMut.mutate()}
            >
              Email me
            </LoadingButton>
          )}
          {canManage(workspace) && !isUnfinished(analysis.status) && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setConfirmDelete(true)}
            >
              <Trash2 />
              Delete
            </Button>
          )}
        </div>
      </div>

      {isUnfinished(analysis.status) && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
            <Loader2 className="size-8 animate-spin text-muted-foreground" />
            <p className="font-medium">Analyzing your posts…</p>
            <p className="max-w-md text-sm text-muted-foreground">
              The AI is reviewing every post and platform of the period. This
              usually takes{" "}
              {analysis.kind === "yearly"
                ? "a few minutes for a whole year"
                : "under a minute"}
              ; the report appears here when it's ready.
            </p>
          </CardContent>
        </Card>
      )}
      {analysis.status === "failed" && (
        <Card className="border-destructive/50">
          <CardContent className="flex gap-3 py-6 text-sm">
            <TriangleAlert className="size-5 shrink-0 text-destructive" />
            <div>
              <p className="font-medium">The analysis failed</p>
              <p className="text-muted-foreground">
                {analysis.error ?? "Unknown error."} Please try again.
              </p>
            </div>
          </CardContent>
        </Card>
      )}
      {analysis.result && (
        <AnalysisReport
          result={analysis.result}
          posts={analysis.posts ?? []}
          yearly={analysis.kind === "yearly"}
        />
      )}

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete analysis"
        description="This analysis will be permanently deleted."
        confirmLabel="Delete"
        loading={deleteMut.isPending}
        onConfirm={() => deleteMut.mutate()}
      />
    </div>
  )
}

function AiAnalysisPage() {
  const workspace = useCurrentWorkspace()
  const navigate = useNavigate({ from: Route.fullPath })
  const { analysis: analysisParam } = Route.useSearch()
  const [runOpen, setRunOpen] = useState(false)
  const [scheduleOpen, setScheduleOpen] = useState(false)

  const analyses = useAnalyses()
  const schedule = useAnalysisSchedule()
  const list = analyses.data?.data ?? []
  const selectedId = analysisParam ?? list[0]?.id
  const selected = useAnalysis(selectedId)
  const running = list.some((a) => isUnfinished(a.status))

  const select = (id: string | undefined) =>
    navigate({ search: { analysis: id }, replace: true })

  return (
    <div className="space-y-6">
      <PageHeader
        title={
          <>
            <Sparkles className="size-6" />
            AI Analysis
          </>
        }
        description={`A full performance review of ${workspace.name} across every connected platform: each post, each topic, and what to do next.`}
        actions={
          <>
            <Button variant="outline" onClick={() => setScheduleOpen(true)}>
              <CalendarClock />
              {schedule.data?.enabled ? "Scheduled" : "Schedule"}
            </Button>
            <LoadingButton
              icon={Sparkles}
              loading={running}
              onClick={() => setRunOpen(true)}
            >
              Run analysis
            </LoadingButton>
          </>
        }
      />

      {schedule.data?.enabled && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <CalendarClock className="size-4" />
          {describeSchedule(schedule.data)}
          {schedule.data.email_enabled &&
            ` · emailed to ${plural(schedule.data.email_recipients?.length ?? 0, "recipient")}`}
          {schedule.data.next_run_at &&
            ` · next run ${new Date(schedule.data.next_run_at).toLocaleString()}`}
        </p>
      )}

      {analyses.isLoading ? (
        <SkeletonRows count={4} className="h-24" />
      ) : list.length === 0 ? (
        <Card>
          <CardHeader className="items-center text-center">
            <Sparkles className="size-8 text-muted-foreground" />
            <CardTitle>No analysis yet</CardTitle>
            <CardDescription className="max-w-md">
              Run your first analysis to get a per-post and per-topic review of
              your content, what worked, what didn't and how to improve. You can
              also schedule it to run every week, two weeks or month and receive
              the report by email.
            </CardDescription>
          </CardHeader>
        </Card>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[16rem_1fr]">
          <History analyses={list} selectedId={selectedId} onSelect={select} />
          <div className="min-w-0">
            {selected.data ? (
              <AnalysisView
                analysis={selected.data}
                onDeleted={() => select(undefined)}
              />
            ) : selected.isError ? (
              <p className="py-8 text-center text-sm text-muted-foreground">
                This analysis could not be found.
              </p>
            ) : (
              <SkeletonRows count={4} className="h-24" />
            )}
          </div>
        </div>
      )}

      {runOpen && (
        <RunAnalysisDialog
          open={runOpen}
          onOpenChange={setRunOpen}
          onStarted={(analysis) => select(analysis.id)}
        />
      )}
      <ScheduleDialog
        open={scheduleOpen}
        onOpenChange={setScheduleOpen}
        schedule={schedule.data}
      />
    </div>
  )
}
