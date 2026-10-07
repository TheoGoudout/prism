/** The API access token, kept in localStorage between visits. */
const ACCESS_TOKEN = "access_token"

export const getAccessToken = () => localStorage.getItem(ACCESS_TOKEN)

export const setAccessToken = (token: string) =>
  localStorage.setItem(ACCESS_TOKEN, token)

export const clearAccessToken = () => localStorage.removeItem(ACCESS_TOKEN)

export const isLoggedIn = () => getAccessToken() !== null
