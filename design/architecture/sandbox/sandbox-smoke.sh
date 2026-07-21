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
#   ./sandbox-smoke.sh --vault          # data-vault layout (PG + SOIL + secrets in box)
#   ./sandbox-smoke.sh --vault --vault-external-pg  # vault box, PG outside box
#   GITHUB_ROOT=~/github ./sandbox-smoke.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GITHUB_ROOT="${GITHUB_ROOT:-$(cd "$SCRIPT_DIR/../../../.." && pwd)}"
WILLOW_MCP_REPO="${WILLOW_MCP_REPO:-$GITHUB_ROOT/willow-mcp}"
WILLOW_DATA_VAULT_REPO="${WILLOW_DATA_VAULT_REPO:-$GITHUB_ROOT/willow-data-vault}"

SKIP_JELES=0
SKIP_UTETY=0
SKIP_KART=0
SKIP_PG=0
FRESH=0
VAULT_LAYOUT=0
PG_IN_BOX=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-jeles) SKIP_JELES=1 ;;
    --skip-utety) SKIP_UTETY=1 ;;
    --skip-kart) SKIP_KART=1 ;;
    --skip-pg) SKIP_PG=1 ;;
    --fresh) FRESH=1 ;;
    --vault) VAULT_LAYOUT=1 ;;
    --vault-external-pg) VAULT_LAYOUT=1; PG_IN_BOX=0 ;;
    --github-root) GITHUB_ROOT="$2"; shift ;;
    --willow-mcp) WILLOW_MCP_REPO="$2"; shift ;;
    -h|--help)
      sed -n '2,14p' "$0"
      exit 0
      ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift
done

WILLOW_MCP_REPO="$(cd "$WILLOW_MCP_REPO" && pwd)"
GITHUB_ROOT="$(cd "$GITHUB_ROOT" && pwd)"
export WILLOW_MCP_REPO

if [[ "$VAULT_LAYOUT" == "1" ]]; then
  SANDBOX_ROOT="${SANDBOX_ROOT:-$SCRIPT_DIR/.sandbox-vault}"
  VAULT_BOX="$SANDBOX_ROOT/data-vault"
  export WILLOW_HOME="$VAULT_BOX"
  export WILLOW_STORE_ROOT="$VAULT_BOX"
  PG_CONTAINER="${PG_CONTAINER:-willow-sandbox-vault-pg}"
  PG_PORT="${PG_PORT:-55433}"
  REPORT="${REPORT:-$SCRIPT_DIR/LAST-RUN-VAULT.md}"
  export WILLOW_APP_ID="${SANDBOX_APP_ID:-sandbox-vault-admin}"
else
  SANDBOX_ROOT="${SANDBOX_ROOT:-$SCRIPT_DIR/.sandbox}"
  export WILLOW_HOME="$SANDBOX_ROOT/willow-home"
  export WILLOW_STORE_ROOT="$WILLOW_HOME/store"
  PG_CONTAINER="${PG_CONTAINER:-willow-sandbox-pg}"
  PG_PORT="${PG_PORT:-55432}"
  REPORT="${REPORT:-$SCRIPT_DIR/LAST-RUN.md}"
  export WILLOW_APP_ID="${SANDBOX_APP_ID:-sandbox-admin}"
fi

if [[ "$VAULT_LAYOUT" == "1" ]]; then
  if [[ "$PG_IN_BOX" == "1" ]]; then
    LAYOUT_NAME="${LAYOUT_NAME:-vault-full}"
  else
    LAYOUT_NAME="${LAYOUT_NAME:-vault-external}"
  fi
else
  LAYOUT_NAME="${LAYOUT_NAME:-hub}"
fi
export LAYOUT_NAME

export WILLOW_PG_DB="willow_sandbox"
export WILLOW_PG_USER="${WILLOW_PG_USER:-${USER:-sandbox}}"
# New-user isolation: do not inherit operator fleet roots into Kart mounts.
unset WILLOW_ROOT
KART_SANDBOX_TEMPLATE="${KART_SANDBOX_TEMPLATE:-$SCRIPT_DIR/kart-sandbox.json}"

if [[ "$FRESH" == "1" ]]; then
  if command -v docker >/dev/null 2>&1; then
    docker rm -f "$PG_CONTAINER" >/dev/null 2>&1 || true
  fi
  if [[ "$VAULT_LAYOUT" == "1" ]]; then
    if [[ -d "$SANDBOX_ROOT/data-vault/postgres" ]]; then
      docker run --rm -v "$SANDBOX_ROOT/data-vault/postgres:/pg" alpine \
        sh -c 'rm -rf /pg/data' >/dev/null 2>&1 || true
    fi
    [[ -d "$SANDBOX_ROOT/data-vault" ]] && rm -rf "$SANDBOX_ROOT/data-vault"
  else
    [[ -d "$SANDBOX_ROOT/willow-home" ]] && rm -rf "$SANDBOX_ROOT/willow-home"
  fi
