#!/usr/bin/env bash
# sandbox-layout-drive.sh — compare hub vs vault-full vs vault-external layouts
#
# Runs fresh + reuse for each layout with identical probe permissions, then
# writes LAYOUT-DRIVE.md with measured results.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GITHUB_ROOT="${GITHUB_ROOT:-$(cd "$SCRIPT_DIR/../../../.." && pwd)}"
REPORT="$SCRIPT_DIR/LAYOUT-DRIVE.md"
SMOKE="$SCRIPT_DIR/sandbox-smoke.sh"

# Same admin seat for apples-to-apples (KB + store write probes).
export SMOKE_DATA_PLANE_PROBE=1
export SANDBOX_APP_ID=sandbox-vault-admin

RESULTS=$(mktemp)
echo -e "layout\tfresh_exit\treuse_exit\tfresh_sec\treuse_sec\tdoctor\tkart\tdata_plane\treuse_ok" >"$RESULTS"

run_layout() {
  local name="$1"
  shift
  local smoke_args=()
  local env_args=()
  local arg
  for arg in "$@"; do
    case "$arg" in
      --*) smoke_args+=("$arg") ;;
      *=*) env_args+=("$arg") ;;
    esac
  done
  local fresh_sec reuse_sec fresh_exit reuse_exit
  local doctor kart data_plane reuse_ok

  echo "" >&2
  echo "======== layout: $name (fresh) ========" >&2
  local t0=$(date +%s)
  if env "${env_args[@]}" "$SMOKE" "${smoke_args[@]}" --fresh >"/tmp/sandbox-layout-${name}-fresh.log" 2>&1; then
    fresh_exit=0
  else
    fresh_exit=$?
  fi
  fresh_sec=$(( $(date +%s) - t0 ))

  echo "" >&2
  echo "======== layout: $name (reuse) ========" >&2
  local t1=$(date +%s)
  if env "${env_args[@]}" "$SMOKE" "${smoke_args[@]}" >"/tmp/sandbox-layout-${name}-reuse.log" 2>&1; then
    reuse_exit=0
    reuse_ok=yes
  else
    reuse_exit=$?
    reuse_ok=no
  fi
  reuse_sec=$(( $(date +%s) - t1 ))

  doctor=$(grep -o 'diagnostic_summary verdict: [a-z]*' "/tmp/sandbox-layout-${name}-fresh.log" | tail -1 | awk '{print $NF}')
  kart=$(grep -E 'PASS: kart task completed|Kart:.*completed' "/tmp/sandbox-layout-${name}-fresh.log" | head -1 | sed 's/PASS: //;s/^- \*\*Kart:\*\* //')
  data_plane=$(grep -c 'PASS: data plane' "/tmp/sandbox-layout-${name}-fresh.log" || true)

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$name" "$fresh_exit" "$reuse_exit" "$fresh_sec" "$reuse_sec" \
    "${doctor:-?}" "${kart:-?}" "${data_plane:-0}" "$reuse_ok" >>"$RESULTS"

  tail -20 "/tmp/sandbox-layout-${name}-fresh.log" >&2
}

run_layout hub \
  LAYOUT_NAME=hub \
  SANDBOX_ROOT="$SCRIPT_DIR/.sandbox-layout-hub" \
  REPORT="$SCRIPT_DIR/LAST-RUN-hub.md" \
  PG_CONTAINER=willow-layout-hub-pg \
  PG_PORT=55432

run_layout vault-full --vault \
  LAYOUT_NAME=vault-full \
  SANDBOX_ROOT="$SCRIPT_DIR/.sandbox-layout-vault-full" \
  REPORT="$SCRIPT_DIR/LAST-RUN-vault-full.md" \
  PG_CONTAINER=willow-layout-vault-full-pg \
  PG_PORT=55433

run_layout vault-external --vault --vault-external-pg \
  LAYOUT_NAME=vault-external \
  SANDBOX_ROOT="$SCRIPT_DIR/.sandbox-layout-vault-external" \
  REPORT="$SCRIPT_DIR/LAST-RUN-vault-external.md" \
  PG_CONTAINER=willow-layout-vault-external-pg \
  PG_PORT=55434

{
  echo "# Sandbox layout drive"
  echo ""
  echo "**UTC:** $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo ""
  echo "See [SANDBOX-LAYOUTS.md](SANDBOX-LAYOUTS.md) for I/O diagrams."
  echo ""
  echo "## Results (fresh + reuse)"
  echo ""
  echo '```tsv'
  column -t -s $'\t' "$RESULTS"
  echo '```'
  echo ""
  echo "## Per-layout reports"
  echo ""
  echo "| Layout | Fresh report |"
  echo "|--------|--------------|"
  echo "| hub | [LAST-RUN-hub.md](LAST-RUN-hub.md) |"
  echo "| vault-full | [LAST-RUN-vault-full.md](LAST-RUN-vault-full.md) |"
  echo "| vault-external | [LAST-RUN-vault-external.md](LAST-RUN-vault-external.md) |"
} >"$REPORT"

cat "$REPORT"
rm -f "$RESULTS"
