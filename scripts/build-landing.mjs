#!/usr/bin/env node
/**
 * Build the static landing page into `landing/dist/`, ready for deployment to
 * Cloudflare Workers static assets.
 *
 * `landing/index.html` is kept as a template containing `${FRONTEND_URL}` so
 * the Docker image (landing/Dockerfile + landing/docker-entrypoint.sh) can keep
 * substituting it with envsubst at container startup for local development.
 * Workers has no container start hook, so here the same substitution happens at
 * build time, reading FRONTEND_URL from `landing/.env.<mode>`.
 *
 * Usage: bun scripts/build-landing.mjs <dev|staging|production>
 */

import { copyFile, cp, mkdir, readFile, rm, writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const MODES = ["dev", "staging", "production"]

const rootDir = join(dirname(fileURLToPath(import.meta.url)), "..")
const landingDir = join(rootDir, "landing")
const distDir = join(landingDir, "dist")

const fail = (message) => {
  console.error(`build-landing: ${message}`)
  process.exit(1)
}

/** Minimal KEY=VALUE parser — the landing env files hold public URLs only. */
const parseEnvFile = (contents) => {
  const env = {}
  for (const line of contents.split("\n")) {
    const trimmed = line.trim()
    if (trimmed === "" || trimmed.startsWith("#")) continue
    const separator = trimmed.indexOf("=")
    if (separator === -1) continue
    const key = trimmed.slice(0, separator).trim()
    const value = trimmed.slice(separator + 1).trim()
    env[key] = value.replace(/^(["'])(.*)\1$/, "$2")
  }
  return env
}

const mode = process.argv[2]
if (!MODES.includes(mode)) {
  fail(`expected mode to be one of ${MODES.join(", ")}, got "${mode ?? ""}"`)
}

const envPath = join(landingDir, `.env.${mode}`)
let fileEnv = {}
try {
  fileEnv = parseEnvFile(await readFile(envPath, "utf8"))
} catch (error) {
  if (error.code !== "ENOENT") throw error
}

// An inline FRONTEND_URL wins, so CI can point a build at an ad-hoc frontend.
const frontendUrl = process.env.FRONTEND_URL || fileEnv.FRONTEND_URL
if (!frontendUrl) {
  fail(`FRONTEND_URL is not set — add it to ${envPath} or the environment`)
}

const template = await readFile(join(landingDir, "index.html"), "utf8")
const html = template.replaceAll("${FRONTEND_URL}", frontendUrl)

if (html.includes("${")) {
  fail("index.html still contains an unsubstituted ${...} placeholder")
}

await rm(distDir, { recursive: true, force: true })
await mkdir(distDir, { recursive: true })
await writeFile(join(distDir, "index.html"), html)
await copyFile(join(landingDir, "privacy.html"), join(distDir, "privacy.html"))
// Self-hosted fonts: no request leaves the site for a typeface.
await cp(join(landingDir, "fonts"), join(distDir, "fonts"), { recursive: true })
await cp(join(landingDir, "assets"), join(distDir, "assets"), { recursive: true })

console.log(`build-landing: built ${mode} with FRONTEND_URL=${frontendUrl}`)
