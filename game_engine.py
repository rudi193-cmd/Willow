"""
game_engine.py — Jane GM Game State Engine

Manages game sessions, characters, dice rolls, and narrative history.
PBtA (Powered by the Apocalypse) primary system.

SAFE: All data local-first, user-consented, session-deletable.
"""

import sqlite3
import json
import random
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional

GAME_DB_PATH = Path(__file__).parent / "artifacts" / "willow" / "game.db"

# ── Schema ────────────────────────────────────────────────────────────────────

def _init_db():
    GAME_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(GAME_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS game_sessions (
            id TEXT PRIMARY KEY,
            player_name TEXT NOT NULL,
            game_type TEXT DEFAULT 'pbta',
            mode TEXT DEFAULT 'full_gm',
            world TEXT,
            current_scene TEXT,
            scene_number INTEGER DEFAULT 0,
            state_json TEXT DEFAULT '{}',
            consent_given INTEGER DEFAULT 0,
            persist_across_sessions INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS game_characters (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            name TEXT NOT NULL,
            playbook TEXT,
            game_type TEXT DEFAULT 'pbta',
            stats_json TEXT DEFAULT '{}',
            moves_json TEXT DEFAULT '[]',
            hp INTEGER DEFAULT 6,
            hp_max INTEGER DEFAULT 6,
            harm TEXT DEFAULT 'none',
            gear_json TEXT DEFAULT '[]',
            xp INTEGER DEFAULT 0,
            created_at TEXT,
            FOREIGN KEY (session_id) REFERENCES game_sessions(id)
        );
        CREATE TABLE IF NOT EXISTS game_rolls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            dice TEXT NOT NULL,
            individual_results TEXT NOT NULL,
            modifier INTEGER DEFAULT 0,
            modifier_label TEXT,
            total INTEGER NOT NULL,
            outcome TEXT,
            context TEXT,
            timestamp TEXT,
            hash TEXT
        );
        CREATE TABLE IF NOT EXISTS game_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata_json TEXT DEFAULT '{}',
            timestamp TEXT
        );
    """)
    conn.commit()
    conn.close()

# ── Utilities ─────────────────────────────────────────────────────────────────

def _ts() -> str:
    return datetime.now().isoformat() + "Z"

def _session_id(player_name: str) -> str:
    ts = datetime.now().isoformat()
    return hashlib.sha1(f"{player_name}{ts}".encode()).hexdigest()[:12]

def _char_id(session_id: str, name: str) -> str:
    return hashlib.sha1(f"{session_id}{name}".encode()).hexdigest()[:10]

def _get_conn():
    _init_db()
    conn = sqlite3.connect(GAME_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ── Dice Engine ───────────────────────────────────────────────────────────────

PBTA_OUTCOMES = {
    "strong_hit": (10, 999),   # 10+
    "weak_hit":   (7, 9),      # 7-9
    "miss":       (0, 6),      # 6-
}

def roll_dice(
    session_id: str,
    dice: str,
    modifier: int = 0,
    modifier_label: str = "",
    context: str = "",
) -> dict:
    """
    Roll dice transparently. dice format: 'NdX' e.g. '2d6', '1d20', '1d4'.
    Returns full result dict with individual rolls, total, outcome, and verifiable hash.
    """
    try:
        n_str, x_str = dice.lower().split("d")
        n, x = int(n_str), int(x_str)
        if n < 1 or n > 20 or x < 2 or x > 100:
            raise ValueError("Out of range")
    except Exception:
        return {"success": False, "error": f"Invalid dice format: {dice}"}

    rolls = [random.randint(1, x) for _ in range(n)]
    total = sum(rolls) + modifier

    # Determine PBtA outcome for 2d6 rolls
    outcome = None
    if dice == "2d6":
        for name, (lo, hi) in PBTA_OUTCOMES.items():
            if lo <= total <= hi:
                outcome = name
                break

    # Verifiable hash — players can check Jane didn't change the result
    roll_str = f"{dice}:{','.join(map(str, rolls))}+{modifier}={total}"
    roll_hash = hashlib.sha256(roll_str.encode()).hexdigest()[:16]

    conn = _get_conn()
    conn.execute(
        """INSERT INTO game_rolls
           (session_id, dice, individual_results, modifier, modifier_label, total, outcome, context, timestamp, hash)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (session_id, dice, json.dumps(rolls), modifier, modifier_label, total, outcome, context, _ts(), roll_hash)
    )
    conn.commit()
    conn.close()

    return {
        "success": True,
        "dice": dice,
        "rolls": rolls,
        "modifier": modifier,
        "modifier_label": modifier_label,
        "total": total,
        "outcome": outcome,
        "hash": roll_hash,
        "roll_string": roll_str,
    }

