import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Trash2 } from "lucide-react"
import { useState } from "react"

import { UsersService } from "@/client"
import ConfirmDialog from "@/components/Common/ConfirmDialog"
import { DropdownMenuItem } from "@/components/ui/dropdown-menu"
import useCustomToast from "@/hooks/useCustomToast"

interface DeleteUserProps {
  id: string
  onSuccess: () => void
}

const DeleteUser = ({ id, onSuccess }: DeleteUserProps) => {
  const [confirming, setConfirming] = useState(false)
  const queryClient = useQueryClient()
  const { showSuccessToast, showApiError } = useCustomToast()

  const mutation = useMutation({
    mutationFn: () => UsersService.deleteUser({ userId: id }),
    onSuccess: () => {
      showSuccessToast("The user was deleted successfully")
      setConfirming(false)
      onSuccess()
    },
    onError: showApiError,
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  })

  return (
    <>
      <DropdownMenuItem
        variant="destructive"
        // Keep the menu (and with it this component) mounted while confirming
        onSelect={(e) => e.preventDefault()}
        onClick={() => setConfirming(true)}
      >
        <Trash2 />
        Delete User
      </DropdownMenuItem>
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title="Delete User"
        description={
          <>
            The user will be <strong>permanently deleted.</strong> Are you sure?
            You will not be able to undo this action.
          </>
        }
        confirmLabel="Delete"
        loading={mutation.isPending}
        onConfirm={() => mutation.mutate()}
      />
    </>
  )
}

export default DeleteUser
