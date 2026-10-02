# Workflow scripts

Every multi-line step body in `.github/workflows/` lives here as a file, so that
`shellcheck` lints it, `git blame` explains it and you can run it by hand. The
`shellcheck` hook in `.pre-commit-config.yaml` covers everything in here.

## Layout

```
lib/          sourced, never executed: no shebang line of its own, not executable
shared/       scripts more than one workflow calls
<workflow>/   one directory per workflow file, one script per step
```

A script is named after its step's `name:`, kebab-cased: `Trigger the
deployment` in `deploy-coolify.yml` is `deploy-coolify/trigger-the-deployment.sh`.

## Conventions

- `#!/usr/bin/env bash`, then `set -euo pipefail`, and the executable bit.
- **GitHub expressions never reach the command line.** A `${{ … }}` value goes
  in the step's `env:` block and the script reads the environment variable.
  Interpolating it into `run:` would put attacker-controllable text through a
  shell parse (the template-injection class zizmor audits for) and put secrets
  in a process's argv.
- The working directory is the repository root, as GitHub runs a step there.
- The comments explaining *why* a step does something live in the script, with
  the code they describe.
