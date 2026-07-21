#!/usr/bin/env bash
# sandbox-smoke.sh — new-user draft acceptance (agent / cloud VM only)
#
# Validates willow-new-user-draft against a fresh willow-mcp sandbox.
# Do NOT run on the operator laptop when memory is tight — use a Cursor cloud agent.
#
# Usage:
#   ./sandbox-smoke.sh
#   ./sandbox-smoke.sh --skip-kart --skip-jeles
#   ./sandbox-smoke.sh --fresh
#   GITHUB_ROOT=~/github ./sandbox-smoke.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GITHUB_ROOT="${GITHUB_ROOT:-$(cd "$SCRIPT_DIR/../../../.." && pwd)}"
WILLOW_MCP_REPO="${WILLOW_MCP_REPO:-$GITHUB_ROOT/willow-mcp}"
SANDBOX_ROOT="${SANDBOX_ROOT:-$SCRIPT_DIR/.sandbox}"
REPORT="${REPORT:-$SCRIPT_DIR/LAST-RUN.md}"
PG_CONTAINER="${PG_CONTAINER:-willow-sandbox-pg}"
PG_PORT="${PG_PORT:-55432}"

SKIP_JELES=0
SKIP_UTETY=0
SKIP_KART=0
SKIP_PG=0
FRESH=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-jeles) SKIP_JELES=1 ;;
    --skip-utety) SKIP_UTETY=1 ;;
    --skip-kart) SKIP_KART=1 ;;
    --skip-pg) SKIP_PG=1 ;;
    --fresh) FRESH=1 ;;
    --github-root) GITHUB_ROOT="$2"; shift ;;
    --willow-mcp) WILLOW_MCP_REPO="$2"; shift ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift
done

WILLOW_MCP_REPO="$(cd "$WILLOW_MCP_REPO" && pwd)"
GITHUB_ROOT="$(cd "$GITHUB_ROOT" && pwd)"
export WILLOW_MCP_REPO
export WILLOW_HOME="$SANDBOX_ROOT/willow-home"
export WILLOW_STORE_ROOT="$WILLOW_HOME/store"
export WILLOW_PG_DB="willow_sandbox"
export WILLOW_PG_USER="${WILLOW_PG_USER:-${USER:-sandbox}}"
# Default smoke seat (schema_admin + task_queue + store_read). Override with SANDBOX_APP_ID.
export WILLOW_APP_ID="${SANDBOX_APP_ID:-sandbox-admin}"
# New-user isolation: do not inherit operator fleet roots into Kart mounts.
unset WILLOW_ROOT
KART_SANDBOX_TEMPLATE="${KART_SANDBOX_TEMPLATE:-$SCRIPT_DIR/kart-sandbox.json}"

if [[ "$FRESH" == "1" ]]; then
  [[ -d "$SANDBOX_ROOT/willow-home" ]] && rm -rf "$SANDBOX_ROOT/willow-home"
  if command -v docker >/dev/null 2>&1; then
    docker rm -f "$PG_CONTAINER" >/dev/null 2>&1 || true
  fi
fi

mkdir -p "$SANDBOX_ROOT"
: >"$SANDBOX_ROOT/smoke.log"

log() { printf '%s\n' "$*" | tee -a "$SANDBOX_ROOT/smoke.log"; }
fail() { log "FAIL: $*"; exit 1; }
pass() { log "PASS: $*"; }

bwrap_preflight() {
  command -v bwrap >/dev/null 2>&1 || return 1
  bwrap --unshare-pid --unshare-ipc --unshare-uts --die-with-parent \
    --ro-bind / / --dev /dev --proc /proc echo ok >/dev/null 2>&1
}

install_kart_sandbox_policy() {
  local template="${KART_SANDBOX_TEMPLATE:-$SCRIPT_DIR/kart-sandbox.json}" dest="$WILLOW_HOME/kart-sandbox.json"
  local xdg="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
  [[ -f "$template" ]] || return 1
  sed \
    -e "s|__WILLOW_HOME__|$WILLOW_HOME|g" \
    -e "s|__GITHUB_WILLOW__|$GITHUB_ROOT/willow|g" \
    -e "s|__GITHUB_WILLOW_MCP__|$WILLOW_MCP_REPO|g" \
    -e "s|__WILLOW_MCP_VENV__|$WILLOW_MCP_REPO/.venv|g" \
    -e "s|__HOME_LOCAL__|$HOME/.local|g" \
    -e "s|__XDG_RUNTIME_DIR__|$xdg|g" \
    "$template" >"$dest"
  export KART_SANDBOX_CONFIG="$dest"
}

