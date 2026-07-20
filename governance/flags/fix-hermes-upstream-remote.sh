#!/usr/bin/env bash
# Host-only: hermes-agent is Kart read-only (gitsync fetch_err).
# NousResearch/hermes-agent was repurposed; drop poisoned upstream remote.
set -euo pipefail
repo="${HOME}/github/hermes-agent"
if git -C "$repo" remote | grep -qx upstream; then
  git -C "$repo" remote rename upstream upstream-nousresearch-stale \
    || git -C "$repo" remote remove upstream
fi
git -C "$repo" remote -v
