import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { formatDistanceToNow } from "date-fns"
import { Link2, Loader2, Plug, Plus, RefreshCw, Trash2 } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import type { ApiError, IntegrationPublic, Platform } from "@/client"
import { IntegrationsService, OauthService } from "@/client"
import ConfirmDialog from "@/components/Common/ConfirmDialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { canManage } from "@/components/Workspaces/roles"
import { useWorkspace } from "@/contexts/WorkspaceContext"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"

export const Route = createFileRoute("/_layout/integrations")({
  component: IntegrationsPage,
  validateSearch: (
    search: Record<string, unknown>,
  ): { connected?: "1"; error?: string } => ({
    connected: search.connected === "1" ? ("1" as const) : undefined,
    error: typeof search.error === "string" ? search.error : undefined,
  }),
  head: () => ({
    meta: [{ title: "Integrations - Prism" }],
  }),
})

// ---- helpers ----------------------------------------------------------------

const PLATFORM_LABELS: Record<Platform, string> = {
  facebook: "Facebook",
  instagram: "Instagram",
  twitter: "Twitter / X",
  linkedin: "LinkedIn",
  tiktok: "TikTok",
  google_analytics: "Google Analytics",
}

const PLATFORMS: Platform[] = [
  "facebook",
  "instagram",
  "twitter",
  "linkedin",
  "tiktok",
  "google_analytics",
]

// Error codes set by the backend's OAuth callback (plus the provider's own
// `error` value, e.g. access_denied, which is shown as-is if unknown).
const OAUTH_ERRORS: Record<string, string> = {
  access_denied: "Connection cancelled: access was not granted.",
  invalid_state:
    "The connection link expired or is invalid. Please try connecting again.",
  missing_code: "The platform didn't complete the authorization. Please retry.",
  forbidden: "Only workspace owners and admins can connect platforms.",
  connection_failed:
    "We couldn't connect to the platform. Please try again in a moment.",
}

function oauthErrorMessage(code: string): string {
  return OAUTH_ERRORS[code] ?? `Connection failed: ${code}`
}

function statusVariant(
  status: string,
): "default" | "secondary" | "destructive" | "outline" {
  if (status === "active") return "default"
  if (status === "error" || status === "expired") return "destructive"
  return "secondary"
}

function useConnectPlatform() {
  const { currentWorkspace } = useWorkspace()
  const { showErrorToast } = useCustomToast()
  const [pending, setPending] = useState<Platform | null>(null)

  async function connect(platform: Platform) {
    if (!currentWorkspace) return
    setPending(platform)
    try {
      const resp = await OauthService.connect({
        platform,
        workspaceId: currentWorkspace.id,
      })
      const { authorization_url } = resp as { authorization_url: string }
      window.location.href = authorization_url
    } catch (err) {
      setPending(null)
      handleError.call(showErrorToast, err as ApiError)
    }
  }

  return { connect, pending }
}

function fmtSynced(ts: string | null | undefined): string {
  if (!ts) return "Never"
  return formatDistanceToNow(new Date(ts), { addSuffix: true })
}

// ---- Row actions ------------------------------------------------------------

