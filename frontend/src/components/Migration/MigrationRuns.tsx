import { ArrowRightLeft, Loader2 } from "lucide-react"

import type { MigrationPublic, MigrationStatus } from "@/client"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useMigrations } from "@/hooks/useMigrations"
import { formatRelative, plural } from "@/lib/format"
import { isUnfinished } from "@/lib/jobs"
import { cn } from "@/lib/utils"
import { sourceLabel } from "./sources"

const STATUS_LABELS: Record<MigrationStatus, string> = {
  pending: "Waiting",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
}

/** The workspace's migrations from other tools; hidden until there is one. */
export function MigrationRuns() {
  const { data } = useMigrations()
  if (!data?.length) return null
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <ArrowRightLeft className="size-4" />
          Migrations
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col divide-y">
        {data.map((migration) => (
          <MigrationRun key={migration.id} migration={migration} />
        ))}
      </CardContent>
    </Card>
  )
}

function MigrationRun({ migration }: { migration: MigrationPublic }) {
  const running = isUnfinished(migration.status)
  return (
    <div className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{sourceLabel(migration.source)}</span>
        <Badge
          variant={migration.status === "failed" ? "destructive" : "secondary"}
          className={cn(
            migration.status === "completed" &&
              "border-transparent bg-success/12 text-success",
          )}
        >
          {running && <Loader2 className="size-3 animate-spin" />}
          {STATUS_LABELS[migration.status]}
        </Badge>
        <span className="text-xs text-muted-foreground">
          Since {migration.date_from}
          {migration.created_at &&
            ` · started ${formatRelative(migration.created_at)}`}
        </span>
      </div>
      {migration.error && (
        <p className="text-sm text-destructive">{migration.error}</p>
      )}
      <ul className="flex flex-col gap-1 text-sm">
        {migration.profiles.map(({ errors = [], ...profile }) => (
          <li key={profile.remote_profile_id} className="text-muted-foreground">
            <span className="text-foreground">{profile.name}</span>
            {profile.done
              ? `: ${profile.posts} posts, ${profile.days} days of metrics`
              : running
                ? ": waiting…"
                : ": not migrated"}
            {errors.length > 0 && (
              <span title={errors.join("\n")}>
                {" "}
                ({plural(errors.length, "part")} couldn't be fetched)
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