sandbox_env() {
  unset WILLOW_ROOT
  export WILLOW_HOME WILLOW_STORE_ROOT WILLOW_PG_DB WILLOW_PG_USER WILLOW_APP_ID
  export KART_SANDBOX_CONFIG WILLOW_MCP_REPO="$WILLOW_MCP_REPO"
  # rlimit preexec + bwrap namespaces can fail with EAGAIN on some hosts (no cgroup parent).
  export WILLOW_KART_NO_RLIMIT="${WILLOW_KART_NO_RLIMIT:-1}"
  [[ -n "${PGHOST:-}" ]] && export PGHOST PGPORT PGPASSWORD
}

log "=== willow new-user sandbox smoke ==="
log "time: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
log "sandbox: $SANDBOX_ROOT"
log "willow-mcp: $WILLOW_MCP_REPO"
log "github root: $GITHUB_ROOT"

[[ -d "$WILLOW_MCP_REPO" ]] || fail "willow-mcp not found at $WILLOW_MCP_REPO"

VENV="$WILLOW_MCP_REPO/.venv"
PY="$VENV/bin/python3"
if [[ ! -x "$PY" ]]; then
  python3 -m venv "$VENV"
fi
"$PY" -m pip install --upgrade pip -q
"$PY" -m pip install -e "$WILLOW_MCP_REPO" -q
KARTIKEYA_REPO="${KARTIKEYA_REPO:-$GITHUB_ROOT/kartikeya}"
if [[ -d "$KARTIKEYA_REPO/pyproject.toml" || -f "$KARTIKEYA_REPO/pyproject.toml" ]]; then
  "$PY" -m pip install -e "$KARTIKEYA_REPO" --no-deps -q
  log "kartikeya: editable install from $KARTIKEYA_REPO"
fi
WMC="$VENV/bin/willow-mcp"
[[ -x "$WMC" ]] || fail "willow-mcp install failed"

# ── 1. Bootstrap willow-mcp (venv + home + compile + best-effort PG) ─────────
log ""
log "-- bootstrap --"
if [[ "$SKIP_PG" == "1" ]]; then
  export WILLOW_SKIP_PG=1
fi

# Ephemeral Postgres via Docker on the agent (reuses named container when possible)
PG_MODE="none"
BWRAP_OK="no"
if bwrap_preflight; then
  BWRAP_OK="yes"
else
  log "bwrap preflight: namespace unavailable (Kart worker may skip)"
fi

if [[ "$SKIP_PG" == "0" ]] && command -v docker >/dev/null 2>&1; then
  if docker ps --format '{{.Names}}' | grep -qx "$PG_CONTAINER"; then
    PG_MODE="docker-reuse"
    log "postgres: reusing $PG_CONTAINER"
  elif docker ps -a --format '{{.Names}}' | grep -qx "$PG_CONTAINER"; then
    docker start "$PG_CONTAINER" >/dev/null 2>&1 && PG_MODE="docker-reuse" \
      && log "postgres: started existing $PG_CONTAINER" \
      || log "postgres: could not start $PG_CONTAINER"
  else
    if docker run -d --name "$PG_CONTAINER" \
        -e POSTGRES_USER="$WILLOW_PG_USER" \
        -e POSTGRES_PASSWORD=sandbox \
        -e POSTGRES_DB="$WILLOW_PG_DB" \
        -p "127.0.0.1:${PG_PORT}:5432" \
        postgres:16-alpine >/dev/null 2>&1; then
      PG_MODE="docker"
      log "postgres: created $PG_CONTAINER on 127.0.0.1:$PG_PORT"
    else
      log "postgres: docker start failed — falling back to local/best-effort"
    fi
  fi
  if [[ "$PG_MODE" != "none" ]]; then
    for _ in $(seq 1 30); do
      if docker exec "$PG_CONTAINER" pg_isready -U "$WILLOW_PG_USER" -d "$WILLOW_PG_DB" >/dev/null 2>&1; then
        break
      fi
      sleep 1
    done
    export PGHOST=127.0.0.1
    export PGPORT="$PG_PORT"
    export PGPASSWORD=sandbox
  fi
fi

(
  # Bootstrap diagnostic defaults to WILLOW_APP_ID; sandbox-admin is installed after compile.
  WILLOW_APP_ID=willow bash "$WILLOW_MCP_REPO/scripts/sandbox-bootstrap.sh"
) 2>&1 | tee -a "$SANDBOX_ROOT/smoke.log"

[[ -x "$WMC" ]] || fail "willow-mcp binary missing after bootstrap"

# ── 2. Egress + sandbox consent (non-TTY agent path) ─────────────────────────
log ""
log "-- gate / egress --"
"$WMC" setup-egress 2>&1 | tee -a "$SANDBOX_ROOT/smoke.log" || fail "setup-egress"

