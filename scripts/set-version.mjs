#!/usr/bin/env bun
/**
 * Single source of truth for where the release version lives.
 *
 * Every file listed in TARGETS below carries the version in some form. Keeping
 * that list here — rather than as a pile of inline sed/jq steps in a workflow —
 * is what makes drift detectable: `--check` reads all of them back and fails if
 * they disagree. backend/pyproject.toml is canonical: the API reports it as its
 * OpenAPI version, which is what deploy-coolify.yml checks after a deploy.
 *
 *   bun scripts/set-version.mjs 1.5.0        write the version everywhere
 *   bun scripts/set-version.mjs 1.5.0-rc1    pre-release
 *   bun scripts/set-version.mjs --check      verify every file already agrees
 *   bun scripts/set-version.mjs --print      print the current version
 *   bun scripts/set-version.mjs --next <patch|minor|major|rc|explicit> [version]
 *   bun scripts/set-version.mjs --validate <version>
 *   bun scripts/set-version.mjs --is-newer <version>
 *
 * Ported from shop-n-cook's scripts/set-version.mjs, without its Android
 * versionCode and extension manifest targets.
 */

import { execFileSync } from "node:child_process"
import { readFileSync, writeFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..")

const SEMVER = /^(\d+)\.(\d+)\.(\d+)(?:-rc(\d+))?$/

/** Parse `1.5.0` / `1.5.0-rc1`, or throw. */
export function parseVersion(version) {
  const m = SEMVER.exec(version)
  if (!m) {
    throw new Error(
      `invalid version ${JSON.stringify(version)} — expected X.Y.Z or X.Y.Z-rcN`,
    )
  }
  const [, major, minor, patch, rc] = m
  return {
    version,
    major: Number(major),
    minor: Number(minor),
    patch: Number(patch),
    rc: rc === undefined ? null : Number(rc),
    isPrerelease: rc !== undefined,
  }
}

/** The version a bump leads to, from the current one. */
export function nextVersion(current, bump, explicit = "") {
  if (bump === "explicit") {
    if (!explicit) throw new Error("bump = explicit requires the version input")
    // Validated, not just stripped: an unparseable input would otherwise reach
    // the tag and the version files unchallenged.
    return parseVersion(explicit.replace(/^v/, "")).version
  }

  const { major, minor, patch, rc } = parseVersion(current)
  switch (bump) {
    case "major":
      return `${major + 1}.0.0`
    case "minor":
      return `${major}.${minor + 1}.0`
    // Bumping patch off a release candidate promotes it: 1.5.0-rc2 -> 1.5.0
    case "patch":
      return rc === null ? `${major}.${minor}.${patch + 1}` : `${major}.${minor}.${patch}`
    case "rc":
      return rc === null
        ? `${major}.${minor}.${patch + 1}-rc1`
        : `${major}.${minor}.${patch}-rc${rc + 1}`
    default:
      throw new Error(`unknown bump ${bump}`)
  }
}

/**
 * Order two versions. Negative when `a` precedes `b`.
 *
 * Not `sort -V`, which ranks `1.5.0-rc2` *above* `1.5.0` and would therefore
 * reject every promotion of a release candidate: a stable release sorts after
 * all of its own candidates.
 */
export function compareVersions(a, b) {
  const x = parseVersion(a)
  const y = parseVersion(b)
  const key = (v) => [v.major, v.minor, v.patch, v.rc ?? Number.POSITIVE_INFINITY]
  const [kx, ky] = [key(x), key(y)]
  for (let i = 0; i < kx.length; i++) {
    if (kx[i] !== ky[i]) return kx[i] < ky[i] ? -1 : 1
  }
  return 0
}

/** Highest existing `vX.Y.Z[-rcN]` tag, ignoring anything that doesn't parse. */
function highestTag() {
  let tags
  try {
    tags = execFileSync("git", ["tag", "--list"], { cwd: ROOT, encoding: "utf8" })
  } catch {
    return null
  }
  let best = null
  for (const line of tags.split("\n")) {
    const name = line.trim()
    if (!name.startsWith("v")) continue
    let parsed
    try {
      parsed = parseVersion(name.slice(1))
    } catch {
      continue
    }
    if (best === null || compareVersions(parsed.version, best) > 0) {
      best = parsed.version
    }
  }
  return best
}

// --- file handlers -------------------------------------------------------

/** Read/modify a JSON file while preserving Biome's 2-space + trailing-newline style. */
function editJson(relPath, mutate) {
  const path = join(ROOT, relPath)
  const json = JSON.parse(readFileSync(path, "utf8"))
  mutate(json)
  writeFileSync(path, `${JSON.stringify(json, null, 2)}\n`)
}

function readJson(relPath) {
  return JSON.parse(readFileSync(join(ROOT, relPath), "utf8"))
}

/** Replace text in a file via regex, asserting the pattern actually matched. */
function editText(relPath, pattern, replacement) {
  const path = join(ROOT, relPath)
  const before = readFileSync(path, "utf8")
  const after = before.replace(pattern, replacement)
  if (after === before && !pattern.test(before)) {
    throw new Error(`${relPath}: pattern ${pattern} did not match anything`)
  }
  writeFileSync(path, after)
}

function matchText(relPath, pattern, group = 1) {
  const text = readFileSync(join(ROOT, relPath), "utf8")
  const m = pattern.exec(text)
  if (!m) throw new Error(`${relPath}: could not find a version (${pattern})`)
  return m[group]
}

const PYPROJECT_VERSION = /^version = "(.+)"$/m
/**
 * The `app` entry in uv.lock mirrors backend/pyproject.toml's version. `uv`
 * rewrites it on the next lock refresh, and the uv-lock pre-commit hook fails
 * until it does, so the bump writes it too.
 */
const UVLOCK_APP_VERSION = /(\[\[package\]\]\nname = "app"\nversion = )"([^"]*)"/
/** bun.lock records each workspace's version; `bun ci` refuses a stale one. */
const BUNLOCK_FRONTEND_VERSION = /("frontend": \{\n\s*"name": "frontend",\n\s*"version": )"([^"]*)"/
/**
 * The generated client carries the API's OpenAPI version. It is regenerated
 * from the backend, so this is the value regeneration would write: setting it
 * here keeps the bump commit from being followed by a client-regen diff.
 */
