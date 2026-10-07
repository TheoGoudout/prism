import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Plus } from "lucide-react"
import { useState } from "react"
import { useForm } from "react-hook-form"

import { UsersService } from "@/client"
import { Button } from "@/components/ui/button"
import { DialogTrigger } from "@/components/ui/dialog"
import useCustomToast from "@/hooks/useCustomToast"
import {
  toUserUpdate,
  type UserFormData,
  UserFormDialog,
  userFormSchema,
} from "./UserFormDialog"

const AddUser = () => {
  const [isOpen, setIsOpen] = useState(false)
  const queryClient = useQueryClient()
  const { showSuccessToast, showApiError } = useCustomToast()

  const form = useForm<UserFormData>({
    resolver: zodResolver(userFormSchema(true)),
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      email: "",
      full_name: "",
      password: "",
      confirm_password: "",
      is_superuser: false,
      is_active: false,
    },
  })

  const mutation = useMutation({
    mutationFn: (data: UserFormData) =>
      UsersService.createUser({
        requestBody: { ...toUserUpdate(data), password: data.password },
      }),
    onSuccess: () => {
      showSuccessToast("User created successfully")
      form.reset()
      setIsOpen(false)
    },
    onError: showApiError,
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  })

  return (
    <UserFormDialog
      open={isOpen}
      onOpenChange={setIsOpen}
      trigger={
        <DialogTrigger asChild>
          <Button>
            <Plus />
            Add User
          </Button>
        </DialogTrigger>
      }
      title="Add User"
      description="Fill in the form below to add a new user to the system."
      form={form}
      onSubmit={(data) => mutation.mutate(data)}
      loading={mutation.isPending}
      creating
    />
  )
}

export default AddUser
