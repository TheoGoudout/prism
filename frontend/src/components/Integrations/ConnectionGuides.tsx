import { BookOpen, ExternalLink, Loader2, Plug } from "lucide-react"
import { useState } from "react"

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
import {
  CONNECTION_GUIDES,
  type ConnectionGuide,
  GUIDES_REVIEWED_ON,
  type GuideStep,
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
    <div className="space-y-6">
      <p className="text-sm">{guide.summary}</p>

      <section className="rounded-lg border bg-muted/40 p-4">
        <h3 className="mb-2 text-sm font-semibold">Before you start</h3>
        <ul className="list-disc space-y-1.5 pl-5 text-sm">
          {guide.beforeYouStart.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
      </section>

      <ol className="space-y-6">
        {guide.steps.map((step, i) => (
          <Step key={step.title} number={i + 1} step={step} />
        ))}
      </ol>

      <section>
        <h3 className="mb-2 text-sm font-semibold">Something went wrong?</h3>
        <ul className="list-disc space-y-1.5 pl-5 text-sm text-muted-foreground">
          {guide.troubleshooting.map((item, i) => (
            <li key={i}>{item}</li>
          ))}
        </ul>
        <a
          href={guide.helpLink.href}
          target="_blank"
          rel="noreferrer"
          className="mt-3 inline-flex items-center gap-1 text-sm text-primary underline-offset-4 hover:underline"
        >
          {guide.helpLink.label}
          <ExternalLink className="size-3.5" />
        </a>
      </section>

      {editable ? (
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
      )}
    </div>
  )
}

function Step({ number, step }: { number: number; step: GuideStep }) {
  // Screenshots of the platforms' screens may not have been captured yet
  const [imageMissing, setImageMissing] = useState(false)
  return (
    <li className="flex gap-3">
      <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">
        {number}
      </span>
      <div className="min-w-0 flex-1 space-y-2 pt-0.5">
        <h4 className="font-medium">{step.title}</h4>
        <p className="text-sm text-muted-foreground">{step.body}</p>
        {step.image && !imageMissing && (
          <a
            href={step.image.src}
            target="_blank"
            rel="noreferrer"
            title="Open the full-size image"
            className="block max-w-xl"
          >
            <img
              src={step.image.src}
              alt={step.image.alt}
              loading="lazy"
              onError={() => setImageMissing(true)}
              className="w-full rounded-md border shadow-sm"
            />
          </a>
        )}
      </div>
    </li>
  )
}
