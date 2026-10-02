import {
  CheckCircle2,
  Lightbulb,
  ThumbsDown,
  ThumbsUp,
  XCircle,
} from "lucide-react"
import { useState } from "react"

import type {
  AnalysisResult,
  AnalyzedPost,
  Finding,
  Platform,
  PostAnalysis,
  Recommendation,
} from "@/client"
import { PlatformIcon } from "@/components/Integrations/PlatformIcon"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { formatCompact } from "@/lib/format"
import { PLATFORM_LABELS, platformLabel } from "@/lib/platforms"
import { cn } from "@/lib/utils"
import type { Verdict } from "./labels"
import { VERDICT_LABELS } from "./labels"
import { VerdictBadge } from "./VerdictBadge"

const PRIORITY_CLASSES: Record<
  NonNullable<Recommendation["priority"]>,
  string
> = {
  high: "border-transparent bg-destructive/15 text-destructive",
  medium:
    "border-transparent bg-amber-500/15 text-amber-700 dark:text-amber-400",
  low: "border-transparent bg-secondary text-secondary-foreground",
}

/** "2026-03" → "Mar 2026"; other labels are shown as they are. */
function formatMonth(label: string): string {
  const match = /^(\d{4})-(\d{2})$/.exec(label)
  if (!match) return label
  return new Date(Number(match[1]), Number(match[2]) - 1).toLocaleDateString(
    undefined,
    { month: "short", year: "numeric" },
  )
}

function MaybePlatformIcon({ platform }: { platform: string }) {
  return platform in PLATFORM_LABELS ? (
    <PlatformIcon platform={platform as Platform} className="size-6" />
  ) : null
}

