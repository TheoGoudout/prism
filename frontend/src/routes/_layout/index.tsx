import { createFileRoute, Link } from "@tanstack/react-router"
import { BarChart2, Link2 } from "lucide-react"

import { KpiCards } from "@/components/Common/KpiCards"
import { SkeletonRows } from "@/components/Common/SkeletonRows"
import { IntegrationStatusBadge } from "@/components/Integrations/IntegrationStatusBadge"
import { PlatformIcon } from "@/components/Integrations/PlatformIcon"
import { SyncButton } from "@/components/Integrations/SyncButton"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { canManage } from "@/components/Workspaces/roles"
import { useCurrentWorkspace } from "@/contexts/WorkspaceContext"
import { useIntegrations } from "@/hooks/useIntegrations"
import { useMetricsSummary } from "@/hooks/useMetrics"
import { lastDays } from "@/lib/format"
import { platformLabel } from "@/lib/platforms"

export const Route = createFileRoute("/_layout/")({
  component: Dashboard,
  head: () => ({
    meta: [{ title: "Dashboard - Prism" }],
  }),
})

function Dashboard() {
  const workspace = useCurrentWorkspace()
  const summary = useMetricsSummary(lastDays(7))
  const integrationsQuery = useIntegrations()
  const integrations = integrationsQuery.data ?? []
  const editable = canManage(workspace)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">{workspace.name}</h1>
        <p className="mt-1 text-sm text-muted-foreground">Last 7 days</p>
      </div>

      <KpiCards
        className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6"
        metrics={[
          "exposures",
          "reach",
          "engagements",
          "engagement_rate",
          "followers_count",
          "followers_growth",
        ]}
        totals={summary.data?.totals}
        loading={summary.isLoading}
      />

      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-base">Connected platforms</CardTitle>
          {integrations.some((i) => i.status === "error") && (
            <Badge variant="destructive" className="text-xs">
              Sync error
            </Badge>
          )}
        </CardHeader>
        <CardContent>
          {integrationsQuery.isLoading ? (
            <SkeletonRows />
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
              {integrations.map((integration) => (
                <div
                  key={integration.id}
                  className="flex items-center justify-between py-2"
                >
                  <div className="flex items-center gap-3">
                    <PlatformIcon platform={integration.platform} />
                    <div>
                      <p className="text-sm font-medium">
                        {platformLabel(integration.platform)}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {integration.external_account_name}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <IntegrationStatusBadge
                      status={integration.status}
                      className="text-xs"
                    />
                    {editable && (
                      <SyncButton
                        integration={integration}
                        className="size-7"
                      />
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

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
