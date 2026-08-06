#!/usr/bin/env bash
# Install compiled manifests from governance/materialized-mcp-apps/ into
# $WILLOW_HOME/mcp_apps/. Requires write access (see below if denied).
set -euo pipefail
WILLOW_HOME="${WILLOW_HOME:-$HOME/github/.willow}"
SRC="$(cd "$(dirname "$0")/.." && pwd)/materialized-mcp-apps"
if [[ ! -d "$SRC" ]]; then
  echo "missing $SRC — regenerate from willow repo first" >&2
  exit 1
fi
DEST="$WILLOW_HOME/mcp_apps"
install_one() {
  local name="$1"
  install -D -m 664 "$SRC/$name/manifest.json" "$DEST/$name/manifest.json"
  echo "installed $name"
}
if ! test -w "$DEST" 2>/dev/null && ! test -w "$DEST/hanuman/manifest.json" 2>/dev/null; then
  if command -v sudo >/dev/null && sudo -n true 2>/dev/null; then
    echo "mcp_apps not writable as $USER — installing as willow-operator via sudo"
    for agent in "$SRC"/*/; do
      name="$(basename "$agent")"
      sudo -u willow-operator install -D -m 664 "$agent/manifest.json" "$DEST/$name/manifest.json"
      echo "installed $name (willow-operator)"
    done
  else
    cat >&2 <<EOF
Cannot write to $DEST (owned by willow-operator).

Fix once (pick one):
  A) Take ownership (recommended for your login):
     sudo chown -R "\$USER":willow-operator "$DEST"

  B) Refresh group membership, then re-run this script:
     newgrp willow-operator

  C) Install as willow-operator (enter sudo password):
     sudo -u willow-operator $0

Then reload Cursor MCP.
EOF
    exit 1
  fi
else
  for agent in "$SRC"/*/; do
    install_one "$(basename "$agent")"
  done
fi
echo "Done. Reload Cursor MCP (or restart willow-mcp) so seats pick up manifests."
