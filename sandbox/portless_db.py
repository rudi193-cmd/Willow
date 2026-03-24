"""
portless_db.py — Portless Server Architecture
Based on Sean's design from 2026-03-19.

Service listens on filesystem, not network.
Translation layer (MCP, CF Worker) handles external interface when needed.
Core logic stays air-gapped.

Key differences from folderdb.py:
- SQLite per collection (not JSON files) — atomic writes, ACID
- Angular deviation rubric built into write path
- Governance: AI proposes, human ratifies
- .cache and .archive directories for lifecycle
- No network ports. No daemons. Scripts only.
"""

import json
import math
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path


# ── Angular Deviation Rubric v2.0 ─────────────────────────────────────

PI4 = math.pi / 4   # 45°
PI2 = math.pi / 2   # 90°
PI  = math.pi        # 180°

def angular_action(deviation: float) -> str:
    """Determine action based on signed angular deviation."""
    mag = abs(deviation)
    if mag < PI4:
        return "work_quiet"
    elif mag < PI2:
        return "flag"
    else:
        return "stop"

def net_trajectory(deviations: list[float]) -> tuple[float, str]:
    """Weighted sum of recent deviations. Returns (score, interpretation)."""
    if not deviations:
        return 0.0, "stable"
    weights = {PI4: 0.25, PI2: 0.5, PI: 1.0}
    total = 0.0
    for d in deviations:
        mag = abs(d)
        if mag >= PI2:
            w = 1.0
        elif mag >= PI4:
            w = 0.5
        else:
            w = 0.25
        total += d * w
    avg = total / len(deviations)
    if avg > PI4:
        return avg, "improving"
    elif avg < -PI4:
        return avg, "degrading"
    return avg, "stable"


# ── PortlessDB ─────────────────────────────────────────────────────────

