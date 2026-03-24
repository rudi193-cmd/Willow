"""
folderdb.py — Folder-based database for Willow
Each collection is a directory. Each record is a JSON file.
The knowledge graph is the directory structure + index files.
No Postgres. No SQLite. No server. Just files.
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path


class FolderDB:
    def __init__(self, root: str):
        self.root = Path(root)

    def _collection(self, name: str) -> Path:
        p = self.root / name
        p.mkdir(parents=True, exist_ok=True)
        return p

    # ── Write ──────────────────────────────────────────────────────────

    def put(self, collection: str, record: dict, record_id: str = None) -> str:
        """Write a record to a collection. Returns the record ID."""
        rid = record_id or uuid.uuid4().hex[:8]
        record["_id"] = rid
        record["_created"] = record.get("_created", datetime.now().isoformat())
        record["_updated"] = datetime.now().isoformat()

        path = self._collection(collection) / f"{rid}.json"
        path.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
        return rid

    # ── Read ───────────────────────────────────────────────────────────

    def get(self, collection: str, record_id: str) -> dict | None:
        """Read a single record by ID."""
        path = self._collection(collection) / f"{record_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list_ids(self, collection: str) -> list[str]:
        """List all record IDs in a collection."""
        col = self._collection(collection)
        return [p.stem for p in col.glob("*.json")]

    def all(self, collection: str) -> list[dict]:
        """Read all records in a collection."""
        col = self._collection(collection)
        records = []
        for p in sorted(col.glob("*.json")):
            try:
                records.append(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                continue
        return records

    # ── Search ─────────────────────────────────────────────────────────

    def search(self, collection: str, query: str, fields: list[str] = None) -> list[dict]:
        """Simple text search across records. Case-insensitive."""
        q = query.lower()
        fields = fields or ["title", "content", "name", "description", "summary"]
        results = []
        for record in self.all(collection):
            for f in fields:
                val = record.get(f, "")
                if isinstance(val, str) and q in val.lower():
                    results.append(record)
                    break
        return results

    def search_all(self, query: str) -> list[dict]:
        """Search across all collections."""
        results = []
        for col_dir in self.root.iterdir():
            if col_dir.is_dir() and not col_dir.name.startswith("."):
                for record in self.search(col_dir.name, query):
                    record["_collection"] = col_dir.name
                    results.append(record)
                # Also search subdirectories (knowledge/atoms, etc.)
                for sub in col_dir.iterdir():
                    if sub.is_dir() and not sub.name.startswith("."):
                        rel = f"{col_dir.name}/{sub.name}"
                        for record in self.search(rel, query):
                            record["_collection"] = rel
                            results.append(record)
        return results

    # ── Delete ─────────────────────────────────────────────────────────

    def delete(self, collection: str, record_id: str) -> bool:
        """Soft delete — moves to .deleted/ subfolder."""
        src = self._collection(collection) / f"{record_id}.json"
        if not src.exists():
            return False
        deleted_dir = self._collection(collection) / ".deleted"
        deleted_dir.mkdir(exist_ok=True)
        src.rename(deleted_dir / f"{record_id}.json")
        return True

    # ── Edges (knowledge graph) ────────────────────────────────────────

    def add_edge(self, from_id: str, to_id: str, relation: str, context: str = ""):
        """Add an edge to the knowledge graph."""
        edge_id = f"{from_id}_{to_id}_{relation}"
        return self.put("knowledge/edges", {
            "from": from_id,
            "to": to_id,
            "relation": relation,
            "context": context,
        }, record_id=edge_id)

    def edges_for(self, record_id: str) -> list[dict]:
        """Get all edges involving a record."""
        all_edges = self.all("knowledge/edges")
        return [e for e in all_edges if e.get("from") == record_id or e.get("to") == record_id]

    # ── Stats ──────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Collection counts."""
        result = {}
        for col_dir in sorted(self.root.rglob("*")):
            if col_dir.is_dir() and not any(p.startswith(".") for p in col_dir.relative_to(self.root).parts):
                jsons = list(col_dir.glob("*.json"))
                if jsons:
                    rel = str(col_dir.relative_to(self.root))
                    result[rel] = len(jsons)
        return result
