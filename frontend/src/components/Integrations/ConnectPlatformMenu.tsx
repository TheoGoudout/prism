import { Loader2, Plus } from "lucide-react"

import type { Platform } from "@/client"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useConnectPlatform } from "@/hooks/useIntegrations"
import { PLATFORM_LABELS, PLATFORMS } from "@/lib/platforms"

/** "Connect platform" dropdown; already-connected platforms are labelled. */
export function ConnectPlatformMenu({
  connected,
}: {
  connected: Set<Platform>
}) {
  const { connect, pending } = useConnectPlatform()
  return (
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
        {PLATFORMS.map((platform) => (
          <DropdownMenuItem key={platform} onClick={() => connect(platform)}>
            {PLATFORM_LABELS[platform]}
            {connected.has(platform) && (
              <span className="ml-auto text-xs text-muted-foreground">
                Connected
              </span>
            )}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
