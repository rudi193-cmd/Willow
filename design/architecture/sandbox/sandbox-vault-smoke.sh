#!/usr/bin/env bash
# sandbox-vault-smoke.sh — smoke with {user}-data-vault layout
#
# Postgres PGDATA, SOIL collections, secrets (vault.db + vault.key), receipts,
# and Kart SQLite queue all live inside the provisioned box per willow-data-vault.
#
# Usage:
#   ./sandbox-vault-smoke.sh --fresh
#   GITHUB_ROOT=~/github ./sandbox-vault-smoke.sh
#
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sandbox-smoke.sh" --vault "$@"
