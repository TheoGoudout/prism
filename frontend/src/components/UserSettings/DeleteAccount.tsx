import { useMutation } from "@tanstack/react-query"
import { useState } from "react"

import { UsersService } from "@/client"
import ConfirmDialog from "@/components/Common/ConfirmDialog"
import { Button } from "@/components/ui/button"
import useAuth from "@/hooks/useAuth"
import useCustomToast from "@/hooks/useCustomToast"

const DeleteAccount = () => {
  const [confirming, setConfirming] = useState(false)
  const { showSuccessToast, showApiError } = useCustomToast()
  const { logout } = useAuth()

  const mutation = useMutation({
    mutationFn: () => UsersService.deleteUserMe(),
    onSuccess: () => {
      showSuccessToast("Your account has been successfully deleted")
      logout()
    },
    onError: showApiError,
  })

  return (
    <div className="mt-4 max-w-md rounded-lg border border-destructive/50 p-4">
      <h3 className="font-semibold text-destructive">Delete Account</h3>
      <p className="mt-1 text-sm text-muted-foreground">
        Permanently delete your account and all associated data.
      </p>
      <Button
        variant="destructive"
        className="mt-3"
        onClick={() => setConfirming(true)}
      >
        Delete Account
      </Button>
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title="Confirmation Required"
        description={
          <>
            All your account data will be <strong>permanently deleted.</strong>{" "}
            This action cannot be undone.
          </>
        }
        confirmLabel="Delete"
        loading={mutation.isPending}
        onConfirm={() => mutation.mutate()}
      />
    </div>
  )
}

export default DeleteAccount
