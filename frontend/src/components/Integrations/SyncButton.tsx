import { Loader2, RefreshCw } from "lucide-react"

import type { IntegrationPublic } from "@/client"
import { Button } from "@/components/ui/button"
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
    <Button
      variant="ghost"
      size="icon"
      className={className}
      onClick={() => sync.mutate()}
      disabled={sync.isPending || needsReconnect(integration.status)}
      title="Sync now"
      aria-label={`Sync ${platformLabel(integration.platform)} now`}
    >
      {sync.isPending ? (
        <Loader2 className="size-4 animate-spin" />
      ) : (
        <RefreshCw className="size-4" />
      )}
    </Button>
  )
}