function FindingsCard({
  title,
  findings,
  positive,
}: {
  title: string
  findings: Finding[]
  positive: boolean
}) {
  const Icon = positive ? CheckCircle2 : XCircle
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          {positive ? (
            <ThumbsUp className="size-4 text-green-600" />
          ) : (
            <ThumbsDown className="size-4 text-destructive" />
          )}
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {findings.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nothing stood out.</p>
        ) : (
          <ul className="space-y-3">
            {findings.map((finding) => (
              <li key={finding.title} className="flex gap-3 text-sm">
                <Icon
                  className={cn(
                    "mt-0.5 size-4 shrink-0",
                    positive ? "text-green-600" : "text-destructive",
                  )}
                />
                <div>
                  <p className="font-medium">{finding.title}</p>
                  <p className="text-muted-foreground">{finding.detail}</p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

function PostRow({
  analysis,
  post,
}: {
  analysis: PostAnalysis
  post: AnalyzedPost | undefined
}) {
  const text = post?.text?.trim() || "(no text)"
  return (
    <li className="space-y-2 border-b py-4 last:border-b-0">
      <div className="flex items-start gap-3">
        {post && <MaybePlatformIcon platform={post.platform} />}
        <div className="min-w-0 flex-1">
          {post?.permalink ? (
            <a
              href={post.permalink}
              target="_blank"
              rel="noopener noreferrer"
              className="line-clamp-2 text-sm font-medium hover:underline"
            >
              {text}
            </a>
          ) : (
            <p className="line-clamp-2 text-sm font-medium">
              {post ? text : "Post no longer available"}
            </p>
          )}
          {post && (
            <p className="mt-1 text-xs text-muted-foreground">
              {platformLabel(post.platform)} · {post.content_type} ·{" "}
              {new Date(post.published_at).toLocaleDateString()} ·{" "}
              {formatCompact(post.engagements)} engagements ·{" "}
              {formatCompact(post.reach ?? post.impressions)} reach
              {post.engagement_rate != null &&
                ` · ${(post.engagement_rate * 100).toFixed(1)}% rate`}
            </p>
          )}
        </div>
        <VerdictBadge verdict={analysis.verdict} />
      </div>
      <p className="text-sm">{analysis.analysis}</p>
      {analysis.suggestion && (
        <p className="flex gap-2 text-sm text-muted-foreground">
          <Lightbulb className="mt-0.5 size-4 shrink-0 text-amber-500" />
          {analysis.suggestion}
        </p>
      )}
    </li>
  )
}

/** The full result of a completed analysis. */
export function AnalysisReport({
  result,
  posts,
  yearly = false,
}: {
  result: AnalysisResult
  posts: AnalyzedPost[]
  yearly?: boolean
}) {
  const [verdict, setVerdict] = useState<Verdict | null>(null)
  const [topic, setTopic] = useState<string | null>(null)

  const postsById = new Map(posts.map((p) => [p.id, p]))
  const topics = result.topics ?? []
  const selectedTopic = topics.find((t) => t.name === topic)
  const postAnalyses = (result.posts ?? []).filter(
    (p) =>
      (!verdict || p.verdict === verdict) &&
      (!selectedTopic || selectedTopic.post_ids?.includes(p.post_id)),
  )

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Summary</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm leading-relaxed">{result.summary}</p>
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <FindingsCard
          title="What worked"
          findings={result.what_worked ?? []}
          positive
        />
        <FindingsCard
          title="What didn't work"
          findings={result.what_didnt_work ?? []}
          positive={false}
        />
      </div>

      {!!result.recommendations?.length && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Lightbulb className="size-4 text-amber-500" />
              How to improve
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="space-y-3">
              {result.recommendations.map((rec, i) => (
                <li key={rec.title} className="flex gap-3 text-sm">
                  <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-medium">
                    {i + 1}
                  </span>
                  <div>
                    <p className="flex flex-wrap items-center gap-2 font-medium">
                      {rec.title}
                      <Badge
                        className={PRIORITY_CLASSES[rec.priority ?? "medium"]}
                      >
                        {rec.priority ?? "medium"} priority
                      </Badge>
                    </p>
                    <p className="text-muted-foreground">{rec.detail}</p>
                  </div>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
      )}

      {!!result.periods?.length && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Month by month</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="divide-y">
              {result.periods.map((period) => (
                <li
                  key={period.label}
                  className="flex flex-col gap-1 py-3 text-sm sm:flex-row sm:items-start sm:gap-4"
                >
                  <span className="flex w-40 shrink-0 items-center gap-2 font-medium">
                    {formatMonth(period.label)}
                    <VerdictBadge verdict={period.verdict} />
                  </span>
                  <span className="text-muted-foreground">
                    {period.summary}
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {!!result.platforms?.length && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">By platform</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-2">
            {result.platforms.map((platform) => (
              <div
                key={platform.platform}
                className="space-y-2 rounded-lg border p-4"
              >
                <div className="flex items-center gap-2">
                  <MaybePlatformIcon platform={platform.platform} />
                  <span className="font-medium">
                    {platformLabel(platform.platform)}
                  </span>
                  <VerdictBadge
                    verdict={platform.verdict}
                    className="ml-auto"
                  />
                </div>
                <p className="text-sm text-muted-foreground">
                  {platform.summary}
                </p>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {topics.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Topics</CardTitle>
            <CardDescription>
              Posts grouped by subject. Select one to see its posts below.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-2">
            {topics.map((t) => (
              <button
                key={t.name}
                type="button"
                onClick={() => setTopic(topic === t.name ? null : t.name)}
                className={cn(
                  "space-y-2 rounded-lg border p-4 text-left transition-colors hover:bg-accent",
                  topic === t.name && "border-primary bg-accent",
                )}
              >
                <div className="flex items-center gap-2">
                  <span className="font-medium">{t.name}</span>
                  <span className="text-xs text-muted-foreground">
                    {t.post_ids?.length ?? 0} posts
                  </span>
                  <VerdictBadge verdict={t.verdict} className="ml-auto" />
                </div>
                <p className="text-sm text-muted-foreground">{t.summary}</p>
              </button>
            ))}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="gap-3">
          <CardTitle className="text-base">
            {yearly ? "Notable posts" : "Posts"}
            {selectedTopic && ` · ${selectedTopic.name}`}
          </CardTitle>
          {yearly && (
            <CardDescription>
              The year's best and worst performers, analyzed one by one.
            </CardDescription>
          )}
          <div className="flex flex-wrap gap-2">
            {([null, "strong", "average", "weak"] as const).map((v) => (
              <Button
                key={v ?? "all"}
                size="sm"
                variant={verdict === v ? "secondary" : "ghost"}
                onClick={() => setVerdict(v)}
              >
                {v ? VERDICT_LABELS[v] : "All"}
              </Button>
            ))}
            {selectedTopic && (
              <Button size="sm" variant="ghost" onClick={() => setTopic(null)}>
                <XCircle className="size-4" />
                Clear topic
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {postAnalyses.length === 0 ? (
            <p className="py-4 text-center text-sm text-muted-foreground">
              No posts match.
            </p>
          ) : (
            <ul>
              {postAnalyses.map((analysis) => (
                <PostRow
                  key={analysis.post_id}
                  analysis={analysis}
                  post={postsById.get(analysis.post_id)}
                />
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
