import { expect, type Page, test } from "@playwright/test"
import { createUser } from "./utils/privateApi"
import { randomEmail, randomPassword } from "./utils/random"
import { logInOnly, logInUser, logOutUser } from "./utils/user"
import {
  createFirstWorkspace,
  expectDashboard,
  randomWorkspaceName,
} from "./utils/workspace"

test.use({ storageState: { cookies: [], origins: [] } })

async function newUser() {
  const email = randomEmail()
  const password = randomPassword()
  await createUser({ email, password })
  return { email, password }
}

function memberRow(page: Page, email: string) {
  return page.getByRole("row").filter({ hasText: email })
}

async function addMember(page: Page, email: string, role = "Viewer") {
  await page.goto("/settings?tab=members")
  await page.getByLabel("Email").fill(email)
  if (role !== "Viewer") {
    await page.getByRole("combobox").first().click()
    await page.getByRole("option", { name: role }).click()
  }
  await page.getByRole("button", { name: "Add member" }).click()
  await expect(page.getByText(`${email} added to the workspace`)).toBeVisible()
}

test.describe("Onboarding", () => {
  test("New user creates their first workspace", async ({ page }) => {
    const { email, password } = await newUser()
    await logInOnly(page, email, password)

    await expect(
      page.getByRole("heading", { name: "Create your first workspace" }),
    ).toBeVisible()
    const name = await createFirstWorkspace(page, randomWorkspaceName())

    await expectDashboard(page)
    await expect(page.getByRole("heading", { name })).toBeVisible()
  })

  test("User without a workspace can log out", async ({ page }) => {
    const { email, password } = await newUser()
    await logInOnly(page, email, password)

    await page.getByRole("button", { name: "Log out" }).click()
    await expect(page).toHaveURL("/login")
  })
})

test.describe("Workspace settings", () => {
  test("Owner can rename the workspace", async ({ page }) => {
    const { email, password } = await newUser()
    await logInUser(page, email, password)

    const newName = randomWorkspaceName()
    await page.goto("/settings?tab=workspace")
    await page.getByLabel("Name").fill(newName)
    await page.getByRole("button", { name: "Save" }).click()

    await expect(page.getByText("Workspace updated")).toBeVisible()
    await page.goto("/")
    await expect(page.getByRole("heading", { name: newName })).toBeVisible()
  })

  test("Owner can delete the workspace", async ({ page }) => {
    const { email, password } = await newUser()
    await logInUser(page, email, password)

    await page.goto("/settings?tab=workspace")
    await page.getByRole("button", { name: "Delete workspace" }).click()
    await page.getByRole("button", { name: "Delete", exact: true }).click()

    await expect(
      page.getByRole("heading", { name: "Create your first workspace" }),
    ).toBeVisible()
  })
})

test.describe("Members", () => {
  test("Owner adds a member by email, changes their role and removes them", async ({
    page,
  }) => {
    const owner = await newUser()
    const member = await newUser()
    await logInUser(page, owner.email, owner.password)

    await addMember(page, member.email)
    const row = memberRow(page, member.email)
    await expect(row.getByText("Viewer")).toBeVisible()

    await row.getByRole("combobox").click()
    await page.getByRole("option", { name: "Admin" }).click()
    await expect(page.getByText("Role updated")).toBeVisible()
    await expect(row.getByRole("combobox")).toHaveText("Admin")

    await row.getByRole("button", { name: /Remove/ }).click()
    await page.getByRole("button", { name: "Remove", exact: true }).click()
    await expect(page.getByText("Member removed")).toBeVisible()
    await expect(memberRow(page, member.email)).toHaveCount(0)
  })

  test("Adding an unknown email shows an error", async ({ page }) => {
    const owner = await newUser()
    await logInUser(page, owner.email, owner.password)

    await page.goto("/settings?tab=members")
    await page.getByLabel("Email").fill(randomEmail())
    await page.getByRole("button", { name: "Add member" }).click()

    await expect(
      page.getByText("No user with this email. Ask them to sign up first."),
    ).toBeVisible()
  })

  test("Viewers can't manage members or integrations", async ({ page }) => {
    const owner = await newUser()
    const viewer = await newUser()
    await logInUser(page, owner.email, owner.password)
    await addMember(page, viewer.email)
    await logOutUser(page)

    // The viewer now belongs to the owner's workspace: no onboarding
    await logInUser(page, viewer.email, viewer.password)

    await page.goto("/integrations")
    await expect(
      page.getByRole("heading", { name: "Integrations" }),
    ).toBeVisible()
    await expect(
      page.getByRole("button", { name: "Connect platform" }),
    ).toHaveCount(0)

    await page.goto("/settings?tab=members")
    await expect(memberRow(page, owner.email)).toBeVisible()
    await expect(page.getByRole("button", { name: "Add member" })).toHaveCount(
      0,
    )

    await page.goto("/settings?tab=workspace")
    await expect(page.getByLabel("Name")).toBeDisabled()
  })
})

test.describe("Integrations", () => {
  test("OAuth errors are shown as friendly messages", async ({ page }) => {
    const { email, password } = await newUser()
    await logInUser(page, email, password)

    await page.goto("/integrations?error=invalid_state")
    await expect(
      page.getByText(
        "The connection link expired or is invalid. Please try connecting again.",
      ),
    ).toBeVisible()
    // The error is cleared from the URL so a refresh doesn't repeat it
    await expect(page).toHaveURL("/integrations")
  })

  test("Owners see the connect menu with every platform", async ({ page }) => {
    const { email, password } = await newUser()
    await logInUser(page, email, password)

    await page.goto("/integrations")
    await page.getByRole("button", { name: "Connect platform" }).click()
    for (const label of [
      "Facebook",
      "Instagram",
      "Twitter / X",
      "LinkedIn",
      "TikTok",
      "Google Analytics",
    ]) {
      await expect(page.getByRole("menuitem", { name: label })).toBeVisible()
    }
  })
})