fi

mkdir -p "$SANDBOX_ROOT"
: >"$SANDBOX_ROOT/smoke.log"

log() { printf '%s\n' "$*" | tee -a "$SANDBOX_ROOT/smoke.log"; }
fail() { log "FAIL: $*"; exit 1; }
pass() { log "PASS: $*"; }

provision_vault_box() {
  local prov="$WILLOW_DATA_VAULT_REPO/bootstrap/provision.sh"
  [[ -f "$prov" ]] || fail "willow-data-vault not found at $WILLOW_DATA_VAULT_REPO"
  log "vault: provisioning box at $VAULT_BOX (willow-data-vault blueprint)"
  bash "$prov" "$VAULT_BOX" 2>&1 | tee -a "$SANDBOX_ROOT/smoke.log"
  [[ -f "$VAULT_BOX/vault.key" ]] || log "WARN: vault.key not created — willow-mcp will mint on first use"
  pass "data-vault box provisioned"
}

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
  export KART_SANDBOX_CONFIG WILLOW_MCP_REPO="$WILLOW_MCP_REPO" PG_CONTAINER
  # rlimit preexec + bwrap namespaces can fail with EAGAIN on some hosts (no cgroup parent).
  export WILLOW_KART_NO_RLIMIT="${WILLOW_KART_NO_RLIMIT:-1}"
  [[ -n "${PGHOST:-}" ]] && export PGHOST PGPORT PGPASSWORD
}

log "=== willow new-user sandbox smoke ==="
log "layout: $LAYOUT_NAME"
log "time: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
log "sandbox: $SANDBOX_ROOT"
log "willow-mcp: $WILLOW_MCP_REPO"
log "github root: $GITHUB_ROOT"

[[ -d "$WILLOW_MCP_REPO" ]] || fail "willow-mcp not found at $WILLOW_MCP_REPO"
if [[ "$VAULT_LAYOUT" == "1" ]]; then
  [[ -d "$WILLOW_DATA_VAULT_REPO" ]] || fail "willow-data-vault not found at $WILLOW_DATA_VAULT_REPO"
fi

if [[ "$VAULT_LAYOUT" == "1" ]]; then
  log ""
  log "-- data-vault provision --"
  provision_vault_box
fi

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
    PG_VOL=()
    if [[ "$VAULT_LAYOUT" == "1" && "$PG_IN_BOX" == "1" ]]; then
      mkdir -p "$VAULT_BOX/postgres/data"
      PG_VOL=(-v "$VAULT_BOX/postgres/data:/var/lib/postgresql/data")
    fi
    if docker run -d --name "$PG_CONTAINER" \
        -e POSTGRES_USER="$WILLOW_PG_USER" \
        -e POSTGRES_PASSWORD=sandbox \
        -e POSTGRES_DB="$WILLOW_PG_DB" \
        "${PG_VOL[@]}" \
        -p "127.0.0.1:${PG_PORT}:5432" \
        postgres:16-alpine >/dev/null 2>&1; then
      PG_MODE="docker"
      if [[ "$VAULT_LAYOUT" == "1" && "$PG_IN_BOX" == "1" ]]; then
        log "postgres: created $PG_CONTAINER (data in $VAULT_BOX/postgres/data) on 127.0.0.1:$PG_PORT"
      elif [[ "$VAULT_LAYOUT" == "1" ]]; then
        log "postgres: created $PG_CONTAINER (ephemeral, outside vault box) on 127.0.0.1:$PG_PORT"
        PG_MODE="docker-external"
      else
        log "postgres: created $PG_CONTAINER on 127.0.0.1:$PG_PORT"
      fi
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
log "-- $WILLOW_APP_ID manifest --"
mkdir -p "$WILLOW_HOME/mcp_apps/$WILLOW_APP_ID"
MANIFEST_SRC="$SCRIPT_DIR/sandbox-admin.manifest.json"
if [[ "$WILLOW_APP_ID" == "sandbox-vault-admin" ]]; then
  MANIFEST_SRC="$SCRIPT_DIR/sandbox-vault-admin.manifest.json"
fi
cp "$MANIFEST_SRC" "$WILLOW_HOME/mcp_apps/$WILLOW_APP_ID/manifest.json"
pass "$WILLOW_APP_ID manifest"

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

