"""
willow_store.py — Portless Willow Storage (Merged)
Sean's portless architecture + Ganesha's security hardening.

Service listens on filesystem, not network.
Core logic stays air-gapped.
Translation layer (MCP, CF Worker) handles external when needed.

SQLite per collection (ACID, atomic writes).
Angular deviation rubric governs all writes.
Append-only by default. Audit trail on every operation.
Path sanitization prevents escape. Size limits prevent DoS.
JSON export for human-readable debug.
"""

import json
import math
import os
import re
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path


# ── Angular Deviation Rubric v2.0 ─────────────────────────────────────

PI4 = math.pi / 4   # 45°
PI2 = math.pi / 2   # 90°
PI  = math.pi        # 180°

MAX_RECORD_BYTES = 100_000  # 100KB per record


def angular_action(deviation: float) -> str:
    """Determine action based on signed angular deviation.
    work_quiet: minor change, proceed silently
    flag: significant change, log prominently
    stop: major change, requires ratification before proceeding
    """
    mag = abs(deviation)
    if mag < PI4:
        return "work_quiet"
    elif mag < PI2:
        return "flag"
    return "stop"


def net_trajectory(deviations: list[float]) -> tuple[float, str]:
    """Weighted sum of recent deviations → (score, interpretation)."""
    if not deviations:
        return 0.0, "stable"
    total = 0.0
    for d in deviations:
        mag = abs(d)
        w = 1.0 if mag >= PI2 else (0.5 if mag >= PI4 else 0.25)
        total += d * w
    avg = total / len(deviations)
    if avg > PI4:
        return avg, "improving"
    elif avg < -PI4:
        return avg, "degrading"
    return avg, "stable"


# ── Path Security ──────────────────────────────────────────────────────

_SAFE_PATTERN = re.compile(r'^[a-zA-Z0-9_/\-]+$')


def _sanitize_name(name: str) -> str:
    """Strip anything that isn't alphanumeric, underscore, hyphen, or slash."""
    clean = "".join(c for c in name if c.isalnum() or c in "/_-")
    # Collapse multiple slashes, strip leading/trailing
    while "//" in clean:
        clean = clean.replace("//", "/")
    clean = clean.strip("/")
    # Remove any .. traversal
    parts = [p for p in clean.split("/") if p and p != ".."]
    return "/".join(parts)


def _sanitize_id(record_id: str) -> str:
    """Record IDs: alphanumeric, underscore, hyphen only. No slashes."""
    return "".join(c for c in record_id if c.isalnum() or c in "_-")


# ── WillowStore ────────────────────────────────────────────────────────

