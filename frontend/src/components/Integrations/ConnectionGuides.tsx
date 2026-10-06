import { BookOpen, Loader2, Plug } from "lucide-react"

import type { Platform } from "@/client"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useConnectPlatform } from "@/hooks/useIntegrations"
import { PLATFORM_LABELS } from "@/lib/platforms"
import { GuideBody } from "./GuideBody"
import {
  CONNECTION_GUIDES,
  type ConnectionGuide,
  GUIDES_REVIEWED_ON,
} from "./guideContent"
import { PlatformIcon } from "./PlatformIcon"

/** One step-by-step tutorial per available platform, as tabs. */
export function ConnectionGuides({
  available,
  editable,
}: {
  available: Platform[]
  editable: boolean
}) {
  if (available.length === 0) return null
  return (
    <Card data-connection-guides>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <BookOpen className="size-4" />
          How to connect your accounts
        </CardTitle>
        <CardDescription>
          Pick a platform below and follow the steps. Each one takes about 2
          minutes. Guides last checked: {GUIDES_REVIEWED_ON}.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue={available[0]}>
          <TabsList className="h-auto w-full flex-wrap justify-start">
            {available.map((platform) => (
              <TabsTrigger
                key={platform}
                value={platform}
                className="flex-none px-3 py-1.5"
              >
                <PlatformIcon
                  platform={platform}
                  className="size-5 text-[10px]"
                />
                {PLATFORM_LABELS[platform]}
              </TabsTrigger>
            ))}
          </TabsList>
          {available.map((platform) => (
            <TabsContent key={platform} value={platform} className="pt-4">
              <Guide
                platform={platform}
                guide={CONNECTION_GUIDES[platform]}
                editable={editable}
              />
            </TabsContent>
          ))}
        </Tabs>
      </CardContent>
    </Card>
  )
}

function Guide({
  platform,
  guide,
  editable,
}: {
  platform: Platform
  guide: ConnectionGuide
  editable: boolean
}) {
  const label = PLATFORM_LABELS[platform]
  const { connect, pending } = useConnectPlatform()

  return (
    <GuideBody
      guide={guide}
      action={
        editable ? (
          <Button onClick={() => connect(platform)} disabled={pending !== null}>
            {pending ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Plug className="size-4" />
            )}
            Connect {label} now
          </Button>
        ) : (
          <p className="text-sm text-muted-foreground">
            Only workspace owners and admins can connect platforms. Send this
            guide to one of them.
          </p>
        )
      }
    />
  )
}
