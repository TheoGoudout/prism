import { ExternalLink, Plug } from "lucide-react"
import { type ReactNode, useState } from "react"

import type { Platform } from "@/client"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { LoadingButton } from "@/components/ui/loading-button"
import { PasswordInput } from "@/components/ui/password-input"
import {
  useConnectPlatform,
  useConnectWithApiKey,
} from "@/hooks/useIntegrations"
import { API_KEY_PLATFORMS, platformLabel, usesApiKey } from "@/lib/platforms"

/** Connect a platform that has no OAuth by pasting one of its API keys. */
export function ApiKeyConnectDialog({
  platform,
  onClose,
}: {
  platform: Platform
  onClose: () => void
}) {
  const label = platformLabel(platform)
  const help = API_KEY_PLATFORMS[platform]
  const [apiKey, setApiKey] = useState("")
  const mutation = useConnectWithApiKey(platform)

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Connect {label}</DialogTitle>
          <DialogDescription>
            {label} is connected with an API key: create one in your {label}{" "}
            account and paste it below.
          </DialogDescription>
        </DialogHeader>
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault()
            if (apiKey.trim())
              mutation.mutate(apiKey.trim(), { onSuccess: onClose })
          }}
        >
          {help && (
            <>
              <ol className="flex list-decimal flex-col gap-1 pl-5 text-sm text-muted-foreground">
                {help.steps.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ol>
              <ExternalAnchor href={help.keysUrl}>
                Open the {label} API keys
              </ExternalAnchor>
            </>
          )}
          <div className="flex flex-col gap-2">
            <Label htmlFor="platform-api-key">API key</Label>
            <PasswordInput
              id="platform-api-key"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              autoComplete="off"
            />
          </div>
          <p className="text-xs text-muted-foreground">
            The key is stored encrypted and only used to read your statistics.
            To cut Prism off later, delete the key in {label}.
          </p>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="outline" type="button">
                Cancel
              </Button>
            </DialogClose>
            <LoadingButton
              type="submit"
              loading={mutation.isPending}
              disabled={!apiKey.trim()}
            >
              <Plug />
              Connect
            </LoadingButton>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/**
 * Connect any platform: send the browser to the OAuth consent screen, or
 * open the API key dialog (render `dialog`) for the platforms without OAuth.
 */
export function usePlatformConnector() {
  const oauth = useConnectPlatform()
  const [apiKeyPlatform, setApiKeyPlatform] = useState<Platform | null>(null)

  const connect = (platform: Platform) =>
    usesApiKey(platform) ? setApiKeyPlatform(platform) : oauth.connect(platform)

  const dialog = apiKeyPlatform && (
    <ApiKeyConnectDialog
      platform={apiKeyPlatform}
      onClose={() => setApiKeyPlatform(null)}
    />
  )
  return { connect, pending: oauth.pending, dialog }
}

function ExternalAnchor({
  href,
  children,
}: {
  href: string
  children: ReactNode
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 self-start text-sm text-primary underline-offset-4 hover:underline"
    >
      {children}
      <ExternalLink className="size-3.5" />
    </a>
  )
}
