/**
 * Captures the platforms' own screens (Facebook, Google, X, …) for the
 * "How to connect your accounts" guides, by going through each real
 * connection on a running Prism, then disconnecting again.
 *
 * Platforms block scripted password logins, so the browser reuses sessions
 * you log in to by hand once:
 *
 *   1. bun run tutorial-screenshots:login
 *      A browser opens with one tab per site (Prism and each platform).
 *      Log in to each with the test accounts, then close the browser.
 *      The sessions stay in .tutorial-browser-profile/ (git-ignored; it
 *      holds login cookies, never commit or share it).
 *
 *   2. bun run tutorial-screenshots:platforms [platform …]
 *      Connects each platform (all by default), saves a screenshot of each
 *      platform screen to public/assets/images/tutorials/ and disconnects.
 *      Disconnecting revokes Prism's access on the platform, so the next
 *      run sees the same first-time screens. LinkedIn has no revocation
 *      API: remove Prism from your LinkedIn settings between runs.
 *
 * Environment:
 *   PRISM_URL    Prism's frontend, e.g. https://prism.example.com (required)
 *   MASK_TEXT    Comma-separated texts to black out in the screenshots,
 *                e.g. the test accounts' email addresses
 *   BROWSER      "chrome" (default: your installed Google Chrome, which
 *                Google sign-in accepts) or "chromium" (Playwright's own)
 *
 * Use dedicated test accounts with brand-like names (e.g. "Acme Coffee"):
 * their names and pictures appear in the screenshots.
 *
 * Platforms change their screens often. When a screen isn't recognised,
 * the script saves it to public/assets/images/tutorials/_debug/ and moves
 * on to the next platform: adjust SCREENS below to match it.
 */
import { mkdirSync } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { type BrowserContext, chromium, type Page } from "@playwright/test"

import type { Platform } from "../src/client"
import { PLATFORM_LABELS, PLATFORMS } from "../src/lib/platforms"

const here = path.dirname(fileURLToPath(import.meta.url))
const PROFILE_DIR = path.join(here, "../.tutorial-browser-profile")
const OUT_DIR = path.join(here, "../public/assets/images/tutorials")
const DEBUG_DIR = path.join(OUT_DIR, "_debug")

const LOGIN_PAGES = [
  "https://www.facebook.com/",
  "https://www.instagram.com/accounts/login/",
  "https://x.com/login",
  "https://www.linkedin.com/login",
  "https://www.tiktok.com/login",
  "https://accounts.google.com/",
]

/**
 * A platform screen: recognised by `match` (text on the page), saved as
 * `file` (null: not shown in the guides) and left with `next`.
 */
interface Screen {
  name: string
  match: RegExp
  file: string | null
  next: (page: Page) => Promise<void>
}

/** Click the first visible element with one of these roles and names. */
async function click(page: Page, name: RegExp, roles = ["button", "link"]) {
  for (const role of roles) {
    const target = page
      .getByRole(role as "button" | "link", { name })
      .filter({ visible: true })
      .first()
    if ((await target.count()) > 0) {
      await target.click()
      return
    }
  }
  throw new Error(`Nothing to click matching ${name}`)
}

/** Tick a checkbox or radio by its label, if the screen has one. */
async function checkIfPresent(page: Page, label: RegExp) {
  const box = page.getByLabel(label).filter({ visible: true }).first()
  if ((await box.count()) > 0 && !(await box.isChecked())) await box.check()
}

const FACEBOOK_SCREENS: Screen[] = [
  {
    name: "continue",
    match: /Continue as /i,
    file: "facebook-continue.png",
    next: (page) => click(page, /^Continue as /i),
  },
  {
    name: "businesses",
    match: /Choose the businesses|Select (the )?businesses/i,
    file: null,
    next: async (page) => {
      await checkIfPresent(page, /all current and future/i)
      await click(page, /^Continue$/i)
    },
  },
  {
    name: "pages",
    match: /Choose the Pages|Select (the )?Pages/i,
    file: "facebook-pages.png",
    next: async (page) => {
      await checkIfPresent(page, /all current and future Pages/i)
      await click(page, /^Continue$/i)
    },
  },
  {
    name: "permissions",
    match: /Review what .+ is requesting|is requesting access to/i,
    file: "facebook-permissions.png",
    next: (page) => click(page, /^Save$/i),
  },
  {
    name: "linked",
    match: /has been (linked|connected) to|You've now linked/i,
    file: null,
    next: (page) => click(page, /^(Got it|OK)$/i),
  },
]

const SCREENS: Record<Platform, Screen[]> = {
  facebook: FACEBOOK_SCREENS,
  instagram: [
    {
      name: "allow",
      match: /Allow .+ to access|wants to access|would like to access/i,
      file: "instagram-allow.png",
      next: (page) => click(page, /^Allow$/i),
    },
  ],
  twitter: [
    {
      name: "authorize",
      match: /Authorize app|wants to access your X account/i,
      file: "twitter-authorize.png",
      next: async (page) => {
        // Shown for apps requesting sensitive permissions
        await checkIfPresent(page, /I trust this app/i)
        await click(page, /^Authorize app$/i)
      },
    },
  ],
  linkedin: [
    {
      name: "allow",
      match: /would like to|wants to access/i,
      file: "linkedin-allow.png",
      next: (page) => click(page, /^Allow$/i),
    },
  ],
  tiktok: [
    {
      name: "authorize",
      match: /would like to|wants to access|is requesting/i,
      file: "tiktok-authorize.png",
      next: (page) => click(page, /^(Continue|Authorize|Allow)$/i),
    },
  ],
  google_analytics: [
    {
      name: "unverified",
      match: /hasn.t verified this app/i,
      file: null,
      next: async () => {
        throw new Error(
          "Google shows its unverified app warning: get the OAuth app verified first",
        )
      },
    },
    {
      name: "account",
      match: /Choose an account/i,
      file: "google_analytics-account.png",
      next: (page) => click(page, /@/, ["link", "button"]),
    },
    {
      name: "consent",
      match:
        /wants (additional )?access to your Google Account|wants to access your Google Account/i,
      file: "google_analytics-consent.png",
      next: async (page) => {
        await checkIfPresent(page, /Select all/i)
        await checkIfPresent(page, /Google Analytics/i)
        await click(page, /^(Continue|Allow)$/i)
      },
    },
  ],
}

