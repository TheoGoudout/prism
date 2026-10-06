import { ExternalLink } from "lucide-react"
import { type ReactNode, useState } from "react"

import type { ConnectionGuide, GuideStep } from "./guideContent"

/**
 * A step-by-step guide: what to have ready, the numbered steps, what to do
 * when something goes wrong, then ``action`` (e.g. a button starting it).
 */
export function GuideBody({
  guide,
  action,
}: {
  guide: ConnectionGuide
  action: ReactNode
}) {
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
        {guide.helpLink && (
          <a
            href={guide.helpLink.href}
            target="_blank"
            rel="noreferrer"
            className="mt-3 inline-flex items-center gap-1 text-sm text-primary underline-offset-4 hover:underline"
          >
            {guide.helpLink.label}
            <ExternalLink className="size-3.5" />
          </a>
        )}
      </section>

      {action}
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
