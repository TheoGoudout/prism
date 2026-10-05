import { ArrowRightLeft, FileUp } from "lucide-react"
import { useState } from "react"

import type { MigrationSource } from "@/client"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { ApiMigrationDialog } from "./ApiMigrationDialog"
import { MIGRATION_SOURCES, SOURCES } from "./sources"
import { UploadExportDialog } from "./UploadExportDialog"

/**
 * "Migrate from…": bring history over from another social media tool,
 * through its API or from a CSV export.
 */
export function MigrateMenu() {
  const [source, setSource] = useState<MigrationSource | null>(null)
  const [uploading, setUploading] = useState(false)
  // Keep the last source mounted while its dialog closes; each opening
  // mounts a fresh dialog, so no credentials linger from the last one
  const [lastSource, setLastSource] = useState<MigrationSource>("sprout_social")
  const [openings, setOpenings] = useState(0)

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline">
            <ArrowRightLeft className="mr-2 size-4" />
            Migrate from…
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuLabel className="text-xs text-muted-foreground">
            Connect your account
          </DropdownMenuLabel>
          {MIGRATION_SOURCES.map((s) => (
            <DropdownMenuItem
              key={s}
              onClick={() => {
                setLastSource(s)
                setSource(s)
                setOpenings((n) => n + 1)
              }}
            >
              {SOURCES[s].label}
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => setUploading(true)}>
            <FileUp className="size-4" />
            Upload an export (CSV)…
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <ApiMigrationDialog
        key={openings}
        source={lastSource}
        open={source !== null}
        onOpenChange={(open) => !open && setSource(null)}
      />
      <UploadExportDialog open={uploading} onOpenChange={setUploading} />
    </>
  )
}
