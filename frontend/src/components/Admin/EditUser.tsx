import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Pencil } from "lucide-react"
import { useState } from "react"
import { useForm } from "react-hook-form"

import { type UserPublic, UsersService } from "@/client"
import { DropdownMenuItem } from "@/components/ui/dropdown-menu"
import useCustomToast from "@/hooks/useCustomToast"
import {
  toUserUpdate,
  type UserFormData,
  UserFormDialog,
  userFormSchema,
} from "./UserFormDialog"

interface EditUserProps {
  user: UserPublic
  onSuccess: () => void
}

const EditUser = ({ user, onSuccess }: EditUserProps) => {
  const [isOpen, setIsOpen] = useState(false)
  const queryClient = useQueryClient()
  const { showSuccessToast, showApiError } = useCustomToast()

  const form = useForm<UserFormData>({
    resolver: zodResolver(userFormSchema(false)),
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      email: user.email,
      full_name: user.full_name ?? undefined,
      password: "",
      confirm_password: "",
      is_superuser: user.is_superuser ?? false,
      is_active: user.is_active ?? true,
    },
  })

  const mutation = useMutation({
    mutationFn: (data: UserFormData) =>
      UsersService.updateUser({
        userId: user.id,
        requestBody: toUserUpdate(data),
      }),
    onSuccess: () => {
      showSuccessToast("User updated successfully")
      setIsOpen(false)
      onSuccess()
    },
    onError: showApiError,
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  })

  return (
    <UserFormDialog
      open={isOpen}
      onOpenChange={setIsOpen}
      trigger={
        <DropdownMenuItem
          // Keep the menu (and with it this dialog) mounted while editing
          onSelect={(e) => e.preventDefault()}
          onClick={() => setIsOpen(true)}
        >
          <Pencil />
          Edit User
        </DropdownMenuItem>
      }
      title="Edit User"
      description="Update the user details below."
      form={form}
      onSubmit={(data) => mutation.mutate(data)}
      loading={mutation.isPending}
      creating={false}
    />
  )
}

export default EditUser
