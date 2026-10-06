import { useState } from "react"

import type { IntegrationPublic, Platform } from "@/client"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { useSetAccountShown } from "@/hooks/useIntegrations"
import { platformLabel } from "@/lib/platforms"

// What a platform's accounts are called, singular and plural
const ACCOUNT_NOUNS: Partial<Record<Platform, [string, string]>> = {
  facebook: ["Page", "Pages"],
  linkedin: ["Page", "Pages"],
  google_analytics: ["property", "properties"],
}

function accountNoun(platform: Platform, count: number) {
  const [one, many] = ACCOUNT_NOUNS[platform] ?? ["account", "accounts"]
  return count === 1 ? one : many
}

interface AccountSelectorProps {
  integration: IntegrationPublic
  /** Whether the user may change which accounts are shown (owner / admin). */
  editable: boolean
}

/**
 * Which of an integration's accounts (e.g. the Facebook Pages it manages)
 * the dashboards show. Only offered when there is a choice to make.
 */
export function AccountSelector({
  integration,
  editable,
}: AccountSelectorProps) {
  const [open, setOpen] = useState(false)
  const setShown = useSetAccountShown(integration)
  const accounts = integration.accounts ?? []
  const shownCount = accounts.filter((a) => a.is_active).length
  // A single shown account is no choice, but a hidden one must be reachable
  if (accounts.length < 2 && shownCount === accounts.length) return null

  const nouns = accountNoun(integration.platform, 2)
  const title = `${platformLabel(integration.platform)} ${nouns}`

  return (
    <>
      <Button
        variant="link"
        size="sm"
        className="h-auto p-0 text-xs"
        onClick={() => setOpen(true)}
      >
        {shownCount} of {accounts.length}{" "}
        {accountNoun(integration.platform, accounts.length)} shown
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            <DialogDescription>
              {editable
                ? `Choose the ${nouns} the dashboards show. Hidden ${nouns} keep syncing.`
                : `The ${nouns} the dashboards show. Only workspace owners and admins can change them.`}
            </DialogDescription>
          </DialogHeader>
          <ul className="space-y-1">
            {accounts.map((account) => {
              const id = `account-${account.id}`
              return (
                <li key={account.id}>
                  <label
                    htmlFor={id}
                    className="flex cursor-pointer items-center gap-3 rounded-md p-2 hover:bg-muted has-disabled:cursor-default has-disabled:hover:bg-transparent"
                  >
                    <Checkbox
                      id={id}
                      checked={account.is_active}
                      disabled={!editable || setShown.isPending}
                      onCheckedChange={(checked) =>
                        setShown.mutate({ account, shown: checked === true })
                      }
                    />
                    <Avatar className="size-7">
                      {account.avatar_url && (
                        <AvatarImage src={account.avatar_url} alt="" />
                      )}
                      <AvatarFallback className="text-xs">
                        {account.name.charAt(0).toUpperCase()}
                      </AvatarFallback>
                    </Avatar>
                    <span className="truncate text-sm">{account.name}</span>
                  </label>
                </li>
              )
            })}
          </ul>
        </DialogContent>
      </Dialog>
    </>
  )
}
