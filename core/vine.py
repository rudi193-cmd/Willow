# DS=42
import json
import sys
from datetime import datetime
from pathlib import Path
from difflib import SequenceMatcher
from collections import defaultdict

PROMOTION_THRESHOLD = 5
FALLBACK_USER = "Sweet-Pea-Rudi19"


class RelationshipTracker:
    def __init__(self, username: str, db_path: str = None):
        self.username = username
        self.promotion_threshold = PROMOTION_THRESHOLD
        if db_path:
            self.db_path = Path(db_path)
        else:
            base = Path(__file__).parent.parent / "artifacts"
            user_db = base / username / "willow_knowledge.db"
            fallback_db = base / FALLBACK_USER / "willow_knowledge.db"
            self.db_path = user_db if user_db.exists() else fallback_db
        try:
            from core.db import get_connection as _gc
            self.conn = _gc()
            self._init_schema()
        except Exception as e:
            print(f"[RelationshipTracker] DB connect error: {e}", file=sys.stderr)
            self.conn = None

    def _ts(self) -> str:
        return datetime.now().isoformat() + "Z"

    def _row(self, r) -> dict:
        return dict(r) if r else None

    def _init_schema(self):
        return  # schema managed by pg_schema.sql
        c = self.conn.cursor()

        # V2: all entity columns defined in initial CREATE TABLE
        c.execute("""CREATE TABLE IF NOT EXISTS entities (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            name              TEXT NOT NULL UNIQUE,
            entity_type       TEXT NOT NULL,
            description       TEXT,
            mention_count     INTEGER DEFAULT 1,
            layer             INTEGER DEFAULT 1,
            reference_string  TEXT,
            first_seen        TEXT,
            last_mentioned    TEXT,
            mention_contexts  TEXT,
            emotional_valence REAL DEFAULT 0.0,
            promotion_status  TEXT DEFAULT 'untracked',
            never_promote     INTEGER DEFAULT 0,
            username          TEXT,
            promoted_from     INTEGER,
            domain            TEXT DEFAULT 'world'
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS entity_connections (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_a_id     INTEGER,
            entity_b_id     INTEGER,
            connection_type TEXT,
            weight          REAL DEFAULT 1.0,
            source          TEXT,
            created_at      TEXT,
            confirmed       INTEGER DEFAULT 0,
            UNIQUE(entity_a_id, entity_b_id, connection_type)
        )""")

        c.execute("""CREATE TABLE IF NOT EXISTS anonymous_mentions (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            username  TEXT,
            category  TEXT,
            count     INTEGER DEFAULT 0,
            last_seen TEXT,
            UNIQUE(username, category)
        )""")

        c.execute("CREATE INDEX IF NOT EXISTS idx_entity_connections_confirmed ON entity_connections(confirmed, entity_a_id)")

        self.conn.commit()

    def close(self):
        """Return the pool connection. Safe to call multiple times."""
        if getattr(self, "conn", None) is not None:
            self.conn.close()
            self.conn = None

    def __del__(self):
        self.close()

    def record_anonymous_mention(self, context: str, category: str = "unknown") -> int:
        if not self.conn:
            return 0
        try:
            c = self.conn.cursor()
            c.execute(
                "INSERT OR IGNORE INTO anonymous_mentions (username, category, count, last_seen) VALUES (?, ?, 0, ?)",
                (self.username, category, self._ts()),
            )
            c.execute(
                "UPDATE anonymous_mentions SET count = count + 1, last_seen = ? WHERE username = ? AND category = ?",
                (self._ts(), self.username, category),
            )
            self.conn.commit()
            row = c.execute(
                "SELECT count FROM anonymous_mentions WHERE username = ? AND category = ?",
                (self.username, category),
            ).fetchone()
            return row["count"] if row else 0
        except Exception as e:
            print(f"[record_anonymous_mention] {e}", file=sys.stderr)
            return 0

    def record_reference(
        self,
        reference_string: str,
        context: str,
        emotional_valence: float = 0.0,
        entity_type: str = "person",
    ) -> dict:
        if not self.conn:
            return {}
        try:
            c = self.conn.cursor()
            row = c.execute(
                "SELECT * FROM entities WHERE reference_string = ? AND username = ? AND layer = 2",
                (reference_string, self.username),
            ).fetchone()
            now = self._ts()
            if row is None:
                c.execute(
                    """INSERT INTO entities
                       (name, entity_type, description, mention_count, layer, reference_string,
                        first_seen, last_mentioned, mention_contexts, emotional_valence,
                        promotion_status, never_promote, username)
                       VALUES (?, ?, '', 1, 2, ?, ?, ?, ?, ?, 'untracked', 0, ?)""",
                    (
                        reference_string, entity_type, reference_string, now, now,
                        json.dumps([context]), emotional_valence, self.username,
                    ),
                )
                self.conn.commit()
                eid = c.lastrowid
            else:
                eid = row["id"]
                contexts = json.loads(row["mention_contexts"] or "[]")
                contexts.append(context)
                contexts = contexts[-10:]
                old_count = row["mention_count"] or 0
                avg_val = ((row["emotional_valence"] or 0.0) * old_count + emotional_valence) / (old_count + 1)
                new_count = old_count + 1
                if row["never_promote"]:
                    status = "never"
                elif new_count >= self.promotion_threshold:
                    status = "eligible"
                else:
                    status = row["promotion_status"] or "untracked"
                c.execute(
                    """UPDATE entities SET mention_count=?, last_mentioned=?,
                       mention_contexts=?, emotional_valence=?, promotion_status=?
                       WHERE id=?""",
                    (new_count, now, json.dumps(contexts), avg_val, status, eid),
                )
                self.conn.commit()
            return self.get_entity(eid) or {}
        except Exception as e:
            print(f"[record_reference] {e}", file=sys.stderr)
            return {}

    def promote_to_named(
        self,
        reference_id: int,
        confirmed_name: str,
        entity_type: str,
        relationship_type: str = None,
    ) -> dict:
        if not self.conn:
            return {}
        try:
            c = self.conn.cursor()
            old = c.execute("SELECT * FROM entities WHERE id=?", (reference_id,)).fetchone()
            if not old:
                return {}
            now = self._ts()
            c.execute(
                """INSERT INTO entities
                   (name, entity_type, description, mention_count, layer, first_seen,
                    last_mentioned, promotion_status, username, promoted_from, emotional_valence)
                   VALUES (?, ?, ?, ?, 3, ?, ?, 'promoted', ?, ?, ?)""",
                (
                    confirmed_name, entity_type, old["description"] or "",
                    old["mention_count"] or 0, old["first_seen"] or now, now,
                    self.username, reference_id, old["emotional_valence"] or 0.0,
                ),
            )
            self.conn.commit()
            new_id = c.lastrowid
            c.execute("UPDATE entities SET promotion_status='promoted' WHERE id=?", (reference_id,))
            ke_rows = c.execute(
                "SELECT knowledge_id FROM knowledge_entities WHERE entity_id=?", (reference_id,)
            ).fetchall()
            for kr in ke_rows:
                try:
                    c.execute(
                        "INSERT OR IGNORE INTO knowledge_entities (knowledge_id, entity_id) VALUES (?, ?)",
                        (kr["knowledge_id"], new_id),
                    )
                except Exception:
                    pass
            self.conn.commit()
            return self.get_entity(new_id) or {}
        except Exception as e:
            print(f"[promote_to_named] {e}", file=sys.stderr)
            return {}

    def dismiss_promotion(self, reference_id: int, never: bool = False) -> bool:
        if not self.conn:
            return False
        try:
            c = self.conn.cursor()
            if never:
                c.execute(
                    "UPDATE entities SET promotion_status='never', never_promote=1 WHERE id=?",
                    (reference_id,),
                )
            else:
                c.execute(
                    "UPDATE entities SET promotion_status='untracked', mention_count=0 WHERE id=?",
                    (reference_id,),
                )
            self.conn.commit()
            return True
        except Exception as e:
            print(f"[dismiss_promotion] {e}", file=sys.stderr)
            return False

    def record_connection(
        self,
        entity_a_id: int,
        entity_b_id: int,
        connection_type: str,
        weight: float = 1.0,
        source: str = None,
    ) -> dict:
        if not self.conn:
            return {}
        try:
            c = self.conn.cursor()
            # INSERT OR IGNORE: db.py translates to ON CONFLICT DO NOTHING on PostgreSQL.
            # No exception raised on duplicates — no transaction poisoning — no flood.
            c.execute(
                """INSERT OR IGNORE INTO entity_connections
                   (entity_a_id, entity_b_id, connection_type, weight, source, created_at, confirmed)
                   VALUES (?, ?, ?, ?, ?, ?, 0)""",
                (entity_a_id, entity_b_id, connection_type, weight, source, self._ts()),
            )
            if c.rowcount == 0:
                # Row already existed — update weight as running average
                row = c.execute(
                    """SELECT weight FROM entity_connections
                       WHERE entity_a_id=? AND entity_b_id=? AND connection_type=?""",
                    (entity_a_id, entity_b_id, connection_type),
                ).fetchone()
                if row:
                    avg_weight = (row["weight"] + weight) / 2.0
                    c.execute(
                        """UPDATE entity_connections SET weight=?
                           WHERE entity_a_id=? AND entity_b_id=? AND connection_type=?""",
                        (avg_weight, entity_a_id, entity_b_id, connection_type),
                    )
            self.conn.commit()
            row = c.execute(
                """SELECT * FROM entity_connections
                   WHERE entity_a_id=? AND entity_b_id=? AND connection_type=?""",
                (entity_a_id, entity_b_id, connection_type),
            ).fetchone()
            return self._row(row) if row else {}
        except Exception as e:
            print(f"[record_connection] {e}", file=sys.stderr)
            return {}

    def get_connections(self, entity_id: int, min_weight: float = 0.5) -> list:
        if not self.conn:
            return []
        try:
            c = self.conn.cursor()
            rows = c.execute(
                """SELECT ec.connection_type, ec.weight, ec.confirmed,
                          CASE WHEN ec.entity_a_id=? THEN ec.entity_b_id ELSE ec.entity_a_id END AS other_id
                   FROM entity_connections ec
                   WHERE (ec.entity_a_id=? OR ec.entity_b_id=?) AND ec.weight >= ?
                   ORDER BY ec.weight DESC""",
                (entity_id, entity_id, entity_id, min_weight),
            ).fetchall()
            result = []
            for row in rows:
                entity = c.execute(
                    "SELECT id, name, entity_type FROM entities WHERE id=?", (row["other_id"],)
                ).fetchone()
                if entity:
                    result.append({
                        "entity_id": entity["id"],
                        "name": entity["name"],
                        "entity_type": entity["entity_type"],
                        "connection_type": row["connection_type"],
                        "weight": row["weight"],
                        "confirmed": row["confirmed"],
                    })
            return result
        except Exception as e:
            print(f"[get_connections] {e}", file=sys.stderr)
            return []

    def find_similar(self, reference_string: str, entity_type: str = None) -> list:
        if not self.conn:
            return []
        try:
            c = self.conn.cursor()
            query = "SELECT id, name, entity_type, reference_string FROM entities"
            params = []
            if entity_type:
                query += " WHERE entity_type = ?"
                params.append(entity_type)
            rows = c.execute(query, params).fetchall()
            ref_lower = reference_string.lower()
            scored = []
            for row in rows:
                ns = SequenceMatcher(None, ref_lower, (row["name"] or "").lower()).ratio()
                rs = SequenceMatcher(None, ref_lower, (row["reference_string"] or "").lower()).ratio()
                best = max(ns, rs)
                if best > 0.3:
                    scored.append({
                        "entity_id": row["id"],
                        "name": row["name"],
                        "entity_type": row["entity_type"],
                        "similarity": round(best, 3),
                    })
            scored.sort(key=lambda x: x["similarity"], reverse=True)
            return scored[:5]
        except Exception as e:
            print(f"[find_similar] {e}", file=sys.stderr)
            return []

    def get_eligible_for_promotion(self, username: str = None, min_mentions: int = 5) -> list:
        if not self.conn:
            return []
        try:
            c = self.conn.cursor()
            uname = username or self.username
            rows = c.execute(
                """SELECT * FROM entities
                   WHERE layer=2 AND promotion_status='eligible'
                   AND mention_count >= ? AND username=?
                   AND (never_promote IS NULL OR never_promote=0)""",
                (min_mentions, uname),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            return []

    def get_entity(self, entity_id: int) -> dict | None:
        if not self.conn:
            return None
        try:
            row = self.conn.execute(
                "SELECT * FROM entities WHERE id=?", (entity_id,)
            ).fetchone()
            return dict(row) if row else None
        except Exception as e:
            print(f"[get_entity] {e}", file=__import__("sys").stderr)
            return None

    def list_entities(self, username: str = None, layer: int = None,
                      entity_type: str = None) -> list:
        if not self.conn:
            return []
        try:
            c = self.conn.cursor()
            query = "SELECT * FROM entities WHERE 1=1"
            params = []
            if username:
                query += " AND username=?"
                params.append(username)
            if layer is not None:
                query += " AND layer=?"
                params.append(layer)
            if entity_type:
                query += " AND entity_type=?"
                params.append(entity_type)
            query += " ORDER BY mention_count DESC"
            return [dict(r) for r in c.execute(query, params).fetchall()]
        except Exception as e:
            print(f"[list_entities] {e}", file=__import__("sys").stderr)
            return []

    def suggest_connections(self, knowledge_ids: list) -> list:
        """Find entity pairs co-occurring in 2+ knowledge atoms — infer connection type."""
        if not self.conn or not knowledge_ids:
            return []
        try:
            c = self.conn.cursor()
            placeholders = ",".join("?" * len(knowledge_ids))
            rows = c.execute(
                f"SELECT knowledge_id, entity_id FROM knowledge_entities WHERE knowledge_id IN ({placeholders})",
                knowledge_ids,
            ).fetchall()
            from collections import defaultdict
            atom_to_entities: dict = defaultdict(list)
            entity_info: dict = {}
            for row in rows:
                atom_to_entities[row["knowledge_id"]].append(row["entity_id"])
            pair_counts: dict = defaultdict(int)
            for entities in atom_to_entities.values():
                for i in range(len(entities)):
                    for j in range(i + 1, len(entities)):
                        pair = (min(entities[i], entities[j]), max(entities[i], entities[j]))
                        pair_counts[pair] += 1
            results = []
            for (a_id, b_id), count in pair_counts.items():
                if count < 2:
                    continue
                ea = c.execute("SELECT id, name, entity_type FROM entities WHERE id=?", (a_id,)).fetchone()
                eb = c.execute("SELECT id, name, entity_type FROM entities WHERE id=?", (b_id,)).fetchone()
                if not ea or not eb:
                    continue
                type_a = (ea["entity_type"] or "").lower()
                type_b = (eb["entity_type"] or "").lower()
                if "code" in type_a or "file" in type_a or "code" in type_b or "file" in type_b:
                    conn_type = "depends-on"
                elif type_a == type_b:
                    conn_type = "similar-pattern"
                else:
                    conn_type = "co-mention"
                confidence = min(1.0, count / 5.0)
                results.append({
                    "entity_a": {"id": ea["id"], "name": ea["name"], "type": ea["entity_type"]},
                    "entity_b": {"id": eb["id"], "name": eb["name"], "type": eb["entity_type"]},
                    "suggested_type": conn_type,
                    "confidence": round(confidence, 3),
                    "co_occurrence_count": count,
                })
            results.sort(key=lambda x: x["confidence"], reverse=True)
            return results
        except Exception as e:
            print(f"[suggest_connections] {e}", file=__import__("sys").stderr)
            return []

