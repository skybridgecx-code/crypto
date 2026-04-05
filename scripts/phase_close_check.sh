#!/usr/bin/env bash
set -euo pipefail

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Phase close check failed: current directory is not inside a git repository." >&2
  exit 1
fi

repo_root="$(git rev-parse --show-toplevel)"
cd "${repo_root}"

if [[ ! -f "pyproject.toml" ]]; then
  echo "Phase close check failed: pyproject.toml not found at repository root." >&2
  exit 1
fi

if ! grep -q '^name = "crypto-agent"' "pyproject.toml"; then
  echo "Phase close check failed: repository root does not match crypto-agent project." >&2
  exit 1
fi

head_sha="$(git rev-parse --short HEAD)"
branch_name="$(git rev-parse --abbrev-ref HEAD)"

echo "repo_root=${repo_root}"
echo "head=${head_sha}"
echo "branch=${branch_name}"
echo "Running make validate-check..."

make validate-check

status_output="$(git status --porcelain)"

if [[ -n "${status_output}" ]]; then
  echo "Phase close check failed: validate-check passed but the worktree is still dirty." >&2
  echo "${status_output}" >&2
  echo "Commit intended changes or revert remaining churn before treating the phase as closed." >&2
  exit 1
fi

echo "Phase close check passed: validate-check succeeded and the worktree is clean."
