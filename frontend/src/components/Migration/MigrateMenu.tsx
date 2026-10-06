import { ArrowRightLeft, FileUp } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import type { MigrateActions } from "./MigrateDialogs"
import { MIGRATION_SOURCES, SOURCES } from "./sources"

/**
 * "Migrate from…": bring history over from another social media tool,
 * through its API or from a CSV export.
 */
export function MigrateMenu({ openSource, openUpload }: MigrateActions) {
  return (
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
          <DropdownMenuItem key={s} onClick={() => openSource(s)}>
            {SOURCES[s].label}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={openUpload}>
          <FileUp className="size-4" />
          Upload an export (CSV)…
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
