#!/usr/bin/env bash
# scripts/release_v3.sh -- orchestrate the Vedix v3.0.0 public release.
#
# What this script does, in order:
#   1. Verify the working tree is clean (no unstaged or untracked changes).
#   2. Run the cross-block smoke harness against the live SaaS (skips if
#      VEDIX_SAAS_TOKEN is unset; release-day operator must export it).
#   3. Build the MkDocs documentation site at docs/site/.
#   4. Tag the current HEAD as v3.0.0 and push the tag.
#   5. Build the VS Code extension (.vsix) and the JetBrains plugin (.zip).
#   6. Build + upload the Python package to PyPI via `twine`.
#
# Usage:
#   bash scripts/release_v3.sh             # full release
#   DRY_RUN=1 bash scripts/release_v3.sh   # skip push + publish steps
#
# Required env vars on a real release:
#   VEDIX_SAAS_TOKEN  -- bearer token for the live SaaS (enables smoke)
#   VEDIX_SAAS_URL    -- defaults to https://api.vedix.ai
#   TWINE_USERNAME    -- pypi username (usually __token__)
#   TWINE_PASSWORD    -- pypi API token
#
# The script is intentionally noisy: every step prints both its name and
# the exact command being run. If something fails mid-flight, the operator
# can resume from the failing step by hand.

set -euo pipefail

VERSION="3.0.0"
TAG="v${VERSION}"
DRY_RUN="${DRY_RUN:-0}"

# -------------------- helpers --------------------

step()  { printf "\n\033[36m[release]\033[0m %s\n" "$1"; }
ok()    { printf "  \033[32m[OK]\033[0m %s\n" "$1"; }
warn()  { printf "  \033[33m[WARN]\033[0m %s\n" "$1"; }
err()   { printf "  \033[31m[ERR]\033[0m %s\n" "$1" >&2; }

run() {
  printf "  \033[90m$ %s\033[0m\n" "$*"
  if [[ "${DRY_RUN}" == "1" ]]; then
    return 0
  fi
  "$@"
}

# -------------------- step 1: clean tree --------------------

step "verifying clean working tree"
if [[ -n "$(git status --porcelain)" ]]; then
  err "working tree is dirty; commit or stash first"
  git status --short
  exit 1
fi
ok "tree clean"

# -------------------- step 2: smoke --------------------

step "running cross-block smoke harness"
if [[ -z "${VEDIX_SAAS_TOKEN:-}" ]]; then
  warn "VEDIX_SAAS_TOKEN unset; smoke will SKIP the live-SaaS tests"
fi
run python -m pytest -m smoke tests/smoke/ -v --tb=short
ok "smoke passed"

# -------------------- step 3: docs site --------------------

step "building MkDocs documentation site"
(
  cd docs/site
  run python -m mkdocs build --clean
)
ok "docs built at docs/site/site/"

# -------------------- step 4: git tag --------------------

step "tagging ${TAG}"
if git rev-parse "${TAG}" >/dev/null 2>&1; then
  warn "tag ${TAG} already exists locally; skipping creation"
else
  run git tag -a "${TAG}" -m "Vedix v${VERSION} -- first public release"
  ok "tag ${TAG} created"
fi

step "pushing ${TAG} to origin"
if [[ "${DRY_RUN}" == "1" ]]; then
  warn "DRY_RUN=1; skipping push"
else
  run git push origin "${TAG}"
  ok "tag pushed"
fi

# -------------------- step 5: IDE builds --------------------

step "building VS Code extension (.vsix)"
if [[ -d plugins/vedix/ide/vscode ]]; then
  (
    cd plugins/vedix/ide/vscode
    run npm ci --silent
    run npm run package
  )
  ok "vsix built"
else
  warn "plugins/vedix/ide/vscode not present; skipping"
fi

step "building JetBrains plugin (.zip)"
if [[ -d plugins/vedix/ide/jetbrains ]]; then
  (
    cd plugins/vedix/ide/jetbrains
    if [[ -x ./gradlew ]]; then
      run ./gradlew buildPlugin
    else
      run gradle buildPlugin
    fi
  )
  ok "jetbrains plugin built"
else
  warn "plugins/vedix/ide/jetbrains not present; skipping"
fi

# -------------------- step 6: pypi --------------------

step "building + publishing Python package to PyPI"
if [[ "${DRY_RUN}" == "1" ]]; then
  warn "DRY_RUN=1; skipping pypi publish"
elif [[ -d plugins/vedix ]]; then
  (
    cd plugins/vedix
    rm -rf dist build
    run python -m build
    run python -m twine upload --non-interactive dist/*
  )
  ok "pypi publish complete"
else
  warn "plugins/vedix not present; skipping pypi"
fi

# -------------------- done --------------------

step "release pipeline finished"
ok "tag: ${TAG}"
ok "docs:  docs/site/site/"
ok "vsix:  plugins/vedix/ide/vscode/*.vsix"
ok "plugin: plugins/vedix/ide/jetbrains/build/distributions/*.zip"
echo ""
echo "Next manual steps:"
echo "  - Post launch content: Habr, vc.ru, HN, X thread (see docs/launch/)."
echo "  - Record + upload the YouTube demo (script in docs/launch/)."
echo "  - Watch Sentry + arq queue for the first 24h post-launch."
