import { RefreshCw } from "lucide-react"

import type { IntegrationPublic } from "@/client"
import { LoadingButton } from "@/components/ui/loading-button"
import { useSyncIntegration } from "@/hooks/useIntegrations"
import { needsReconnect, platformLabel } from "@/lib/platforms"

export function SyncButton({
  integration,
  className,
}: {
  integration: IntegrationPublic
  className?: string
}) {
  const sync = useSyncIntegration(integration)
  return (
    <LoadingButton
      variant="ghost"
      size="icon"
      className={className}
      icon={RefreshCw}
      loading={sync.isPending}
      onClick={() => sync.mutate()}
      disabled={needsReconnect(integration.status)}
      title="Sync now"
      aria-label={`Sync ${platformLabel(integration.platform)} now`}
    />
  )
}
