import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, Link } from "@tanstack/react-router"
import { subDays, format } from "date-fns"
import {
  BarChart2,
  Eye,
  Link2,
  Loader2,
  RefreshCw,
  TrendingUp,
  Users,
} from "lucide-react"

import { IntegrationsService, MetricsService } from "@/client"
import type { IntegrationPublic } from "@/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { canManage } from "@/components/Workspaces/roles"
import { useWorkspace } from "@/contexts/WorkspaceContext"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"

export const Route = createFileRoute("/_layout/")({
  component: Dashboard,
  head: () => ({
    meta: [{ title: "Dashboard - Prism" }],
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
  const from = subDays(to, 6)
  return { dateFrom: format(from, "yyyy-MM-dd"), dateTo: format(to, "yyyy-MM-dd") }
}

function statusVariant(
  status: string,
): "default" | "secondary" | "destructive" | "outline" {
  if (status === "active") return "default"
  if (status === "error" || status === "expired") return "destructive"
  return "secondary"
}

const PLATFORM_LABELS: Record<string, string> = {
  facebook: "Facebook",
  instagram: "Instagram",
  twitter: "Twitter / X",
  linkedin: "LinkedIn",
  tiktok: "TikTok",
  google_analytics: "Google Analytics",
}

// ---- KPI card ---------------------------------------------------------------

function KpiCard({
  title,
  value,
  icon: Icon,
  loading,
}: {
  title: string
  value: string
  icon: React.ElementType
  loading?: boolean
}) {
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
          <Skeleton className="h-7 w-20" />
        ) : (
          <p className="text-2xl font-bold">{value}</p>
        )}
      </CardContent>
    </Card>
  )
}

// ---- Integration row --------------------------------------------------------

function IntegrationRow({
  integration,
  editable,
}: {
  integration: IntegrationPublic
  editable: boolean
}) {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const syncMut = useMutation({
    mutationFn: () =>
      IntegrationsService.triggerSync({ integrationId: integration.id }),
    onSuccess: () => showSuccessToast("Sync enqueued"),
    onError: handleError.bind(showErrorToast),
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: ["integrations"] }),
  })

  return (
    <div className="flex items-center justify-between py-2">
      <div className="flex items-center gap-3">
        <div className="flex size-8 items-center justify-center rounded-md border bg-muted">
          <Link2 className="size-4 text-muted-foreground" />
        </div>
        <div>
          <p className="text-sm font-medium">
            {PLATFORM_LABELS[integration.platform] ?? integration.platform}
          </p>
          <p className="text-xs text-muted-foreground">
            {integration.external_account_name}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Badge variant={statusVariant(integration.status)} className="capitalize text-xs">
          {integration.status}
        </Badge>
        {editable && integration.status !== "expired" && (
          <Button
            variant="ghost"
            size="icon"
            className="size-7"
            onClick={() => syncMut.mutate()}
            disabled={syncMut.isPending}
            title="Sync now"
            aria-label="Sync now"
          >
            {syncMut.isPending ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <RefreshCw className="size-3.5" />
            )}
          </Button>
        )}
      </div>
    </div>
  )
}

// ---- Dashboard --------------------------------------------------------------

function Dashboard() {
  const { currentWorkspace } = useWorkspace()
  const { dateFrom, dateTo } = defaultRange()

  const summaryQ = useQuery({
    queryKey: ["metrics", "summary", currentWorkspace?.id, dateFrom, dateTo],
    queryFn: () =>
      MetricsService.getSummary({
        workspaceId: currentWorkspace!.id,
        dateFrom,
        dateTo,
      }),
    enabled: !!currentWorkspace,
  })

  const integrationsQ = useQuery({
    queryKey: ["integrations", currentWorkspace?.id],
    queryFn: () =>
      IntegrationsService.listIntegrations({
        workspaceId: currentWorkspace!.id,
      }),
    enabled: !!currentWorkspace,
  })

  if (!currentWorkspace) return null

  const totals = summaryQ.data?.totals
  const integrations = integrationsQ.data?.data ?? []
  const hasError = integrations.some((i) => i.status === "error")

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold">{currentWorkspace.name}</h1>
        <p className="text-muted-foreground text-sm mt-1">Last 7 days</p>
      </div>

      {/* KPI cards */}
      <div className="grid gap-4 grid-cols-2 md:grid-cols-3 xl:grid-cols-5">
        <KpiCard
          title="Impressions"
          value={fmt(totals?.impressions)}
          icon={BarChart2}
          loading={summaryQ.isLoading}
        />
        <KpiCard
          title="Views"
          value={fmt(totals?.views)}
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
          title="Engagements"
          value={fmt(totals?.engagements)}
          icon={BarChart2}
          loading={summaryQ.isLoading}
        />
        <KpiCard
          title="Followers"
          value={fmt(totals?.followers_count)}
          icon={Users}
          loading={summaryQ.isLoading}
        />
      </div>

      {/* Integrations */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-base">Connected platforms</CardTitle>
          {hasError && (
            <Badge variant="destructive" className="text-xs">
              Sync error
            </Badge>
          )}
        </CardHeader>
        <CardContent>
          {integrationsQ.isLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : integrations.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-8 text-center text-muted-foreground">
              <Link2 className="size-8" />
              <p className="text-sm">No platforms connected yet.</p>
              <Button asChild variant="outline" size="sm">
                <Link to="/integrations">Connect a platform</Link>
              </Button>
            </div>
          ) : (
            <div className="divide-y">
              {integrations.map((i) => (
                <IntegrationRow key={i.id} integration={i} editable={canManage(currentWorkspace)} />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Quick links */}
      <div className="flex gap-3">
        <Button asChild variant="outline" size="sm">
          <Link to="/analytics">
            <BarChart2 className="mr-2 size-4" />
            Full analytics
          </Link>
        </Button>
        <Button asChild variant="outline" size="sm">
          <Link to="/integrations">
            <Link2 className="mr-2 size-4" />
            Manage integrations
          </Link>
        </Button>
      </div>
    </div>
  )
}
