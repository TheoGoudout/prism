import { Loader2, Plus } from "lucide-react"

import type { Platform } from "@/client"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
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
