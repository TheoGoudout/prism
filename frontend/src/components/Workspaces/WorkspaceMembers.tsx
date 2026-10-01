import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { LogOut, Trash2 } from "lucide-react"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import type { WorkspaceMemberPublic, WorkspaceRole } from "@/client"
import { WorkspacesService } from "@/client"
import ConfirmDialog from "@/components/Common/ConfirmDialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useWorkspace } from "@/contexts/WorkspaceContext"
import useAuth from "@/hooks/useAuth"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"
import { canManage, ROLE_DESCRIPTIONS, ROLE_LABELS } from "./roles"

const ROLES: WorkspaceRole[] = ["viewer", "admin", "owner"]

const addSchema = z.object({
  email: z.email({ message: "Enter a valid email address" }),
  role: z.enum(["viewer", "admin", "owner"]),
})

type AddFormData = z.infer<typeof addSchema>

function AddMemberForm({ workspaceId }: { workspaceId: string }) {
  const { currentWorkspace } = useWorkspace()
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
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
    onError: handleError.bind(showErrorToast),
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: ["members", workspaceId] }),
  })

  // Only owners can grant the owner role
  const grantable = ROLES.filter(
    (r) => r !== "owner" || currentWorkspace?.role === "owner",
  )

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit((d) => mutation.mutate(d))}
        className="flex flex-col gap-3 sm:flex-row sm:items-end"
      >
        <FormField
          control={form.control}
          name="email"
          render={({ field }) => (
            <FormItem className="flex-1">
              <FormLabel>Email</FormLabel>
              <FormControl>
                <Input
                  type="email"
                  placeholder="teammate@example.com"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
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

function MemberRow({
  member,
  workspaceId,
  myRole,
  isMe,
  isLastOwner,
}: {
  member: WorkspaceMemberPublic
  workspaceId: string
  myRole: WorkspaceRole
  isMe: boolean
  isLastOwner: boolean
}) {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const [confirmRemove, setConfirmRemove] = useState(false)

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["members", workspaceId] })
    // My own role or membership may have changed
    if (isMe) queryClient.invalidateQueries({ queryKey: ["workspaces"] })
  }

  const roleMut = useMutation({
    mutationFn: (role: WorkspaceRole) =>
      WorkspacesService.updateMember({
        workspaceId,
        userId: member.user_id,
        requestBody: { role },
      }),
    onSuccess: () => showSuccessToast("Role updated"),
    onError: handleError.bind(showErrorToast),
    onSettled: invalidate,
  })

  const removeMut = useMutation({
    mutationFn: () =>
      WorkspacesService.removeMember({ workspaceId, userId: member.user_id }),
    onSuccess: () => {
      showSuccessToast(isMe ? "You left the workspace" : "Member removed")
      setConfirmRemove(false)
    },
    onError: handleError.bind(showErrorToast),
    onSettled: invalidate,
  })

  // Mirrors the API rules: only owners change roles; owners/admins remove
  // others (admins can't remove owners); anyone can leave; a workspace always
  // keeps at least one owner.
  const canChangeRole = myRole === "owner" && !isLastOwner
  const canRemove =
    !isLastOwner &&
    (isMe ||
      myRole === "owner" ||
      (myRole === "admin" && member.role !== "owner"))
  const name = member.user_full_name || member.user_email

  return (
    <TableRow>
      <TableCell>
        <div className="font-medium">
          {name}
          {isMe && (
            <span className="ml-2 text-xs text-muted-foreground">(you)</span>
          )}
        </div>
        {member.user_full_name && (
          <div className="text-xs text-muted-foreground">
            {member.user_email}
          </div>
        )}
      </TableCell>
      <TableCell>
        {canChangeRole ? (
          <Select
            value={member.role}
            onValueChange={(v) => roleMut.mutate(v as WorkspaceRole)}
            disabled={roleMut.isPending}
          >
            <SelectTrigger className="w-28" aria-label={`Role of ${name}`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ROLES.map((r) => (
                <SelectItem key={r} value={r}>
                  {ROLE_LABELS[r]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          <Badge variant="secondary">{ROLE_LABELS[member.role]}</Badge>
        )}
      </TableCell>
      <TableCell className="text-right">
        {canRemove && (
          <Button
            variant="ghost"
            size="icon"
            title={isMe ? "Leave workspace" : "Remove member"}
            aria-label={isMe ? "Leave workspace" : `Remove ${name}`}
            className="text-destructive hover:text-destructive"
            onClick={() => setConfirmRemove(true)}
          >
            {isMe ? (
              <LogOut className="size-4" />
            ) : (
              <Trash2 className="size-4" />
            )}
          </Button>
        )}
        <ConfirmDialog
          open={confirmRemove}
          onOpenChange={setConfirmRemove}
          title={isMe ? "Leave workspace" : "Remove member"}
          description={
            isMe
              ? "You will lose access to this workspace."
              : `${name} will lose access to this workspace.`
          }
          confirmLabel={isMe ? "Leave" : "Remove"}
          loading={removeMut.isPending}
          onConfirm={() => removeMut.mutate()}
        />
      </TableCell>
    </TableRow>
  )
}

export default function WorkspaceMembers() {
  const { currentWorkspace } = useWorkspace()
  const { user } = useAuth()

  const membersQ = useQuery({
    queryKey: ["members", currentWorkspace?.id],
    queryFn: () =>
      WorkspacesService.listMembers({ workspaceId: currentWorkspace!.id }),
    enabled: !!currentWorkspace,
  })

  if (!currentWorkspace) return null
  const members = membersQ.data?.data ?? []
  const ownerCount = members.filter((m) => m.role === "owner").length

  return (
    <div className="flex flex-col gap-6 max-w-3xl">
      {canManage(currentWorkspace) && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Add a member</CardTitle>
            <CardDescription>
              They need a Prism account first. Viewers can{" "}
              {ROLE_DESCRIPTIONS.viewer.toLowerCase()}, admins can also{" "}
              {ROLE_DESCRIPTIONS.admin.toLowerCase()}.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <AddMemberForm workspaceId={currentWorkspace.id} />
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Members{membersQ.data ? ` (${membersQ.data.count})` : ""}
          </CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          {membersQ.isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Member</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {members.map((m) => (
                  <MemberRow
                    key={m.user_id}
                    member={m}
                    workspaceId={currentWorkspace.id}
                    myRole={currentWorkspace.role}
                    isMe={m.user_id === user?.id}
                    isLastOwner={m.role === "owner" && ownerCount === 1}
                  />
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
