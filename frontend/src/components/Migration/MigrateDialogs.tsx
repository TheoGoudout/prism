import { type ReactNode, useState } from "react"

import type { MigrationSource } from "@/client"
import { ApiMigrationDialog } from "./ApiMigrationDialog"
import { UploadExportDialog } from "./UploadExportDialog"

export interface MigrateActions {
  openSource: (source: MigrationSource) => void
  openUpload: () => void
}

/**
 * The migration dialogs, and the actions opening them, so the "Migrate
 * from…" menu and the guides open the same dialogs.
 */
export function useMigrateDialogs(): MigrateActions & { dialogs: ReactNode } {
  const [source, setSource] = useState<MigrationSource | null>(null)
  const [uploading, setUploading] = useState(false)
  // Keep the last source mounted while its dialog closes; each opening
  // mounts a fresh dialog, so no credentials linger from the last one
  const [lastSource, setLastSource] = useState<MigrationSource>("sprout_social")
  const [openings, setOpenings] = useState(0)

  return {
    openSource: (s) => {
      setLastSource(s)
      setSource(s)
      setOpenings((n) => n + 1)
    },
    openUpload: () => setUploading(true),
    dialogs: (
      <>
        <ApiMigrationDialog
          key={openings}
          source={lastSource}
          open={source !== null}
          onOpenChange={(open) => !open && setSource(null)}
        />
        <UploadExportDialog open={uploading} onOpenChange={setUploading} />
      </>
    ),
  }
}
