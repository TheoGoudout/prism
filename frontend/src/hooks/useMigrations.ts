import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import type {
  ExportFormat,
  MigrationCreate,
  MigrationPublic,
  MigrationSource,
  SourceCredentials,
} from "@/client"
import { MigrateService } from "@/client"
import { useCurrentWorkspace } from "@/contexts/WorkspaceContext"
import useCustomToast from "@/hooks/useCustomToast"
import { pollWhileUnfinished } from "@/lib/jobs"

/** The accounts history can be migrated into: those found by a sync. */
export function useMigrationAccounts(enabled = true) {
  const workspace = useCurrentWorkspace()
  return useQuery({
    queryKey: ["migration-accounts", workspace.id],
    queryFn: () =>
      MigrateService.listMigrationAccounts({ workspaceId: workspace.id }),
    enabled,
  })
}

/** The workspace's API migrations, refreshed while one is still running. */
export function useMigrations() {
  const workspace = useCurrentWorkspace()
  return useQuery({
    queryKey: ["migrations", workspace.id],
    queryFn: () => MigrateService.listMigrations({ workspaceId: workspace.id }),
    refetchInterval: pollWhileUnfinished((migrations: MigrationPublic[]) =>
      migrations.map((m) => m.status),
    ),
  })
}

/** Check the credentials and list the source's profiles. */
export function useSourceProfiles(source: MigrationSource) {
  const workspace = useCurrentWorkspace()
  const { showApiError } = useCustomToast()
  return useMutation({
    mutationFn: (credentials: SourceCredentials) =>
      MigrateService.listSourceProfiles({
        workspaceId: workspace.id,
        source,
        requestBody: credentials,
      }),
    onError: showApiError,
  })
}

export function useStartMigration(source: MigrationSource) {
  const workspace = useCurrentWorkspace()
  const queryClient = useQueryClient()
  const { showSuccessToast, showApiError } = useCustomToast()
  return useMutation({
    mutationFn: (migration: MigrationCreate) =>
      MigrateService.startMigration({
        workspaceId: workspace.id,
        source,
        requestBody: migration,
      }),
    onSuccess: () =>
      showSuccessToast(
        "Migration started. It runs in the background and can take a while.",
      ),
    onError: showApiError,
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: ["migrations", workspace.id] }),
  })
}

export function useUploadExport() {
  const workspace = useCurrentWorkspace()
  const { showApiError } = useCustomToast()
  return useMutation({
    mutationFn: (upload: {
      accountId: string
      file: File
      format: ExportFormat | null
    }) =>
      MigrateService.uploadExport({
        workspaceId: workspace.id,
        formData: {
          platform_account_id: upload.accountId,
          // The generated client types binary uploads as strings
          file: upload.file as unknown as string,
          export_format: upload.format,
        },
      }),
    onError: showApiError,
  })
}