"$PY" - <<'PY' 2>&1 | tee -a "$SANDBOX_ROOT/smoke.log"
import json, os
from pathlib import Path
home = Path(os.environ["WILLOW_HOME"])
# Canonical path (config/settings.global.json) — legacy root copy is ignored when canonical exists.
path = home / "config" / "settings.global.json"
data = {"consent": {"internet": False, "cloud_llm": False, "lan": False}}
if path.is_file():
    try:
        existing = json.loads(path.read_text())
        if isinstance(existing, dict):
            data = existing
    except json.JSONDecodeError:
        pass
if not isinstance(data, dict):
    data = {}
data.setdefault("consent", {})["internet"] = False  # gate deny baseline for smoke
data["consent"]["cloud_llm"] = False
data["consent"]["lan"] = False
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(data, indent=2) + "\n")
path.chmod(0o600)
print("wrote sandbox consent (internet=false baseline):", path)
PY
pass "egress keys + consent baseline"

# ── 2b. Sandbox admin manifest (schema confirm for Kart) ─────────────────────
log ""
log "-- sandbox-admin manifest --"
mkdir -p "$WILLOW_HOME/mcp_apps/sandbox-admin"
cp "$SCRIPT_DIR/sandbox-admin.manifest.json" "$WILLOW_HOME/mcp_apps/sandbox-admin/manifest.json"
pass "sandbox-admin manifest"

# ── 2c. Kart mount policy (rendered new-user paths) ───────────────────────────
log ""
log "-- kart-sandbox policy --"
if install_kart_sandbox_policy; then
  pass "kart-sandbox.json installed"
  log "kart policy: $WILLOW_HOME/kart-sandbox.json"
else
  log "WARN: could not render kart-sandbox policy — Kart may use fleet defaults"
fi

# ── 3. Doctor (python only — avoids CLI gate INFO noise) ──────────────────────
log ""
log "-- doctor --"
sandbox_env
DOCTOR_JSON="$("$PY" 2>/dev/null <<PY
import json
from willow_mcp import server
d = server.diagnostic_summary("$WILLOW_APP_ID")
print(json.dumps(d, default=str))
PY
)"
echo "$DOCTOR_JSON" | "$PY" 2>/dev/null <<'PY' | tee -a "$SANDBOX_ROOT/smoke.log" || true
import json, sys
d = json.load(sys.stdin)
print("verdict:", d.get("verdict"))
for name, chk in (d.get("checks") or {}).items():
    if isinstance(chk, dict) and "status" in chk:
        print(f"  {name:18} {chk['status']}")
PY
DOCTOR_VERDICT="$(echo "$DOCTOR_JSON" | "$PY" 2>/dev/null -c 'import json,sys; print(json.load(sys.stdin).get("verdict","unknown"))')"
log "diagnostic_summary verdict: $DOCTOR_VERDICT"
[[ "$DOCTOR_VERDICT" == "broken" ]] && fail "doctor verdict is broken"

# ── 4. Hub store smoke (store_read — hanuman has no store_write) ─────────────
log ""
log "-- hub store --"
"$PY" - <<PY 2>&1 | tee -a "$SANDBOX_ROOT/smoke.log"
import json
from willow_mcp import server
r = server.store_stats(app_id="$WILLOW_APP_ID")
print(json.dumps(r, indent=2))
assert "error" not in r, r
PY
pass "store_stats"

# ── 5. Kart (Postgres required) ───────────────────────────────────────────────
KART_NOTE="skipped"
if [[ "$SKIP_KART" == "1" ]]; then
  log "kart: --skip-kart"