class PortlessDB:
    def __init__(self, root: str):
        self.root = Path(root)
        self._connections = {}

    def _sanitize(self, name: str) -> str:
        """Strip path traversal and shell metacharacters."""
        clean = "".join(c for c in name if c.isalnum() or c in "/_-.")
        clean = clean.replace("..", "").strip("/.")
        return clean

    def _db_path(self, collection: str) -> Path:
        """Each collection is a SQLite DB file."""
        clean = self._sanitize(collection)
        p = self.root / clean
        p.mkdir(parents=True, exist_ok=True)
        return p / "store.db"

    def _conn(self, collection: str) -> sqlite3.Connection:
        """Get or create connection for a collection."""
        key = self._sanitize(collection)
        if key not in self._connections:
            db_path = self._db_path(collection)
            conn = sqlite3.connect(str(db_path))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS records (
                    id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted INTEGER DEFAULT 0,
                    deviation REAL DEFAULT 0.0,
                    action TEXT DEFAULT 'work_quiet'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    deviation REAL,
                    action TEXT,
                    timestamp TEXT NOT NULL
                )
            """)
            conn.commit()
            self._connections[key] = conn
        return self._connections[key]

    def _resolve_path(self, path: str) -> Path:
        """Resolve and validate path stays within root."""
        resolved = (self.root / self._sanitize(path)).resolve()
        if not str(resolved).startswith(str(self.root.resolve())):
            raise ValueError(f"Path escape attempt: {path}")
        return resolved

    # ── Write ──────────────────────────────────────────────────────────

    def put(self, collection: str, record: dict, record_id: str = None,
            deviation: float = 0.0) -> tuple[str, str]:
        """
        Write a record. Returns (record_id, action).
        Action comes from angular deviation rubric:
          work_quiet = minor change, proceed
          flag = significant change, log prominently
          stop = major change, requires ratification
        """
        rid = self._sanitize(record_id) if record_id else uuid.uuid4().hex[:8]
        action = angular_action(deviation)

        # Size limit: 100KB per record
        data = json.dumps(record, default=str)
        if len(data) > 100_000:
            raise ValueError(f"Record too large: {len(data)} bytes (max 100KB)")

        # Check for ID collision — append-only by default
        conn = self._conn(collection)
        existing = conn.execute(
            "SELECT id FROM records WHERE id = ? AND deleted = 0", (rid,)
        ).fetchone()
        if existing:
            raise ValueError(f"Record {rid} already exists. Use update() to modify.")

        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO records (id, data, created_at, updated_at, deviation, action) VALUES (?, ?, ?, ?, ?, ?)",
            (rid, data, now, now, deviation, action)
        )
        conn.execute(
            "INSERT INTO audit_log (record_id, operation, deviation, action, timestamp) VALUES (?, 'create', ?, ?, ?)",
            (rid, deviation, action, now)
        )
        conn.commit()
        return rid, action

    def update(self, collection: str, record_id: str, record: dict,
               deviation: float = 0.0) -> tuple[str, str]:
        """Update existing record. Logs to audit trail."""
        rid = self._sanitize(record_id)
        action = angular_action(deviation)

        data = json.dumps(record, default=str)
        if len(data) > 100_000:
            raise ValueError(f"Record too large: {len(data)} bytes (max 100KB)")

        conn = self._conn(collection)
        now = datetime.now().isoformat()
        result = conn.execute(
            "UPDATE records SET data = ?, updated_at = ?, deviation = ?, action = ? WHERE id = ? AND deleted = 0",
            (data, now, deviation, action, rid)
        )
        if result.rowcount == 0:
            raise ValueError(f"Record {rid} not found or deleted.")

        conn.execute(
            "INSERT INTO audit_log (record_id, operation, deviation, action, timestamp) VALUES (?, 'update', ?, ?, ?)",
            (rid, deviation, action, now)
        )
        conn.commit()
        return rid, action

    # ── Read ───────────────────────────────────────────────────────────

    def get(self, collection: str, record_id: str) -> dict | None:
        """Read a single record."""
        conn = self._conn(collection)
        row = conn.execute(
            "SELECT data, created_at, updated_at, deviation, action FROM records WHERE id = ? AND deleted = 0",
            (self._sanitize(record_id),)
        ).fetchone()
        if not row:
            return None
        record = json.loads(row[0])
        record["_id"] = record_id
        record["_created"] = row[1]
        record["_updated"] = row[2]
        record["_deviation"] = row[3]
        record["_action"] = row[4]
        return record

    def all(self, collection: str) -> list[dict]:
        """Read all non-deleted records."""
        conn = self._conn(collection)
        rows = conn.execute(
            "SELECT id, data, created_at, updated_at, deviation, action FROM records WHERE deleted = 0 ORDER BY created_at"
        ).fetchall()
        results = []
        for row in rows:
            record = json.loads(row[1])
            record["_id"] = row[0]
            record["_created"] = row[2]
            record["_updated"] = row[3]
            record["_deviation"] = row[4]
            record["_action"] = row[5]
            results.append(record)
        return results

    def list_ids(self, collection: str) -> list[str]:
        """List all active record IDs."""
        conn = self._conn(collection)
        return [r[0] for r in conn.execute(
            "SELECT id FROM records WHERE deleted = 0"
        ).fetchall()]

    # ── Search ─────────────────────────────────────────────────────────

    def search(self, collection: str, query: str) -> list[dict]:
        """Text search within a collection."""
        conn = self._conn(collection)
        rows = conn.execute(
            "SELECT id, data, deviation, action FROM records WHERE deleted = 0 AND data LIKE ?",
            (f"%{query}%",)
        ).fetchall()
        results = []
        for row in rows:
            record = json.loads(row[1])
            record["_id"] = row[0]
            record["_deviation"] = row[2]
            record["_action"] = row[3]
            results.append(record)
        return results

    # ── Delete ─────────────────────────────────────────────────────────

    def delete(self, collection: str, record_id: str) -> bool:
        """Soft delete with audit trail."""
        conn = self._conn(collection)
        now = datetime.now().isoformat()
        result = conn.execute(
            "UPDATE records SET deleted = 1, updated_at = ? WHERE id = ? AND deleted = 0",
            (now, self._sanitize(record_id))
        )
        if result.rowcount == 0:
            return False
        conn.execute(
            "INSERT INTO audit_log (record_id, operation, timestamp) VALUES (?, 'delete', ?)",
            (record_id, now)
        )
        conn.commit()
        return True

    # ── Edges ──────────────────────────────────────────────────────────

    def add_edge(self, from_id: str, to_id: str, relation: str, context: str = ""):
        edge_id = f"{self._sanitize(from_id)}_{self._sanitize(to_id)}_{self._sanitize(relation)}"
        return self.put("knowledge/edges", {
            "from": from_id, "to": to_id,
            "relation": relation, "context": context,
        }, record_id=edge_id)

    def edges_for(self, record_id: str) -> list[dict]:
        results = self.search("knowledge/edges", record_id)
        return [r for r in results if r.get("from") == record_id or r.get("to") == record_id]

    # ── Audit ──────────────────────────────────────────────────────────

    def audit_log(self, collection: str, limit: int = 20) -> list[dict]:
        """Read recent audit entries."""
        conn = self._conn(collection)
        rows = conn.execute(
            "SELECT record_id, operation, deviation, action, timestamp FROM audit_log ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [{"record_id": r[0], "operation": r[1], "deviation": r[2],
                 "action": r[3], "timestamp": r[4]} for r in rows]

    # ── Stats ──────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Collection counts and trajectory."""
        result = {}
        for db_file in sorted(self.root.rglob("store.db")):
            col = str(db_file.parent.relative_to(self.root))
            try:
                conn = sqlite3.connect(str(db_file))
                count = conn.execute("SELECT COUNT(*) FROM records WHERE deleted = 0").fetchone()[0]
                devs = [r[0] for r in conn.execute(
                    "SELECT deviation FROM records WHERE deleted = 0 AND deviation != 0"
                ).fetchall()]
                traj_score, traj_label = net_trajectory(devs)
                result[col] = {"count": count, "trajectory": traj_label, "score": round(traj_score, 3)}
                conn.close()
            except Exception:
                continue
        return result

    def close(self):
        for conn in self._connections.values():
            conn.close()
        self._connections.clear()
