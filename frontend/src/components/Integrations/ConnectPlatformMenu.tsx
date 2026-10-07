import { Plus } from "lucide-react"

import type { Platform } from "@/client"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { LoadingButton } from "@/components/ui/loading-button"
import { PLATFORM_LABELS } from "@/lib/platforms"
import { usePlatformConnector } from "./ApiKeyConnectDialog"
import { PlatformIcon } from "./PlatformIcon"

/**
 * "Connect platform" dropdown, listing the platforms set up on the server;
 * already-connected platforms are labelled.
 */
export function ConnectPlatformMenu({
  available,
  connected,
}: {
  available: Platform[]
  connected: Set<Platform>
}) {
  const { connect, pending, dialog } = usePlatformConnector()
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <LoadingButton icon={Plus} loading={pending !== null}>
            Connect platform
          </LoadingButton>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          {available.length === 0 && (
            <DropdownMenuItem disabled>
              No platforms are set up yet
            </DropdownMenuItem>
          )}
          {available.map((platform) => (
            <DropdownMenuItem key={platform} onClick={() => connect(platform)}>
              <PlatformIcon
                platform={platform}
                className="size-5 text-[10px]"
              />
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
      {dialog}
    </>
  )
}
