import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"

import {
  type Body_login_login_access_token as AccessToken,
  LoginService,
  type UserPublic,
  type UserRegister,
  UsersService,
} from "@/client"
import { clearAccessToken, isLoggedIn, setAccessToken } from "@/lib/auth"
import useCustomToast from "./useCustomToast"

const useAuth = () => {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showApiError } = useCustomToast()

  const { data: user } = useQuery<UserPublic | null, Error>({
    queryKey: ["currentUser"],
    queryFn: UsersService.readUserMe,
    enabled: isLoggedIn(),
  })

  const signUpMutation = useMutation({
    mutationFn: (data: UserRegister) =>
      UsersService.registerUser({ requestBody: data }),
    onSuccess: () => {
      navigate({ to: "/login" })
    },
    onError: showApiError,
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] })
    },
  })

  const loginMutation = useMutation({
    mutationFn: async (data: AccessToken) => {
      const response = await LoginService.loginAccessToken({ formData: data })
      setAccessToken(response.access_token)
    },
    onSuccess: () => {
      navigate({ to: "/" })
    },
    onError: showApiError,
  })

  const logout = () => {
    clearAccessToken()
    navigate({ to: "/login" })
  }

  return {
    signUpMutation,
    loginMutation,
    logout,
    user,
  }
}

export default useAuth