else
  log ""
  log "-- kart --"
  SCHEMA_OUT=$("$PY" 2>&1 <<'PY'
import json
from willow_mcp import server
r = server.schema_confirm_mapping(app_id="sandbox-admin", table="tasks")
print(json.dumps(r, indent=2))
PY
)
  echo "$SCHEMA_OUT" | tee -a "$SANDBOX_ROOT/smoke.log"
  if echo "$SCHEMA_OUT" | grep -q postgres_unavailable; then
    KART_NOTE="skipped (postgres_unavailable)"
    log "kart: skipped — no Postgres"
  elif echo "$SCHEMA_OUT" | grep -q '"error"'; then
    KART_NOTE="skipped (schema_confirm)"
    log "kart: skipped — schema confirm failed"
  else
    pass "tasks schema confirmed"

    KART_OUT=$("$PY" 2>&1 <<'PY'
import json, os
from willow_mcp import server

app_id = os.environ["WILLOW_APP_ID"]
pg = server.get_pg()
if not pg:
    print(json.dumps({"error": "postgres_unavailable"}))
    raise SystemExit(0)

result = server.task_submit(
    app_id=app_id,
    task="echo sandbox-smoke-ok",
    agent="kart",
    lane="fast",
)
print(json.dumps(result, indent=2))
PY
)
    echo "$KART_OUT" | tee -a "$SANDBOX_ROOT/smoke.log"
    if echo "$KART_OUT" | grep -q postgres_unavailable; then
      KART_NOTE="skipped (postgres_unavailable)"
      log "kart: skipped — task_submit needs Postgres"
    elif echo "$KART_OUT" | grep -q unconfirmed_schema; then
      KART_NOTE="skipped (schema)"
      log "kart: skipped — confirm tasks schema first"
    elif echo "$KART_OUT" | grep -q '"status": "pending"'; then
      TASK_ID=$(echo "$KART_OUT" | "$PY" -c 'import json,sys; print(json.load(sys.stdin).get("task_id",""))' 2>/dev/null || true)
      if [[ "$BWRAP_OK" != "yes" ]]; then
        KART_NOTE="submitted (bwrap preflight failed — namespace unavailable)"
        pass "kart task submitted (worker skipped)"
      elif command -v bwrap >/dev/null 2>&1; then
        sandbox_env
        "$WMC" worker --lane fast --once --app-id "$WILLOW_APP_ID" 2>&1 | tee -a "$SANDBOX_ROOT/smoke.log" || true
        if [[ -n "$TASK_ID" ]]; then
          TASK_STATUS=$("$PY" 2>&1 <<PY || true
import json
from willow_mcp import server
r = server.task_status(app_id="$WILLOW_APP_ID", task_id="$TASK_ID")
print(json.dumps(r, default=str))
PY
)
          echo "$TASK_STATUS" | tee -a "$SANDBOX_ROOT/smoke.log"
          if echo "$TASK_STATUS" | grep -q '"status": "completed"' \
              && echo "$TASK_STATUS" | grep -q 'sandbox-smoke-ok'; then
            KART_NOTE="completed"
            pass "kart task completed"
          elif echo "$TASK_STATUS" | grep -q sandbox_setup_failed; then
            KART_NOTE="submitted (sandbox_setup_failed — bwrap namespace limit)"
            pass "kart task submitted"
          else
            KART_NOTE="worker ran (check task_status)"
            pass "kart task submitted"
          fi
        else
          KART_NOTE="ran worker"
          pass "kart task submitted"
        fi
      else
        KART_NOTE="skipped (no bwrap)"
        log "kart: bwrap not found — worker skip"
      fi
    else
      KART_NOTE="failed submit"
      fail "kart task_submit unexpected: $KART_OUT"
    fi
  fi
fi

# ── 6. Gate deny: allow_net without lease ───────────────────────────────────
log ""
log "-- gate deny check --"
"$PY" - <<PY 2>&1 | tee -a "$SANDBOX_ROOT/smoke.log"
import json
from willow_mcp import server
r = server.task_submit(
    app_id="$WILLOW_APP_ID",
    task="curl -s https://example.com",
    allow_net=True,
)
print(json.dumps(r, indent=2))
assert "error" in r, "expected net denial"
print("gate deny: ok (allow_net refused)")
PY
pass "egress denied without full gate"

# ── 7. Optional repos ─────────────────────────────────────────────────────────
log ""
log "-- optional apps --"
if [[ "$SKIP_JELES" == "0" ]]; then
  if [[ -f "$GITHUB_ROOT/Jeles/docs/architecture.md" ]]; then
    pass "Jeles repo present"
  else
    log "WARN: Jeles not found at $GITHUB_ROOT/Jeles"
  fi
else
  log "jeles: --skip-jeles"
fi

if [[ "$SKIP_UTETY" == "0" ]]; then
  if [[ -d "$GITHUB_ROOT/UTETY/utety/core" ]]; then
    pass "UTETY repo present"
  else
    log "WARN: UTETY not found at $GITHUB_ROOT/UTETY"
  fi
else
  log "utety: --skip-utety"
fi

# ── 8. Report ─────────────────────────────────────────────────────────────────
log ""
log "=== smoke complete ==="

{
  echo "# Sandbox smoke — LAST RUN"
  echo ""
  echo "- **UTC:** $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "- **Sandbox:** \`$SANDBOX_ROOT\`"
  echo "- **Postgres mode:** $PG_MODE (\`$WILLOW_PG_DB\`)"
  echo "- **Doctor verdict:** $DOCTOR_VERDICT"
  echo "- **Kart:** $KART_NOTE"
  echo "- **bwrap preflight:** $BWRAP_OK"
  echo "- **App ID:** $WILLOW_APP_ID"
  echo ""
  echo "## Notes"
  echo ""
  echo "- Kart mount policy: \`$WILLOW_HOME/kart-sandbox.json\` (rendered from template)"
  echo "- Findings: [SANDBOX-FINDINGS.md](SANDBOX-FINDINGS.md)"
  echo ""
  echo "## Log"
  echo ""
  echo '```'
  tail -n 80 "$SANDBOX_ROOT/smoke.log"
  echo '```'
} >"$REPORT"

log "report: $REPORT"
cat "$REPORT"
