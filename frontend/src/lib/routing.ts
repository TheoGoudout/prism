import { redirect } from "@tanstack/react-router"

import { isLoggedIn } from "@/lib/auth"

/** A route's `head`: the page title, e.g. "Posts - Prism". */
export const pageHead = (title: string) => () => ({
  meta: [{ title: `${title} - Prism` }],
})

/** `beforeLoad` of the pages only logged-out visitors need (login, sign up…). */
export function redirectIfLoggedIn() {
  if (isLoggedIn()) {
    throw redirect({ to: "/" })
  }
}