class WillowStore:
    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self._connections = {}

    def _validate_path(self, collection: str) -> Path:
        """Resolve collection path. Reject if outside root."""
        clean = _sanitize_name(collection)
        if not clean:
            raise ValueError(f"Invalid collection name: {collection}")
        target = (self.root / clean).resolve()
        if not str(target).startswith(str(self.root)):
            raise ValueError(f"Path escape blocked: {collection}")
        # Reject symlinks
        if target.exists() and target.is_symlink():
            raise ValueError(f"Symlink blocked: {collection}")
        return target

    def _db_path(self, collection: str) -> Path:
        """Each collection is a directory with a store.db."""
        target = self._validate_path(collection)
        target.mkdir(parents=True, exist_ok=True)
        return target / "store.db"

    def _conn(self, collection: str) -> sqlite3.Connection:
        """Get or create connection. Thread-safe."""
        key = _sanitize_name(collection)
        if key not in self._connections:
            db_path = self._db_path(collection)
            conn = sqlite3.connect(str(db_path), check_same_thread=False)
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

    # ── Write ──────────────────────────────────────────────────────────

    def put(self, collection: str, record: dict, record_id: str = None,
            deviation: float = 0.0) -> tuple[str, str]:
        """
        Write a record. Returns (record_id, action).
        Append-only: raises if ID already exists. Use update() to modify.
        """
        rid = _sanitize_id(record_id) if record_id else uuid.uuid4().hex[:8]
        if not rid:
            raise ValueError("Invalid record ID after sanitization")

        action = angular_action(deviation)
        data = json.dumps(record, default=str)

        if len(data) > MAX_RECORD_BYTES:
            raise ValueError(f"Record too large: {len(data)} bytes (max {MAX_RECORD_BYTES})")

        conn = self._conn(collection)
        existing = conn.execute(
            "SELECT id FROM records WHERE id = ? AND deleted = 0", (rid,)
        ).fetchone()
        if existing:
            raise ValueError(f"Record '{rid}' exists. Use update() to modify.")

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
        """Update existing record. Audit-trailed."""
        rid = _sanitize_id(record_id)
        action = angular_action(deviation)
        data = json.dumps(record, default=str)

        if len(data) > MAX_RECORD_BYTES:
            raise ValueError(f"Record too large: {len(data)} bytes (max {MAX_RECORD_BYTES})")

        conn = self._conn(collection)
        now = datetime.now().isoformat()
        result = conn.execute(
            "UPDATE records SET data = ?, updated_at = ?, deviation = ?, action = ? WHERE id = ? AND deleted = 0",
            (data, now, deviation, action, rid)
        )
        if result.rowcount == 0:
            raise ValueError(f"Record '{rid}' not found or deleted.")

        conn.execute(
            "INSERT INTO audit_log (record_id, operation, deviation, action, timestamp) VALUES (?, 'update', ?, ?, ?)",
            (rid, deviation, action, now)
        )
        conn.commit()
        return rid, action

    # ── Read ───────────────────────────────────────────────────────────

    def get(self, collection: str, record_id: str) -> dict | None:
        """Read a single record by ID."""
        conn = self._conn(collection)
        row = conn.execute(
            "SELECT data, created_at, updated_at, deviation, action FROM records WHERE id = ? AND deleted = 0",
            (_sanitize_id(record_id),)
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
        conn = self._conn(collection)
        return [r[0] for r in conn.execute(
            "SELECT id FROM records WHERE deleted = 0"
        ).fetchall()]

    # ── Search ─────────────────────────────────────────────────────────

    def search(self, collection: str, query: str) -> list[dict]:
        """Text search within a collection (SQL LIKE)."""
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

    def search_all(self, query: str) -> list[dict]:
        """Search across ALL collections. The 'go ask Willow' pattern."""
        results = []
        for db_file in sorted(self.root.rglob("store.db")):
            col = str(db_file.parent.relative_to(self.root))
            if col.startswith("."):
                continue
            for record in self.search(col, query):
                record["_collection"] = col
                results.append(record)
        return results

    # ── Delete ─────────────────────────────────────────────────────────

    def delete(self, collection: str, record_id: str) -> bool:
        """Soft delete with audit trail. Invisible to search/get/all."""
        conn = self._conn(collection)
        rid = _sanitize_id(record_id)
        now = datetime.now().isoformat()
        result = conn.execute(
            "UPDATE records SET deleted = 1, updated_at = ? WHERE id = ? AND deleted = 0",
            (now, rid)
        )
        if result.rowcount == 0:
            return False
        conn.execute(
            "INSERT INTO audit_log (record_id, operation, timestamp) VALUES (?, 'delete', ?)",
            (rid, now)
        )
        conn.commit()
        return True

    # ── Edges ──────────────────────────────────────────────────────────

    def add_edge(self, from_id: str, to_id: str, relation: str, context: str = ""):
        """Add an edge to the knowledge graph."""
        edge_id = f"{_sanitize_id(from_id)}_{_sanitize_id(to_id)}_{_sanitize_id(relation)}"
        return self.put("knowledge/edges", {
            "from": from_id, "to": to_id,
            "relation": relation, "context": context,
        }, record_id=edge_id)

    def edges_for(self, record_id: str) -> list[dict]:
        """Get all edges involving a record."""
        return [r for r in self.search("knowledge/edges", record_id)
                if r.get("from") == record_id or r.get("to") == record_id]

    # ── Audit ──────────────────────────────────────────────────────────

    def audit_log(self, collection: str, limit: int = 20) -> list[dict]:
        conn = self._conn(collection)
        rows = conn.execute(
            "SELECT record_id, operation, deviation, action, timestamp FROM audit_log ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [{"record_id": r[0], "operation": r[1], "deviation": r[2],
                 "action": r[3], "timestamp": r[4]} for r in rows]

    # ── Export (human-readable debug) ──────────────────────────────────

    def export_json(self, collection: str, output_dir: str = None) -> str:
        """Export a collection to JSON for human inspection."""
        records = self.all(collection)
        out = Path(output_dir) if output_dir else self._validate_path(collection)
        out.mkdir(parents=True, exist_ok=True)
        export_path = out / "export.json"
        export_path.write_text(json.dumps(records, indent=2, default=str), encoding="utf-8")
        return str(export_path)

    # ── Stats ──────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Collection counts and trajectory."""
        result = {}
        for db_file in sorted(self.root.rglob("store.db")):
            if any(p.startswith(".") for p in db_file.relative_to(self.root).parts):
                continue
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
