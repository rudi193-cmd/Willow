"""
credentials.py - Fernet-encrypted SQLite credential vault
Key: ~/.willow_master.key (0600)  DB: ~/.willow_creds.db
"""
import json, os, stat
from core.db import get_connection
from datetime import datetime, timezone
from pathlib import Path

KEY_PATH = Path.home() / ".willow_master.key"

def _load_or_create_key():
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        raise RuntimeError("pip install cryptography")
    if KEY_PATH.exists():
        return KEY_PATH.read_bytes().strip()
    key = Fernet.generate_key()
    KEY_PATH.write_bytes(key)
    KEY_PATH.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return key

def _fernet():
    from cryptography.fernet import Fernet
    return Fernet(_load_or_create_key())

def _get_conn():
    conn = get_connection()
    conn.execute(
        "CREATE TABLE IF NOT EXISTS credentials ("
        "name TEXT PRIMARY KEY, value_enc BYTEA NOT NULL, "
        "env_key TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS audit_log ("
        "id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY, action TEXT NOT NULL, "
        "name TEXT NOT NULL, timestamp TEXT NOT NULL, "
        "actor TEXT DEFAULT 'claude-code')"
    )
    conn.commit()
    return conn

def _audit(conn, action, name):
    conn.execute(
        "INSERT INTO audit_log (action,name,timestamp) VALUES (?,?,?)",
        (action, name, datetime.now(timezone.utc).isoformat())
    )

def set_cred(name, value, env_key=None):
    enc = _fernet().encrypt(value.encode())
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()
    conn.execute(
        "INSERT INTO credentials (name,value_enc,env_key,created_at,updated_at) "
        "VALUES (?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET "
        "value_enc=excluded.value_enc, "
        "env_key=COALESCE(excluded.env_key,credentials.env_key), "
        "updated_at=excluded.updated_at",
        (name, enc, env_key, now, now)
    )
    _audit(conn, "set", name)
    conn.commit()
    conn.close()

def get_cred(name):
    conn = _get_conn()
    row = conn.execute("SELECT value_enc FROM credentials WHERE name=?", (name,)).fetchone()
    conn.close()
    return _fernet().decrypt(row[0]).decode() if row else None

def delete_cred(name):
    conn = _get_conn()
    cur = conn.execute("DELETE FROM credentials WHERE name=?", (name,))
    deleted = cur.rowcount > 0
    if deleted:
        _audit(conn, "delete", name)
    conn.commit()
    conn.close()
    return deleted

def list_creds():
    conn = _get_conn()
    rows = conn.execute(
        "SELECT name,env_key,created_at,updated_at FROM credentials ORDER BY name"
    ).fetchall()
    conn.close()
    return [{"name": r[0], "env_key": r[1], "created_at": r[2], "updated_at": r[3]} for r in rows]

def push_to_env():
    conn = _get_conn()
    rows = conn.execute(
        "SELECT name,value_enc,env_key FROM credentials WHERE env_key IS NOT NULL"
    ).fetchall()
    conn.close()
    f = _fernet()
    pushed = 0
    for _name, enc, env_key in rows:
        try:
            os.environ[env_key] = f.decrypt(enc).decode()
            pushed += 1
        except Exception:
            pass
    return pushed

def export_env_file(path):
    conn = _get_conn()
    rows = conn.execute("SELECT name,value_enc,env_key FROM credentials").fetchall()
    conn.close()
    f = _fernet()
    lines = []
    for name, enc, env_key in rows:
        key = env_key or name.upper().replace("-", "_").replace(".", "_")
        try:
            lines.append(f"{key}={f.decrypt(enc).decode()}\n")
        except Exception:
            pass
    Path(path).write_text("".join(lines), encoding="utf-8")
    return len(lines)

def migrate_from_json(json_path):
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    count = 0
    for name, value in data.items():
        if isinstance(value, str) and value.strip():
            set_cred(str(name), value.strip())
            count += 1
    return count
