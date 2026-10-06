import { format, subYears } from "date-fns"
import { ArrowLeft, ArrowRightLeft, ExternalLink, Search } from "lucide-react"
import { type ReactNode, useState } from "react"

import type {
  MigrationSource,
  PlatformAccountPublic,
  RemoteProfile,
} from "@/client"
import { PlatformIcon } from "@/components/Integrations/PlatformIcon"
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
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { LoadingButton } from "@/components/ui/loading-button"
import { PasswordInput } from "@/components/ui/password-input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  useMigrationAccounts,
  useSourceProfiles,
  useStartMigration,
} from "@/hooks/useMigrations"
import { platformLabel } from "@/lib/platforms"
import { SOURCES } from "./sources"

const SKIP = "skip"
const PERIODS = [1, 2, 3, 5]

/**
 * Migrate from another tool's API in two steps: credentials, then which of
 * its profiles go into which Prism account.
 */
export function ApiMigrationDialog({
  source,
  open,
  onOpenChange,
}: {
  source: MigrationSource
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const info = SOURCES[source]
  const [token, setToken] = useState("")
  const [userId, setUserId] = useState("")
  const [blogId, setBlogId] = useState("")
  const [years, setYears] = useState("2")
  const [mapping, setMapping] = useState<Record<string, string>>({})

  const accounts = useMigrationAccounts(open)
  const profilesMut = useSourceProfiles(source)
  const startMut = useStartMigration(source)
  const profiles = profilesMut.data

  const credentials = {
    api_token: token.trim(),
    user_id: info.needsUserId ? userId.trim() || null : null,
    blog_id: info.needsUserId ? blogId.trim() || null : null,
  }
  const canSearch =
    !!credentials.api_token && (!info.needsUserId || !!credentials.user_id)
  const selected = Object.entries(mapping).filter(([, id]) => id !== SKIP)

  const reset = () => {
    profilesMut.reset()
    setMapping({})
  }

  const findProfiles = () =>
    profilesMut.mutate(credentials, {
      onSuccess: (found) =>
        setMapping(
          Object.fromEntries(
            found.map((p) => [p.id, p.suggested_account_id ?? SKIP]),
          ),
        ),
    })

  const start = () =>
    startMut.mutate(
      {
        credentials,
        profiles: selected.map(([remote, account]) => ({
          remote_profile_id: remote,
          platform_account_id: account,
        })),
        date_from: format(subYears(new Date(), Number(years)), "yyyy-MM-dd"),
      },
      {
        // The menu mounts a fresh dialog each time it opens
        onSuccess: () => onOpenChange(false),
      },
    )

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Migrate from {info.label}</DialogTitle>
          <DialogDescription>
            {profiles
              ? "Choose the Prism account each profile's history goes into."
              : `Prism fetches your posts and daily metrics from ${info.label} and adds them to your connected accounts.`}
          </DialogDescription>
        </DialogHeader>

        {!profiles ? (
          <form
            className="flex flex-col gap-4"
            onSubmit={(e) => {
              e.preventDefault()
              if (canSearch) findProfiles()
            }}
          >
            <ol className="flex list-decimal flex-col gap-1 pl-5 text-sm text-muted-foreground">
              {info.steps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
            <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
              <span className="text-muted-foreground">{info.requirement}</span>
              <ExternalAnchor href={info.appUrl}>
                Open {info.label}
              </ExternalAnchor>
              <ExternalAnchor href={info.docs.href}>
                {info.docs.label}
              </ExternalAnchor>
            </p>
            <div className="flex flex-col gap-2">
              <Label htmlFor="migration-token">API token</Label>
              <PasswordInput
                id="migration-token"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                autoComplete="off"
              />
            </div>
            {info.needsUserId && (
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="flex flex-col gap-2">
                  <Label htmlFor="migration-user-id">User ID</Label>
                  <Input
                    id="migration-user-id"
                    value={userId}
                    onChange={(e) => setUserId(e.target.value)}
                    inputMode="numeric"
                  />
                </div>
                <div className="flex flex-col gap-2">
                  <Label htmlFor="migration-blog-id">
                    Brand ID{" "}
                    <span className="font-normal text-muted-foreground">
                      (optional)
                    </span>
                  </Label>
                  <Input
                    id="migration-blog-id"
                    value={blogId}
                    onChange={(e) => setBlogId(e.target.value)}
                    inputMode="numeric"
                  />
                </div>
              </div>
            )}
            <p className="text-xs text-muted-foreground">
              Your credentials are only used for this migration: they're stored
              encrypted while it runs, then deleted.
            </p>
            <DialogFooter>
              <DialogClose asChild>
                <Button variant="outline" type="button">
                  Cancel
                </Button>
              </DialogClose>
              <LoadingButton
                type="submit"
                loading={profilesMut.isPending}
                disabled={!canSearch}
              >
                <Search />
                Find profiles
              </LoadingButton>
            </DialogFooter>
          </form>
        ) : (
          <div className="flex flex-col gap-4">
            {profiles.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No profiles were found in this {info.label} account.
              </p>
            ) : (
              <ul className="flex max-h-80 flex-col gap-3 overflow-y-auto">
                {profiles.map((profile) => (
                  <ProfileRow
                    key={profile.id}
                    profile={profile}
                    accounts={(accounts.data ?? []).filter(
                      (a) => a.platform === profile.platform,
                    )}
                    value={mapping[profile.id] ?? SKIP}
                    onChange={(value) =>
                      setMapping((m) => ({ ...m, [profile.id]: value }))
                    }
                  />
                ))}
              </ul>
            )}
            {accounts.data?.length === 0 && (
              <p className="text-sm text-muted-foreground">
                Connect your accounts in Prism first: history is added to
                accounts that have synced at least once.
              </p>
            )}
            <div className="flex flex-col gap-2">
              <Label>History to migrate</Label>
              <Select value={years} onValueChange={setYears}>
                <SelectTrigger
                  className="w-full"
                  aria-label="History to migrate"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PERIODS.map((y) => (
                    <SelectItem key={y} value={String(y)}>
                      Last {y === 1 ? "year" : `${y} years`}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <DialogFooter>
              <Button variant="outline" type="button" onClick={reset}>
                <ArrowLeft />
                Back
              </Button>
              <LoadingButton
                loading={startMut.isPending}
                disabled={selected.length === 0}
                onClick={start}
              >
                <ArrowRightLeft />
                Migrate{" "}
                {selected.length === 1
                  ? "1 profile"
                  : `${selected.length} profiles`}
              </LoadingButton>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

function ProfileRow({
  profile,
  accounts,
  value,
  onChange,
}: {
  profile: RemoteProfile
  accounts: PlatformAccountPublic[]
  value: string
  onChange: (value: string) => void
}) {
  return (
    <li className="flex flex-col gap-2 sm:flex-row sm:items-center">
      <div className="flex min-w-0 flex-1 items-center gap-2">
        {profile.platform && (
          <PlatformIcon
            platform={profile.platform}
            className="size-6 text-[10px]"
          />
        )}
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{profile.name}</p>
          <p className="text-xs text-muted-foreground capitalize">
            {profile.platform
              ? platformLabel(profile.platform)
              : profile.network}
          </p>
        </div>
      </div>
      {profile.platform ? (
        <Select value={value} onValueChange={onChange}>
          <SelectTrigger
            className="w-full sm:w-56"
            aria-label={`Prism account for ${profile.name}`}
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={SKIP}>Don't migrate</SelectItem>
            {accounts.map((account) => (
              <SelectItem key={account.id} value={account.id}>
                {account.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ) : (
        <span className="text-xs text-muted-foreground sm:w-56">
          Not supported by Prism
        </span>
      )}
    </li>
  )
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
      className="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline"
    >
      {children}
      <ExternalLink className="size-3.5" />
    </a>
  )
}
