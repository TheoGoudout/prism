import { Plug, Trash2 } from "lucide-react"
import { useState } from "react"

import type { IntegrationPublic } from "@/client"
import ConfirmDialog from "@/components/Common/ConfirmDialog"
import { Button } from "@/components/ui/button"
import { LoadingButton } from "@/components/ui/loading-button"
import { TableCell, TableRow } from "@/components/ui/table"
import { useDeleteIntegration } from "@/hooks/useIntegrations"
import { formatRelative } from "@/lib/format"
import { needsReconnect, platformLabel } from "@/lib/platforms"
import { AccountSelector } from "./AccountSelector"
import { usePlatformConnector } from "./ApiKeyConnectDialog"
import { IntegrationStatusBadge } from "./IntegrationStatusBadge"
import { PlatformIcon } from "./PlatformIcon"
import { SyncButton } from "./SyncButton"

interface IntegrationRowProps {
  integration: IntegrationPublic
  /** Whether the user may sync, reconnect and disconnect (owner / admin). */
  editable: boolean
}

export function IntegrationRow({ integration, editable }: IntegrationRowProps) {
  const label = platformLabel(integration.platform)
  const {
    connect,
    pending: reconnecting,
    dialog: apiKeyDialog,
  } = usePlatformConnector()
  const remove = useDeleteIntegration(integration)
  const [confirmDelete, setConfirmDelete] = useState(false)

  return (
    <TableRow>
      <TableCell className="font-medium">
        <span className="flex items-center gap-2">
          <PlatformIcon platform={integration.platform} className="size-6" />
          {label}
        </span>
      </TableCell>
      <TableCell className="text-sm text-muted-foreground">
        <div className="flex flex-col items-start gap-0.5">
          {integration.external_account_name}
          <AccountSelector integration={integration} editable={editable} />
        </div>
      </TableCell>
      <TableCell>
        <IntegrationStatusBadge status={integration.status} />
      </TableCell>
      <TableCell className="text-sm text-muted-foreground">
        {formatRelative(integration.last_synced_at)}
      </TableCell>
      <TableCell>
        {integration.sync_error && (
          <span className="line-clamp-1 max-w-xs text-xs text-destructive">
            {integration.sync_error}
          </span>
        )}
      </TableCell>
      <TableCell className="text-right">
        {editable && (
          <div className="flex items-center justify-end gap-2">
            {needsReconnect(integration.status) && (
              <LoadingButton
                variant="outline"
                size="sm"
                icon={Plug}
                loading={reconnecting !== null}
                onClick={() => connect(integration.platform)}
              >
                Reconnect
              </LoadingButton>
            )}
            <SyncButton integration={integration} />
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
          loading={remove.isPending}
          onConfirm={() =>
            remove.mutate(undefined, {
              onSuccess: () => setConfirmDelete(false),
            })
          }
        />
        {apiKeyDialog}
      </TableCell>
    </TableRow>
  )
}