function IntegrationRow({
  integration,
  editable,
}: {
  integration: IntegrationPublic
  editable: boolean
}) {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const { connect, pending: reconnecting } = useConnectPlatform()
  const [confirmDelete, setConfirmDelete] = useState(false)
  const label = PLATFORM_LABELS[integration.platform] ?? integration.platform
  const needsReconnect = integration.status === "expired"

  const syncMut = useMutation({
    mutationFn: () =>
      IntegrationsService.triggerSync({ integrationId: integration.id }),
    onSuccess: () => showSuccessToast("Sync enqueued"),
    onError: handleError.bind(showErrorToast),
  })

  const deleteMut = useMutation({
    mutationFn: () =>
      IntegrationsService.deleteIntegration({ integrationId: integration.id }),
    onSuccess: () => {
      showSuccessToast("Integration removed")
      setConfirmDelete(false)
      queryClient.invalidateQueries({ queryKey: ["integrations"] })
    },
    onError: handleError.bind(showErrorToast),
  })

  return (
    <TableRow>
      <TableCell>
        <div className="font-medium">{label}</div>
      </TableCell>
      <TableCell className="text-muted-foreground text-sm">
        {integration.external_account_name}
      </TableCell>
      <TableCell>
        <Badge
          variant={statusVariant(integration.status)}
          className="capitalize"
        >
          {integration.status}
        </Badge>
      </TableCell>
      <TableCell className="text-sm text-muted-foreground">
        {fmtSynced(integration.last_synced_at)}
      </TableCell>
      <TableCell>
        {integration.sync_error && (
          <span className="text-xs text-destructive line-clamp-1 max-w-xs">
            {integration.sync_error}
          </span>
        )}
      </TableCell>
      <TableCell className="text-right">
        {editable && (
          <div className="flex items-center justify-end gap-2">
            {needsReconnect && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => connect(integration.platform)}
                disabled={reconnecting !== null}
              >
                {reconnecting ? (
                  <Loader2 className="mr-1 size-4 animate-spin" />
                ) : (
                  <Plug className="mr-1 size-4" />
                )}
                Reconnect
              </Button>
            )}
            <Button
              variant="ghost"
              size="icon"
              onClick={() => syncMut.mutate()}
              disabled={syncMut.isPending || needsReconnect}
              title="Sync now"
              aria-label={`Sync ${label} now`}
            >
              {syncMut.isPending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <RefreshCw className="size-4" />
              )}
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setConfirmDelete(true)}
              title="Disconnect"
              aria-label={`Disconnect ${label}`}
              className="text-destructive hover:text-destructive"
            >
              <Trash2 className="size-4" />
            </Button>
          </div>
        )}
        <ConfirmDialog
          open={confirmDelete}
          onOpenChange={setConfirmDelete}
          title={`Disconnect ${label}`}
          description={
            <>
              <strong>{integration.external_account_name}</strong> will be
              disconnected and all of its synced metrics deleted.
            </>
          }
          confirmLabel="Disconnect"
          loading={deleteMut.isPending}
          onConfirm={() => deleteMut.mutate()}
        />
      </TableCell>
    </TableRow>
  )
}

// ---- Main page --------------------------------------------------------------

function IntegrationsPage() {
  const { currentWorkspace } = useWorkspace()
  const { connected, error: oauthError } = Route.useSearch()
  const navigate = Route.useNavigate()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const queryClient = useQueryClient()
  const { connect, pending } = useConnectPlatform()

  // Show the OAuth result once, then drop it from the URL so a refresh
  // doesn't repeat the toast.
  const oauthResultHandled = useRef(false)
  useEffect(() => {
    if ((!connected && !oauthError) || oauthResultHandled.current) return
    oauthResultHandled.current = true
    if (connected) {
      showSuccessToast("Platform connected. The first sync has started.")
      queryClient.invalidateQueries({ queryKey: ["integrations"] })
    }
    if (oauthError) {
      showErrorToast(oauthErrorMessage(oauthError))
    }
    navigate({ search: {}, replace: true })
  }, [
    connected,
    oauthError,
    navigate,
    queryClient,
    showErrorToast,
    showSuccessToast,
  ])

  const integrationsQ = useQuery({
    queryKey: ["integrations", currentWorkspace?.id],
    queryFn: () =>
      IntegrationsService.listIntegrations({
        workspaceId: currentWorkspace!.id,
      }),
    enabled: !!currentWorkspace,
  })

  if (!currentWorkspace) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-3 text-muted-foreground">
        <Link2 className="size-10" />
        <p>Select a workspace to manage integrations.</p>
      </div>
    )
  }

  const integrations = integrationsQ.data?.data ?? []
  const connectedPlatforms = new Set(integrations.map((i) => i.platform))
  const editable = canManage(currentWorkspace)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Integrations</h1>
          <p className="text-muted-foreground text-sm mt-1">
            {currentWorkspace.name}
          </p>
        </div>
        {editable && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button disabled={pending !== null}>
                {pending ? (
                  <Loader2 className="mr-2 size-4 animate-spin" />
                ) : (
                  <Plus className="mr-2 size-4" />
                )}
                Connect platform
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {PLATFORMS.map((p) => (
                <DropdownMenuItem key={p} onClick={() => connect(p)}>
                  {PLATFORM_LABELS[p]}
                  {connectedPlatforms.has(p) && (
                    <span className="ml-auto text-xs text-muted-foreground">
                      Connected
                    </span>
                  )}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Connected accounts</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          {integrationsQ.isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : integrations.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 gap-3 text-muted-foreground">
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
    </div>
  )
}
