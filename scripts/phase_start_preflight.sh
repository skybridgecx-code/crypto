#!/usr/bin/env bash
set -euo pipefail

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Preflight failed: current directory is not inside a git repository." >&2
  exit 1
fi

repo_root="$(git rev-parse --show-toplevel)"
cd "${repo_root}"

if [[ ! -f "pyproject.toml" ]]; then
  echo "Preflight failed: pyproject.toml not found at repository root." >&2
  exit 1
fi

if ! grep -q '^name = "crypto-agent"' "pyproject.toml"; then
  echo "Preflight failed: repository root does not match crypto-agent project." >&2
  exit 1
fi

head_sha="$(git rev-parse --short HEAD)"
branch_name="$(git rev-parse --abbrev-ref HEAD)"
status_output="$(git status --porcelain)"

echo "repo_root=${repo_root}"
echo "head=${head_sha}"
echo "branch=${branch_name}"

if [[ -n "${status_output}" ]]; then
  echo "Preflight failed: worktree is not clean." >&2
  echo "${status_output}" >&2
  echo "Stash or commit interrupted work before starting a new bounded phase." >&2
  exit 1
fi

echo "Preflight passed: repo, HEAD, and clean-tree checks are all valid."
