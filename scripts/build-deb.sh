#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

if ! command -v debuild >/dev/null 2>&1; then
  echo "debuild is required (install devscripts)" >&2
  exit 1
fi

if ! command -v dh >/dev/null 2>&1; then
  echo "debhelper is required" >&2
  exit 1
fi

export DEB_BUILD_OPTIONS="${DEB_BUILD_OPTIONS:-nocheck}"
debuild -us -uc -b

if command -v lintian >/dev/null 2>&1; then
  CHANGES="$(ls -1t ../capiforge_*_all.changes 2>/dev/null | head -1 || true)"
  if [[ -n "${CHANGES}" ]]; then
    lintian "${CHANGES}" || true
  fi
fi

echo "Debian package build complete."