async function launch(headless: boolean): Promise<BrowserContext> {
  const options = {
    headless,
    viewport: { width: 1280, height: 800 },
    deviceScaleFactor: 2,
    locale: "en-US",
    colorScheme: "light" as const,
  }
  const channel = process.env.BROWSER === "chromium" ? undefined : "chrome"
  try {
    return await chromium.launchPersistentContext(PROFILE_DIR, {
      ...options,
      channel,
    })
  } catch (err) {
    if (!channel) throw err
    console.warn("Google Chrome not found, using Playwright's Chromium")
    return chromium.launchPersistentContext(PROFILE_DIR, options)
  }
}

function prismUrl(): string {
  const url = process.env.PRISM_URL?.replace(/\/$/, "")
  if (!url) throw new Error("Set PRISM_URL to the Prism frontend's address")
  return url
}

async function login() {
  const context = await launch(false)
  const pages = [`${prismUrl()}/login`, ...LOGIN_PAGES]
  for (const [i, url] of pages.entries()) {
    const page = context.pages()[i] ?? (await context.newPage())
    await page.goto(url)
  }
  console.log("Log in on every tab, then close the browser window.")
  await new Promise<void>((resolve) => context.on("close", () => resolve()))
}

async function screenshot(page: Page, file: string) {
  const masked = (process.env.MASK_TEXT ?? "")
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean)
    .map((text) => page.getByText(text))
  await page.screenshot({ path: path.join(OUT_DIR, file), mask: masked })
}

/** The screen currently shown, waiting for the page to settle. */
async function currentScreen(page: Page, screens: Screen[]) {
  for (let attempt = 0; attempt < 20; attempt++) {
    for (const screen of screens) {
      const text = page.getByText(screen.match).filter({ visible: true })
      if ((await text.count()) > 0) return screen
    }
    await page.waitForTimeout(500)
  }
  return null
}

async function capture(page: Page, platform: Platform) {
  const label = PLATFORM_LABELS[platform]
  const prism = prismUrl()
  const backInPrism = (url: URL) => url.href.startsWith(prism)

  await page.goto(`${prism}/integrations`)
  await page.getByRole("button", { name: "Connect platform" }).click()
  await page.getByRole("menuitem", { name: label }).click()
  await page.waitForURL((url) => !backInPrism(url))
  await page.waitForLoadState("domcontentloaded")

  const seen = new Set<string>()
  while (!backInPrism(new URL(page.url()))) {
    const screen = await currentScreen(page, SCREENS[platform])
    if (!screen) {
      if (backInPrism(new URL(page.url()))) break
      const file = `${platform}-unknown-${seen.size + 1}.png`
      await page.screenshot({ path: path.join(DEBUG_DIR, file) })
      throw new Error(`Unrecognised screen, saved to _debug/${file}`)
    }
    if (seen.has(screen.name)) {
      throw new Error(`Stuck on the "${screen.name}" screen`)
    }
    seen.add(screen.name)
    if (screen.file) {
      await page.waitForLoadState("networkidle").catch(() => {})
      await screenshot(page, screen.file)
      console.log(`  saved ${screen.file}`)
    }
    await screen.next(page)
    await page.waitForLoadState("domcontentloaded")
  }

  if (seen.size === 0) {
    console.warn(
      `  ${label} skipped its screens: Prism is probably still authorised there. Remove it from the platform's connected apps and run again.`,
    )
  }

  // Back in Prism: disconnect, which also revokes access on the platform
  await page.waitForURL(/\/integrations/)
  await page
    .getByRole("button", { name: `Disconnect ${label}` })
    .first()
    .click()
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Disconnect" })
    .click()
  await page.getByRole("dialog").waitFor({ state: "hidden" })
}

async function main() {
  const args = process.argv.slice(2)
  if (args[0] === "--login") return login()

  const unknown = args.filter((a) => !PLATFORMS.includes(a as Platform))
  if (unknown.length) throw new Error(`Unknown platform(s): ${unknown}`)
  const platforms = args.length ? (args as Platform[]) : PLATFORMS

  mkdirSync(DEBUG_DIR, { recursive: true })
  const context = await launch(process.env.HEADLESS === "1")
  const page = context.pages()[0] ?? (await context.newPage())
  const failed: Platform[] = []
  try {
    for (const platform of platforms) {
      console.log(PLATFORM_LABELS[platform])
      try {
        await capture(page, platform)
      } catch (err) {
        failed.push(platform)
        console.error(`  failed: ${err instanceof Error ? err.message : err}`)
      }
    }
  } finally {
    await context.close()
  }
  if (failed.length) {
    console.error(`\nFailed: ${failed.join(", ")}`)
    process.exitCode = 1
  }
}

await main()
