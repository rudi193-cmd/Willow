#!/usr/bin/env bash
# Willow Daemon Launcher (WSL/Linux)
# Equivalent of start_daemons.bat — launches background daemons server.py doesn't own.
# Pigeon + OCR Consumer are owned by server.py — do NOT launch them here.
#
# Usage: ./start_daemons.sh [--kill-first]
# ΔΣ=42

set -euo pipefail
WILLOW_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="${WILLOW_VENV:-/home/sean/.willow-venv}/bin/python"

if [ ! -f "$PYTHON" ]; then
    PYTHON="python3"
fi

# Optional: kill stale daemons first
if [[ "${1:-}" == "--kill-first" ]]; then
    echo "[*] Killing stale daemons..."
    for script in monitor.py coherence_scanner.py topology_builder.py compost.py safe_sync.py persona_scheduler.py pulse.py; do
        pkill -f "$script" 2>/dev/null || true
    done
    sleep 1
fi

echo "========================================"
echo " Willow AIOS — Daemon Launcher (WSL)"
echo "========================================"
echo ""

# 1. Governance Monitor (every 60s) — monitor.py doesn't exist yet, skip
if [ -f "$WILLOW_DIR/governance/monitor.py" ]; then
    echo "[1/7] Governance Monitor..."
    nohup "$PYTHON" "$WILLOW_DIR/governance/monitor.py" --interval 60 --daemon \
        >> "$WILLOW_DIR/governance/monitor.log" 2>&1 &
    echo "      PID=$!"
else
    echo "[1/7] Governance Monitor... SKIPPED (monitor.py not found)"
fi

# 2. Coherence Scanner (every 1h)
echo "[2/7] Coherence Scanner..."
nohup "$PYTHON" "$WILLOW_DIR/core/coherence_scanner.py" --interval 3600 --daemon \
    >> "$WILLOW_DIR/core/coherence_scan.log" 2>&1 &
echo "      PID=$!"

# 3. Topology Builder (every 1h)
echo "[3/7] Topology Builder..."
nohup "$PYTHON" "$WILLOW_DIR/core/topology_builder.py" --interval 3600 --daemon \
    >> "$WILLOW_DIR/core/topology_build.log" 2>&1 &
echo "      PID=$!"

# 4. Compost (every 24h)
echo "[4/7] Compost..."
nohup "$PYTHON" "$WILLOW_DIR/core/compost.py" --interval 86400 --daemon \
    >> "$WILLOW_DIR/core/compaction.log" 2>&1 &
echo "      PID=$!"

# 5. SAFE Sync (every 5m)
echo "[5/7] SAFE Sync..."
nohup "$PYTHON" "$WILLOW_DIR/core/safe_sync.py" --interval 300 --daemon \
    >> "$WILLOW_DIR/core/safe_sync.log" 2>&1 &
echo "      PID=$!"

# 6. Persona Scheduler (every 60s)
echo "[6/7] Persona Scheduler..."
nohup "$PYTHON" "$WILLOW_DIR/core/persona_scheduler.py" --interval 60 --daemon \
    >> "$WILLOW_DIR/core/persona_scheduler.log" 2>&1 &
echo "      PID=$!"

# 7. Pulse / Kart daemon (30s poll)
echo "[7/7] Pulse (Kart daemon)..."
nohup "$PYTHON" "$WILLOW_DIR/core/pulse.py" --daemon \
    >> "$WILLOW_DIR/core/pulse.log" 2>&1 &
echo "      PID=$!"

echo ""
echo "========================================"
echo " Daemons launched. Pigeon + OCR owned by server.py."
echo "========================================"
echo ""
echo "Logs:"
echo "  governance/monitor.log"
echo "  core/coherence_scan.log"
echo "  core/topology_build.log"
echo "  core/compaction.log"
echo "  core/safe_sync.log"
echo "  core/persona_scheduler.log"
echo "  core/pulse.log"
echo ""
echo "To stop: pkill -f 'coherence_scanner\|topology_builder\|compost\|safe_sync\|persona_scheduler\|pulse'"