const CLIENT_VERSION = /(VERSION: )'([^']*)'/

const TARGETS = [
  {
    path: "backend/pyproject.toml",
    read: () => matchText("backend/pyproject.toml", PYPROJECT_VERSION),
    write: (v) =>
      editText("backend/pyproject.toml", PYPROJECT_VERSION, `version = "${v}"`),
  },
  {
    path: "uv.lock",
    read: () => matchText("uv.lock", UVLOCK_APP_VERSION, 2),
    write: (v) => editText("uv.lock", UVLOCK_APP_VERSION, `$1"${v}"`),
  },
  {
    path: "frontend/package.json",
    read: () => readJson("frontend/package.json").version,
    write: (v) =>
      editJson("frontend/package.json", (j) => {
        j.version = v
      }),
  },
  {
    path: "bun.lock",
    read: () => matchText("bun.lock", BUNLOCK_FRONTEND_VERSION, 2),
    write: (v) => editText("bun.lock", BUNLOCK_FRONTEND_VERSION, `$1"${v}"`),
  },
  {
    path: "frontend/src/client/core/OpenAPI.ts",
    read: () => matchText("frontend/src/client/core/OpenAPI.ts", CLIENT_VERSION, 2),
    write: (v) =>
      editText("frontend/src/client/core/OpenAPI.ts", CLIENT_VERSION, `$1'${v}'`),
  },
]

/** The version the repo currently claims, read from the backend as canonical. */
export function currentVersion() {
  return matchText("backend/pyproject.toml", PYPROJECT_VERSION)
}

function check() {
  const canonical = currentVersion()
  parseVersion(canonical)
  const mismatches = []

  for (const target of TARGETS) {
    let actual
    try {
      actual = target.read()
    } catch (err) {
      mismatches.push(`${target.path}: ${err.message}`)
      continue
    }
    if (actual !== canonical) {
      mismatches.push(`${target.path}: expected ${canonical}, found ${actual ?? "(no version)"}`)
    }
  }

  if (mismatches.length > 0) {
    console.error(`Version drift (canonical is ${canonical}):`)
    for (const line of mismatches) console.error(`  - ${line}`)
    process.exit(1)
  }
  console.log(`All version files agree on ${canonical}.`)
}

function main() {
  const arg = process.argv[2]

  if (!arg) {
    console.error(
      "usage: set-version.mjs <version> | --check | --print" +
        " | --is-newer <version> | --validate <version>" +
        " | --next <patch|minor|major|rc|explicit> [version]",
    )
    process.exit(2)
  }
  if (arg === "--print") {
    console.log(currentVersion())
    return
  }
  if (arg === "--check") {
    check()
    return
  }
  if (arg === "--validate") {
    console.log(parseVersion(process.argv[3] ?? "").version)
    return
  }
  if (arg === "--next") {
    console.log(nextVersion(currentVersion(), process.argv[3] ?? "", process.argv[4] ?? ""))
    return
  }
  if (arg === "--is-newer") {
    const candidate = parseVersion(process.argv[3] ?? "").version
    const highest = highestTag()
    if (highest === null) {
      console.log(`No existing tags; ${candidate} is acceptable.`)
      return
    }
    if (compareVersions(candidate, highest) <= 0) {
      console.error(`${candidate} does not sort above the highest existing tag v${highest}.`)
      process.exit(1)
    }
    console.log(`${candidate} sorts above the highest existing tag v${highest}.`)
    return
  }

  const { version } = parseVersion(arg)
  for (const target of TARGETS) {
    target.write(version)
    console.log(`  ${target.path} -> ${version}`)
  }
  console.log(`Set version to ${version}.`)
}

if (import.meta.main) main()
