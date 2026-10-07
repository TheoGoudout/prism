import { useMutation } from "@tanstack/react-query"
import { Download, Sparkles, TrendingDown, TrendingUp } from "lucide-react"

import type { Insight } from "@/client"
import { AiService } from "@/client"
import { SkeletonRows } from "@/components/Common/SkeletonRows"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { LoadingButton } from "@/components/ui/loading-button"
import { useMetricsParams } from "@/hooks/useMetrics"
import type { DateRange } from "@/lib/format"

const INSIGHT_ICONS: Record<Insight["type"], React.ReactNode> = {
  positive: <TrendingUp className="mt-0.5 size-4 shrink-0 text-green-500" />,
  negative: (
    <TrendingDown className="mt-0.5 size-4 shrink-0 text-destructive" />
  ),
  neutral: (
    <Sparkles className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
  ),
}

function downloadMarkdown(markdown: string, filename: string) {
  const url = URL.createObjectURL(
    new Blob([markdown], { type: "text/markdown" }),
  )
  const link = document.createElement("a")
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

/** AI-generated insights, plus a downloadable markdown report. */
export function InsightsPanel({ range }: { range: DateRange }) {
  const params = useMetricsParams(range)

  const insights = useMutation({
    mutationFn: () => AiService.generateInsights(params),
  })
  const report = useMutation({
    mutationFn: () => AiService.generateReport(params),
    onSuccess: (data) =>
      downloadMarkdown(
        data.report,
        `report-${range.dateFrom}-${range.dateTo}.md`,
      ),
  })
  const busy = insights.isPending || report.isPending

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2 text-base">
          <Sparkles className="size-4" />
          AI Insights
        </CardTitle>
        <div className="flex gap-2">
          <LoadingButton
            variant="outline"
            size="sm"
            icon={Sparkles}
            loading={insights.isPending}
            disabled={busy}
            onClick={() => insights.mutate()}
          >
            Generate insights
          </LoadingButton>
          <LoadingButton
            variant="outline"
            size="sm"
            icon={Download}
            loading={report.isPending}
            disabled={busy}
            onClick={() => report.mutate()}
          >
            Download report
          </LoadingButton>
        </div>
      </CardHeader>
      <CardContent>
        {insights.isIdle && (
          <p className="py-4 text-center text-sm text-muted-foreground">
            Click "Generate insights" to get AI-powered analysis of your
            metrics.
          </p>
        )}
        {insights.isPending && <SkeletonRows count={4} className="h-14" />}
        {insights.isError && (
          <p className="py-4 text-center text-sm text-destructive">
            Failed to generate insights. Please try again.
          </p>
        )}
        {insights.data && (
          <ul className="space-y-3">
            {insights.data.insights.map((insight) => (
              <li key={insight.title} className="flex gap-3 text-sm">
                {INSIGHT_ICONS[insight.type]}
                <div>
                  <p className="font-medium">{insight.title}</p>
                  <p className="text-muted-foreground">{insight.body}</p>
                </div>
              </li>
            ))}
          </ul>
        )}
        {report.isError && (
          <p className="pt-4 text-center text-sm text-destructive">
            Failed to generate the report. Please try again.
          </p>
        )}
      </CardContent>
    </Card>
  )
}