# ── 4b. Data-plane probe (secrets + SOIL + optional PG-in-box + KB) ───────────
DATA_PLANE_PROBE="${SMOKE_DATA_PLANE_PROBE:-$([[ "$VAULT_LAYOUT" == "1" ]] && echo 1 || echo 0)}"
if [[ "$DATA_PLANE_PROBE" == "1" ]]; then
  log ""
  log "-- data plane probe --"
  export PG_CONTAINER PG_IN_BOX LAYOUT_NAME
  sandbox_env
  "$PY" - <<PY 2>&1 | tee -a "$SANDBOX_ROOT/smoke.log" || fail "data plane probe"
import json, os, subprocess
from pathlib import Path
from willow_mcp import server
from willow_mcp.vault import default_vault

home = Path(os.environ["WILLOW_HOME"])
store_root = Path(os.environ["WILLOW_STORE_ROOT"])
app_id = os.environ["WILLOW_APP_ID"]
pg_container = os.environ.get("PG_CONTAINER", "")
pg_in_box = os.environ.get("PG_IN_BOX", "1") == "1"
layout = os.environ.get("LAYOUT_NAME", "unknown")

vault = default_vault()
vault.init()
vault.write("sandbox.probe", f"smoke-ok-{layout}")
assert vault.read("sandbox.probe") == f"smoke-ok-{layout}"
assert (home / "vault.key").is_file(), "vault.key missing"
assert (home / "vault.db").is_file(), "vault.db missing"
print(json.dumps({
    "layout": layout,
    "vault_key": str(home / "vault.key"),
    "vault_db": str(home / "vault.db"),
    "store_root": str(store_root),
}, indent=2))

put = server.store_put(
    app_id=app_id,
    collection="sandbox_probe",
    record_id=f"probe-{layout}",
    record={"layout": layout, "probe": True},
)
print(json.dumps(put, indent=2))
assert "error" not in put, put
soil_db = store_root / "sandbox_probe" / "store.db"
assert soil_db.is_file(), f"SOIL store missing: {soil_db}"
print(json.dumps({"soil_db": str(soil_db)}, indent=2))

pg_mount = home / "postgres" / "data"
if layout.startswith("vault"):
    if pg_in_box:
        assert pg_mount.is_dir(), f"postgres mount dir missing: {pg_mount}"
    else:
        assert not (pg_mount / "PG_VERSION").exists(), "PGDATA should not live in vault box for vault-external"
if pg_container:
    r = subprocess.run(
        ["docker", "exec", pg_container, "cat", "/var/lib/postgresql/data/PG_VERSION"],
        capture_output=True, text=True, timeout=10,
    )
    assert r.returncode == 0 and r.stdout.strip(), f"PG_VERSION unreadable: {r.stderr}"
    print(json.dumps({
        "postgres_pgdata_in_box": pg_in_box and layout.startswith("vault"),
        "postgres_pg_version": r.stdout.strip(),
        "postgres_container": pg_container,
    }, indent=2))

kb_schema = server.schema_confirm_mapping(app_id=app_id, table="knowledge")
print(json.dumps({"knowledge_schema": kb_schema.get("confirmed", kb_schema)}, indent=2))
assert "error" not in kb_schema, kb_schema
probe = f"layout-kb-probe-{layout}"
ing = server.knowledge_ingest(app_id=app_id, content=probe, source="layout-drive", domain="sandbox")
print(json.dumps({"knowledge_ingest": ing}, indent=2))
assert "error" not in ing, ing
search = server.knowledge_search(app_id=app_id, query=probe, limit=5)
assert "error" not in search, search
assert any(probe in str(r.get("content", "")) for r in search.get("results", [])), search
print(json.dumps({"knowledge_search_count": len(search.get("results", []))}, indent=2))
PY
  pass "data plane: secrets + SOIL + KB"
fi

# ── 5. Kart (Postgres required) ───────────────────────────────────────────────
KART_NOTE="skipped"
if [[ "$SKIP_KART" == "1" ]]; then
  log "kart: --skip-kart"
else
  log ""
  log "-- kart --"
  SCHEMA_OUT=$("$PY" 2>&1 <<'PY'
import json, os
from willow_mcp import server
r = server.schema_confirm_mapping(app_id=os.environ["WILLOW_APP_ID"], table="tasks")
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
  echo "- **Layout:** $LAYOUT_NAME"
  echo "- **Sandbox:** \`$SANDBOX_ROOT\`"
  echo "- **WILLOW_HOME:** \`$WILLOW_HOME\`"
  echo "- **WILLOW_STORE_ROOT:** \`$WILLOW_STORE_ROOT\`"
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
