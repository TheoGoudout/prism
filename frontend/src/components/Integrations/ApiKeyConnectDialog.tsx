import { Plug } from "lucide-react"
import { useState } from "react"
import type { Platform } from "@/client"
import { CancelButton } from "@/components/Common/CancelButton"
import { ExternalLink } from "@/components/Common/ExternalLink"
import {
  Dialog,
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
              <ExternalLink href={help.keysUrl} className="self-start text-sm">
                Open the {label} API keys
              </ExternalLink>
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
            <CancelButton />
            <LoadingButton
              type="submit"
              icon={Plug}
              loading={mutation.isPending}
              disabled={!apiKey.trim()}
            >
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
