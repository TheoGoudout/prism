import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { WorkspacesService } from "@/client"
import ConfirmDialog from "@/components/Common/ConfirmDialog"
import { TextField } from "@/components/Common/FormFields"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Form } from "@/components/ui/form"
import { LoadingButton } from "@/components/ui/loading-button"
import { useCurrentWorkspace } from "@/contexts/WorkspaceContext"
import useCustomToast from "@/hooks/useCustomToast"
import { canManage } from "./roles"

const formSchema = z.object({
  name: z.string().min(1, { message: "Name is required" }).max(255),
})

type FormData = z.infer<typeof formSchema>

export default function WorkspaceGeneral() {
  const workspace = useCurrentWorkspace()
  const queryClient = useQueryClient()
  const { showSuccessToast, showApiError } = useCustomToast()
  const [confirmDelete, setConfirmDelete] = useState(false)

  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    values: { name: workspace.name },
  })

  const renameMut = useMutation({
    mutationFn: (data: FormData) =>
      WorkspacesService.updateWorkspace({
        workspaceId: workspace.id,
        requestBody: data,
      }),
    onSuccess: () => showSuccessToast("Workspace updated"),
    onError: showApiError,
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: ["workspaces"] }),
  })

  const deleteMut = useMutation({
    mutationFn: () =>
      WorkspacesService.deleteWorkspace({ workspaceId: workspace.id }),
    onSuccess: () => {
      showSuccessToast("Workspace deleted")
      setConfirmDelete(false)
      queryClient.invalidateQueries({ queryKey: ["workspaces"] })
    },
    onError: showApiError,
  })
  const editable = canManage(workspace)

  return (
    <div className="flex flex-col gap-6 max-w-xl">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">General</CardTitle>
          <CardDescription>
            {editable
              ? "Rename this workspace."
              : "Only owners and admins can change workspace settings."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form
              onSubmit={form.handleSubmit((d) => renameMut.mutate(d))}
              className="flex flex-col gap-4"
            >
              <TextField
                control={form.control}
                name="name"
                label="Name"
                disabled={!editable}
              />
              {editable && (
                <LoadingButton
                  type="submit"
                  className="self-start"
                  loading={renameMut.isPending}
                  disabled={!form.formState.isDirty}
                >
                  Save
                </LoadingButton>
              )}
            </form>
          </Form>
        </CardContent>
      </Card>

      {workspace.role === "owner" && (
        <Card className="border-destructive/50">
          <CardHeader>
            <CardTitle className="text-base text-destructive">
              Delete workspace
            </CardTitle>
            <CardDescription>
              Permanently delete this workspace, its integrations and all synced
              metrics.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button
              variant="destructive"
              onClick={() => setConfirmDelete(true)}
            >
              Delete workspace
            </Button>
          </CardContent>
        </Card>
      )}

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete workspace"
        description={
          <>
            <strong>{workspace.name}</strong> and all of its data will be
            permanently deleted. This cannot be undone.
          </>
        }
        confirmLabel="Delete"
        loading={deleteMut.isPending}
        onConfirm={() => deleteMut.mutate()}
      />
    </div>
  )
}
