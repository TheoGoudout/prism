import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useForm } from "react-hook-form"
import { z } from "zod"
import { WorkspacesService } from "@/client"
import { CancelButton } from "@/components/Common/CancelButton"
import { TextField } from "@/components/Common/FormFields"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Form } from "@/components/ui/form"
import { LoadingButton } from "@/components/ui/loading-button"
import useCustomToast from "@/hooks/useCustomToast"

const formSchema = z.object({
  name: z.string().min(1, { message: "Name is required" }),
})

type FormData = z.infer<typeof formSchema>

interface CreateWorkspaceModalProps {
  isOpen: boolean
  onClose: () => void
}

export default function CreateWorkspaceModal({
  isOpen,
  onClose,
}: CreateWorkspaceModalProps) {
  const queryClient = useQueryClient()
  const { showSuccessToast, showApiError } = useCustomToast()

  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    defaultValues: { name: "" },
  })

  const mutation = useMutation({
    mutationFn: (data: FormData) =>
      WorkspacesService.createWorkspace({ requestBody: data }),
    onSuccess: () => {
      showSuccessToast("Workspace created successfully")
      form.reset()
      onClose()
    },
    onError: showApiError,
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["workspaces"] })
    },
  })

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>New workspace</DialogTitle>
          <DialogDescription>
            Create a workspace to organise your social media integrations.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit((d) => mutation.mutate(d))}>
            <div className="py-4">
              <TextField
                control={form.control}
                name="name"
                label="Name"
                placeholder="My brand"
                required
              />
            </div>
            <DialogFooter>
              <CancelButton disabled={mutation.isPending} />
              <LoadingButton type="submit" loading={mutation.isPending}>
                Create
              </LoadingButton>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
