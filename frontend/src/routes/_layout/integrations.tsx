import { useQueryClient } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { Link2 } from "lucide-react"
import { useEffect, useRef } from "react"

import { SkeletonRows } from "@/components/Common/SkeletonRows"
import { ConnectionGuides } from "@/components/Integrations/ConnectionGuides"
import { ConnectPlatformMenu } from "@/components/Integrations/ConnectPlatformMenu"
import { IntegrationRow } from "@/components/Integrations/IntegrationRow"
import { useMigrateDialogs } from "@/components/Migration/MigrateDialogs"
import { MigrateMenu } from "@/components/Migration/MigrateMenu"
import { MigrationGuides } from "@/components/Migration/MigrationGuides"
import { MigrationRuns } from "@/components/Migration/MigrationRuns"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { canManage } from "@/components/Workspaces/roles"
import { useCurrentWorkspace } from "@/contexts/WorkspaceContext"
import useCustomToast from "@/hooks/useCustomToast"
import { useAvailablePlatforms, useIntegrations } from "@/hooks/useIntegrations"

// Set by the backend's OAuth callback when it redirects back here
interface OAuthResult {
  connected?: "1"
  error?: string
}

export const Route = createFileRoute("/_layout/integrations")({
  component: IntegrationsPage,
  validateSearch: (search: Record<string, unknown>): OAuthResult => ({
    // The router JSON-parses search values, so "?connected=1" arrives as 1
    connected: String(search.connected) === "1" ? "1" : undefined,
    error: typeof search.error === "string" ? search.error : undefined,
  }),
  head: () => ({
    meta: [{ title: "Integrations - Prism" }],
  }),
})

// Error codes set by the OAuth callback. Unknown codes (e.g. a provider's own
// error value) are shown as-is.
const OAUTH_ERRORS: Record<string, string> = {
  access_denied: "Connection cancelled: access was not granted.",
  invalid_state:
    "The connection link expired or is invalid. Please try connecting again.",
  missing_code: "The platform didn't complete the authorization. Please retry.",
  forbidden: "Only workspace owners and admins can connect platforms.",
  platform_unavailable: "This platform is no longer set up on this server.",
  connection_failed:
    "We couldn't connect to the platform. Please try again in a moment.",
}

/**
 * Show the result of an OAuth round-trip once, then drop it from the URL so
 * a page refresh doesn't repeat the toast.
 */
function useOAuthResultToast() {
  const { connected, error } = Route.useSearch()
  const navigate = Route.useNavigate()
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const handled = useRef(false)

  useEffect(() => {
    if ((!connected && !error) || handled.current) return
    handled.current = true
    if (connected) {
      showSuccessToast("Platform connected. The first sync has started.")
      queryClient.invalidateQueries({ queryKey: ["integrations"] })
    }
    if (error) {
      showErrorToast(OAUTH_ERRORS[error] ?? `Connection failed: ${error}`)
    }
    navigate({ search: {}, replace: true })
  }, [
    connected,
    error,
    navigate,
    queryClient,
    showErrorToast,
    showSuccessToast,
  ])
}

function IntegrationsPage() {
  useOAuthResultToast()
  const workspace = useCurrentWorkspace()
  const { data, isLoading } = useIntegrations()
  const integrations = data ?? []
  const { data: available } = useAvailablePlatforms()
  const editable = canManage(workspace)
  const migrate = useMigrateDialogs()

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Integrations</h1>
          <p className="mt-1 text-sm text-muted-foreground">{workspace.name}</p>
        </div>
        {editable && (
          <div className="flex flex-wrap justify-end gap-2">
            {integrations.length > 0 && (
              <MigrateMenu
                openSource={migrate.openSource}
                openUpload={migrate.openUpload}
              />
            )}
            {available && (
              <ConnectPlatformMenu
                available={available}
                connected={new Set(integrations.map((i) => i.platform))}
              />
            )}
          </div>
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Connected accounts</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          {isLoading ? (
            <SkeletonRows />
          ) : integrations.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 py-12 text-muted-foreground">
              <Link2 className="size-8" />
              <p className="text-sm">No integrations yet.</p>
              <p className="text-xs">
                {editable
                  ? 'Click "Connect platform" to add your first social media account.'
                  : "Ask a workspace owner or admin to connect a platform."}
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Platform</TableHead>
                  <TableHead>Account</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Last synced</TableHead>
                  <TableHead>Error</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {integrations.map((integration) => (
                  <IntegrationRow
                    key={integration.id}
                    integration={integration}
                    editable={editable}
                  />
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <MigrationRuns />

      {available && (
        <ConnectionGuides available={available} editable={editable} />
      )}

      {integrations.length > 0 && (
        <MigrationGuides
          editable={editable}
          openSource={migrate.openSource}
          openUpload={migrate.openUpload}
        />
      )}
      {migrate.dialogs}
    </div>
  )
}
