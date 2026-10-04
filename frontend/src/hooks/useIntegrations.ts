import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"

import type { IntegrationPublic, Platform } from "@/client"
import { IntegrationsService } from "@/client"
import { useCurrentWorkspace } from "@/contexts/WorkspaceContext"
import useCustomToast from "@/hooks/useCustomToast"

/** The current workspace's integrations. */
export function useIntegrations() {
  const workspace = useCurrentWorkspace()
  return useQuery({
    queryKey: ["integrations", workspace.id],
    queryFn: () =>
      IntegrationsService.listIntegrations({ workspaceId: workspace.id }),
  })
}

/**
 * The platforms that can be connected: those whose app is set up on the
 * server. The others are hidden.
 */
export function useAvailablePlatforms() {
  const workspace = useCurrentWorkspace()
  return useQuery({
    queryKey: ["available-platforms", workspace.id],
    queryFn: () =>
      IntegrationsService.listAvailablePlatforms({ workspaceId: workspace.id }),
    // Server configuration: it only changes on a redeploy
    staleTime: Number.POSITIVE_INFINITY,
  })
}

export function useSyncIntegration(integration: IntegrationPublic) {
  const queryClient = useQueryClient()
  const { showSuccessToast, showApiError } = useCustomToast()
  return useMutation({
    mutationFn: () =>
      IntegrationsService.triggerSync({
        workspaceId: integration.workspace_id,
        integrationId: integration.id,
      }),
    onSuccess: () => showSuccessToast("Sync enqueued"),
    onError: showApiError,
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: ["integrations"] }),
  })
}

export function useDeleteIntegration(integration: IntegrationPublic) {
  const queryClient = useQueryClient()
  const { showSuccessToast, showApiError } = useCustomToast()
  return useMutation({
    mutationFn: () =>
      IntegrationsService.deleteIntegration({
        workspaceId: integration.workspace_id,
        integrationId: integration.id,
      }),
    onSuccess: () => showSuccessToast("Integration removed"),
    onError: showApiError,
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: ["integrations"] }),
  })
}

/**
 * Start the OAuth flow: fetch the provider's authorization URL and send the
 * browser there. `pending` is the platform being connected, if any.
 */
export function useConnectPlatform() {
  const workspace = useCurrentWorkspace()
  const { showApiError } = useCustomToast()
  const [pending, setPending] = useState<Platform | null>(null)

  async function connect(platform: Platform) {
    setPending(platform)
    try {
      const { authorization_url } = await IntegrationsService.connect({
        platform,
        workspaceId: workspace.id,
      })
      window.location.href = authorization_url
    } catch (err) {
      setPending(null)
      showApiError(err)
    }
  }

  return { connect, pending }
}
