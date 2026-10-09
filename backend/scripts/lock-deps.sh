#!/usr/bin/env bash
# Regenerate backend/requirements.lock, the exact versions CI, the container
# image, and development install.
#
#   backend/scripts/lock-deps.sh
#
# Resolves in a clean Linux Python 3.12 container (what CI and the image run),
# from pyproject.toml's ranges, then runs the full test suite against the result.
# Commit the new lock only if the tests pass. Needs docker, or set DOCKER=finch.
set -euo pipefail

DOCKER="${DOCKER:-docker}"
BACKEND="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(dirname "$BACKEND")"

"$DOCKER" run --rm -v "$REPO:/src" -w /src/backend python:3.12 sh -ec '
  pip install -q --upgrade pip
  pip install -q -e ".[dev,postgres]"
  {
    echo "# Exact versions for CI, the container image, and local development, so all three run what the tests ran."
    echo "# Generated on Linux, Python 3.12: pip install -e \".[dev,postgres]\" && pip freeze --exclude-editable"
    echo "# Regenerate deliberately to take upgrades, then run the full suite. See backend/scripts/lock-deps.sh."
    pip freeze --exclude-editable
  } > requirements.lock.new
  python -m pytest -q -p no:warnings
  mv requirements.lock.new requirements.lock
  echo "requirements.lock updated: $(grep -vc "^#" requirements.lock) packages"
'
