import { expect, test } from "@playwright/test"
import { createUser } from "./utils/privateApi"
import { randomEmail, randomPassword } from "./utils/random"
import { logInOnly } from "./utils/user"
import { createFirstWorkspace } from "./utils/workspace"

test.use({ storageState: { cookies: [], origins: [] } })

test("Posts page invites a workspace without posts to connect a platform", async ({
  page,
}) => {
  const email = randomEmail()
  const password = randomPassword()
  await createUser({ email, password })
  await logInOnly(page, email, password)
  await createFirstWorkspace(page)

  await page.getByRole("link", { name: "Posts" }).click()

  await expect(page).toHaveURL("/posts")
  await expect(page.getByRole("heading", { name: "Posts" })).toBeVisible()
  await expect(page.getByText("No posts yet.")).toBeVisible()
  await page.getByRole("link", { name: "Go to integrations" }).click()
  await expect(page).toHaveURL("/integrations")
})
