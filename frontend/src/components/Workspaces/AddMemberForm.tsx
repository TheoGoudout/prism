import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { WorkspacesService } from "@/client"
import { TextField } from "@/components/Common/FormFields"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { LoadingButton } from "@/components/ui/loading-button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { useCurrentWorkspace } from "@/contexts/WorkspaceContext"
import useCustomToast from "@/hooks/useCustomToast"
import { ROLE_LABELS, ROLES } from "./roles"

const addSchema = z.object({
  email: z.email({ message: "Enter a valid email address" }),
  role: z.enum(["viewer", "admin", "owner"]),
})

type AddFormData = z.infer<typeof addSchema>

export function AddMemberForm() {
  const workspace = useCurrentWorkspace()
  const workspaceId = workspace.id
  const queryClient = useQueryClient()
  const { showSuccessToast, showApiError } = useCustomToast()
  const form = useForm<AddFormData>({
    resolver: zodResolver(addSchema),
    defaultValues: { email: "", role: "viewer" },
  })

  const mutation = useMutation({
    mutationFn: (data: AddFormData) =>
      WorkspacesService.addMember({ workspaceId, requestBody: data }),
    onSuccess: (member) => {
      showSuccessToast(`${member.user_email} added to the workspace`)
      form.reset()
    },
    onError: showApiError,
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: ["members", workspaceId] }),
  })

  // Only owners can grant the owner role
  const grantable = ROLES.filter(
    (r) => r !== "owner" || workspace.role === "owner",
  )

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit((d) => mutation.mutate(d))}
        className="flex flex-col gap-3 sm:flex-row sm:items-end"
      >
        <TextField
          control={form.control}
          name="email"
          label="Email"
          type="email"
          placeholder="teammate@example.com"
          className="flex-1"
        />
        <FormField
          control={form.control}
          name="role"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Role</FormLabel>
              <Select value={field.value} onValueChange={field.onChange}>
                <FormControl>
                  <SelectTrigger className="w-full sm:w-32">
                    <SelectValue />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {grantable.map((r) => (
                    <SelectItem key={r} value={r}>
                      {ROLE_LABELS[r]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          )}
        />
        <LoadingButton type="submit" loading={mutation.isPending}>
          Add member
        </LoadingButton>
      </form>
    </Form>
  )
}