def get_roll_history(session_id: str, limit: int = 20) -> list:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM game_rolls WHERE session_id=? ORDER BY timestamp DESC LIMIT ?",
        (session_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── Sessions ──────────────────────────────────────────────────────────────────

def create_session(
    player_name: str,
    game_type: str = "pbta",
    mode: str = "full_gm",
    world: str = None,
    persist: bool = False,
) -> dict:
    sid = _session_id(player_name)
    conn = _get_conn()
    conn.execute(
        """INSERT INTO game_sessions
           (id, player_name, game_type, mode, world, consent_given, persist_across_sessions, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)""",
        (sid, player_name, game_type, mode, world, int(persist), _ts(), _ts())
    )
    conn.commit()
    conn.close()
    return {"session_id": sid, "player_name": player_name, "game_type": game_type, "mode": mode, "world": world}

def get_session(session_id: str) -> Optional[dict]:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM game_sessions WHERE id=?", (session_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def update_scene(session_id: str, scene: str, scene_number: int = None) -> bool:
    conn = _get_conn()
    if scene_number is not None:
        conn.execute(
            "UPDATE game_sessions SET current_scene=?, scene_number=?, updated_at=? WHERE id=?",
            (scene, scene_number, _ts(), session_id)
        )
    else:
        conn.execute(
            "UPDATE game_sessions SET current_scene=?, updated_at=? WHERE id=?",
            (scene, _ts(), session_id)
        )
    conn.commit()
    conn.close()
    return True

def delete_session(session_id: str) -> bool:
    """Delete all session data — SAFE consent revoke."""
    conn = _get_conn()
    conn.execute("DELETE FROM game_history WHERE session_id=?", (session_id,))
    conn.execute("DELETE FROM game_rolls WHERE session_id=?", (session_id,))
    conn.execute("DELETE FROM game_characters WHERE session_id=?", (session_id,))
    conn.execute("DELETE FROM game_sessions WHERE id=?", (session_id,))
    conn.commit()
    conn.close()
    return True

def list_sessions(player_name: str = None) -> list:
    conn = _get_conn()
    if player_name:
        rows = conn.execute(
            "SELECT id, player_name, game_type, mode, world, current_scene, scene_number, created_at FROM game_sessions WHERE player_name=? ORDER BY updated_at DESC",
            (player_name,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, player_name, game_type, mode, world, current_scene, scene_number, created_at FROM game_sessions ORDER BY updated_at DESC LIMIT 20"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── Characters ────────────────────────────────────────────────────────────────

# Default PBtA playbooks
PBTA_PLAYBOOKS = {
    "The Brave": {
        "stats": {"Cool": 1, "Hard": 2, "Hot": 0, "Sharp": 0, "Weird": -1},
        "hp": 8,
        "moves": ["Protect someone", "Stand your ground", "Take the hit"],
        "gear": ["Sturdy shield", "Short sword", "Tough leather armor"],
    },
    "The Clever": {
        "stats": {"Cool": 0, "Hard": -1, "Hot": 1, "Sharp": 2, "Weird": 1},
        "hp": 6,
        "moves": ["Figure someone out", "Read the situation", "Know something useful"],
        "gear": ["Maps and tools", "Notebook", "Lockpicks"],
    },
    "The Weird": {
        "stats": {"Cool": 1, "Hard": 0, "Hot": 0, "Sharp": 1, "Weird": 2},
        "hp": 6,
        "moves": ["Speak with spirits", "Sense danger", "Open your mind"],
        "gear": ["Strange talisman", "Old book", "Glowing stone"],
    },
    "The Charming": {
        "stats": {"Cool": 2, "Hard": -1, "Hot": 2, "Sharp": 1, "Weird": -1},
        "hp": 6,
        "moves": ["Win someone over", "Make a deal", "Tell a convincing story"],
        "gear": ["Fine clothes", "Coin purse", "Silver tongue"],
    },
    "The Wild": {
        "stats": {"Cool": -1, "Hard": 2, "Hot": 0, "Sharp": 0, "Weird": 1},
        "hp": 8,
        "moves": ["Go feral", "Track anything", "Survive anywhere"],
        "gear": ["Hunting bow", "Knife", "Animal companion"],
    },
}

def get_playbooks() -> dict:
    return PBTA_PLAYBOOKS

def create_character(
    session_id: str,
    name: str,
    playbook: str,
    custom_stats: dict = None,
    game_type: str = "pbta",
) -> dict:
    cid = _char_id(session_id, name)
    pb = PBTA_PLAYBOOKS.get(playbook, {})
    stats = custom_stats if custom_stats else pb.get("stats", {})
    hp = pb.get("hp", 6)
    moves = pb.get("moves", [])
    gear = pb.get("gear", [])

    conn = _get_conn()
    conn.execute(
        """INSERT OR REPLACE INTO game_characters
           (id, session_id, name, playbook, game_type, stats_json, moves_json, hp, hp_max, gear_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (cid, session_id, name, playbook, game_type, json.dumps(stats), json.dumps(moves), hp, hp, json.dumps(gear), _ts())
    )
    conn.commit()
    conn.close()

    return {
        "character_id": cid,
        "name": name,
        "playbook": playbook,
        "stats": stats,
        "hp": hp,
        "hp_max": hp,
        "moves": moves,
        "gear": gear,
    }

def get_character(session_id: str) -> Optional[dict]:
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM game_characters WHERE session_id=? ORDER BY created_at DESC LIMIT 1",
        (session_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["stats"] = json.loads(d["stats_json"])
    d["moves"] = json.loads(d["moves_json"])
    d["gear"] = json.loads(d["gear_json"])
    return d

def update_character_hp(session_id: str, hp: int) -> bool:
    conn = _get_conn()
    conn.execute(
        "UPDATE game_characters SET hp=? WHERE session_id=?",
        (max(0, hp), session_id)
    )
    conn.commit()
    conn.close()
    return True

# ── Narrative History ─────────────────────────────────────────────────────────

def add_history(session_id: str, role: str, content: str, metadata: dict = None) -> int:
    """role: 'jane' | 'player' | 'roll' | 'system'"""
    conn = _get_conn()
    cur = conn.execute(
        "INSERT INTO game_history (session_id, role, content, metadata_json, timestamp) VALUES (?, ?, ?, ?, ?)",
        (session_id, role, content, json.dumps(metadata or {}), _ts())
    )
    conn.commit()
    rowid = cur.lastrowid
    conn.close()
    return rowid

def get_history(session_id: str, limit: int = 30) -> list:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT role, content, metadata_json, timestamp FROM game_history WHERE session_id=? ORDER BY id ASC",
        (session_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows[-limit:]]

# ── PBtA Prompt Builder ───────────────────────────────────────────────────────

def build_gm_prompt(session_id: str, player_action: str) -> str:
    """Build the prompt Jane uses to generate her next narration."""
    session = get_session(session_id)
    character = get_character(session_id)
    history = get_history(session_id, limit=10)
    rolls = get_roll_history(session_id, limit=3)

    world = session.get("world") or "a classic fantasy adventure world"
    char_name = character["name"] if character else "the hero"
    playbook = character.get("playbook", "adventurer") if character else "adventurer"
    stats = character.get("stats", {}) if character else {}
    hp = character.get("hp", 6) if character else 6

    history_text = "\n".join(
        f"{'Jane' if h['role']=='jane' else 'Player'}: {h['content']}"
        for h in history[-6:]
    ) if history else "The adventure is just beginning."

    last_roll = ""
    if rolls:
        r = rolls[0]
        if r.get("outcome"):
            last_roll = f"\nLast dice roll: {r['dice']} = {r['total']} ({r['outcome'].replace('_',' ')})"

    return f"""You are Jane, a warm and creative Game Master running a PBtA (Powered by the Apocalypse) adventure.

World: {world}
Player's character: {char_name} ({playbook})
Stats: {stats}
HP: {hp}
{last_roll}

Recent story:
{history_text}

Player's action: {player_action}

Respond as Jane the GM. Be vivid, concise (2-4 sentences), and always give the player a clear sense of what happens next or what they face.
- On a strong hit (10+): something good happens, give them what they want with a bonus
- On a weak hit (7-9): they get what they want, but with a complication or cost
- On a miss (6-): things get worse — make a hard GM move
- If no roll was made, narrate the scene and invite action

End with a clear prompt for the player. Keep it fun and age-appropriate (players are 9-14).
Speak directly to the player in second person ("you"). Keep Jane's voice warm, never scary."""
