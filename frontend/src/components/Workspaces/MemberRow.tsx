import { useMutation, useQueryClient } from "@tanstack/react-query"
import { LogOut, Trash2 } from "lucide-react"
import { useState } from "react"

import type { WorkspaceMemberPublic, WorkspaceRole } from "@/client"
import { WorkspacesService } from "@/client"
import ConfirmDialog from "@/components/Common/ConfirmDialog"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { TableCell, TableRow } from "@/components/ui/table"
import { useCurrentWorkspace } from "@/contexts/WorkspaceContext"
import useCustomToast from "@/hooks/useCustomToast"
import { ROLE_LABELS, ROLES } from "./roles"

interface MemberRowProps {
  member: WorkspaceMemberPublic
  /** Whether this row is the current user. */
  isMe: boolean
  /** Whether this member is the workspace's only owner. */
  isLastOwner: boolean
}

export function MemberRow({ member, isMe, isLastOwner }: MemberRowProps) {
  const { id: workspaceId, role: myRole } = useCurrentWorkspace()
  const queryClient = useQueryClient()
  const { showSuccessToast, showApiError } = useCustomToast()
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
    onError: showApiError,
    onSettled: invalidate,
  })

  const removeMut = useMutation({
    mutationFn: () =>
      WorkspacesService.removeMember({ workspaceId, userId: member.user_id }),
    onSuccess: () => {
      showSuccessToast(isMe ? "You left the workspace" : "Member removed")
      setConfirmRemove(false)
    },
    onError: showApiError,
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
