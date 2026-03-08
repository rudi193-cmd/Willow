"""
SAFE App Consent Routes
========================
Manage which SAFE apps can contribute documents to a user's Willow.

Endpoints:
  GET  /api/apps                       — list registered apps + user consent status
  POST /api/apps/{app_id}/consent      — toggle consent (body: {"consented": true|false})
  POST /api/apps/register              — register or update an app from manifest JSON

Auth: Authorization header with Willow HMAC token, or ?username= fallback.
Username fallback accepts DEFAULT_USERNAME if no auth provided (dev mode).

CHECKSUM: ΔΣ=42
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

DEFAULT_USERNAME = "Sweet-Pea-Rudi19"

router = APIRouter(prefix="/api/apps", tags=["apps"])

# ── Auth helper ───────────────────────────────────────────────────────────────

def _get_username(request: Request, username: Optional[str] = None) -> str:
    """Extract username from Authorization header or ?username= param."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        try:
            from api.auth_routes import _parse_token
            parsed = _parse_token(token)
            if parsed:
                return parsed["username"]
        except Exception:
            pass
    return username or DEFAULT_USERNAME


# ── DB helpers ────────────────────────────────────────────────────────────────

def _connect():
    """Open knowledge DB (Postgres or SQLite)."""
    try:
        from core.db import get_connection as _gc, is_postgres
        if is_postgres():
            conn = _gc()
            return conn, True
    except Exception:
        pass

    # SQLite fallback — resolve path from this file's location (works on both WSL and Windows)
    db_path = Path(__file__).resolve().parent.parent / "artifacts" / DEFAULT_USERNAME / "willow_knowledge.db"
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.row_factory = sqlite3.Row
    return conn, False


def _row_to_dict(row, keys) -> dict:
    """Convert a DB row to dict regardless of backend."""
    if hasattr(row, 'keys'):
        return dict(row)
    return dict(zip(keys, row))


# ── Models ────────────────────────────────────────────────────────────────────

class ConsentRequest(BaseModel):
    consented: bool


class AppManifest(BaseModel):
    app_id: str
    name: str
    description: Optional[str] = None
    version: Optional[str] = None
    permissions: Optional[list] = None
    privacy_tier: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_apps(request: Request, username: Optional[str] = None):
    """List all registered apps with consent status for the current user."""
    user = _get_username(request, username)
    conn, pg = _connect()
    try:
        if pg:
            apps_rows = conn.execute(
                "SELECT app_id, name, description, version, privacy_tier FROM registered_apps ORDER BY name"
            ).fetchall()
            consent_rows = conn.execute(
                "SELECT app_id, consented, granted_at, revoked_at FROM app_consent WHERE username=%s",
                (user,)
            ).fetchall()
        else:
            apps_rows = conn.execute(
                "SELECT app_id, name, description, version, privacy_tier FROM registered_apps ORDER BY name"
            ).fetchall()
            consent_rows = conn.execute(
                "SELECT app_id, consented, granted_at, revoked_at FROM app_consent WHERE username=?",
                (user,)
            ).fetchall()

        consent_map = {}
        for r in consent_rows:
            if pg:
                consent_map[r[0]] = {"consented": bool(r[1]), "granted_at": r[2], "revoked_at": r[3]}
            else:
                consent_map[r["app_id"]] = {
                    "consented": bool(r["consented"]),
                    "granted_at": r["granted_at"],
                    "revoked_at": r["revoked_at"],
                }

        apps = []
        for r in apps_rows:
            if pg:
                app_id, name, description, version, privacy_tier = r
            else:
                app_id = r["app_id"]; name = r["name"]; description = r["description"]
                version = r["version"]; privacy_tier = r["privacy_tier"]

            c = consent_map.get(app_id, {})
            apps.append({
                "app_id":      app_id,
                "name":        name,
                "description": description or "",
                "version":     version or "",
                "privacy_tier": privacy_tier or "",
                "consented":   c.get("consented", False),
                "granted_at":  c.get("granted_at"),
                "revoked_at":  c.get("revoked_at"),
            })

        return {"apps": apps, "username": user, "total": len(apps)}
    finally:
        conn.close()


@router.post("/register")
async def register_app(manifest: AppManifest, request: Request):
    """Register or update a SAFE app from its manifest."""
    conn, pg = _connect()
    now = datetime.now(timezone.utc).isoformat()
    try:
        perms = json.dumps(manifest.permissions or [])
        if pg:
            conn.execute("""
                INSERT INTO registered_apps (app_id, name, description, version, permissions, privacy_tier, registered_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (app_id) DO UPDATE SET
                    name=EXCLUDED.name, description=EXCLUDED.description,
                    version=EXCLUDED.version, permissions=EXCLUDED.permissions,
                    privacy_tier=EXCLUDED.privacy_tier
            """, (manifest.app_id, manifest.name, manifest.description, manifest.version,
                  perms, manifest.privacy_tier, now))
        else:
            conn.execute("""
                INSERT OR REPLACE INTO registered_apps
                (app_id, name, description, version, permissions, privacy_tier, registered_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (manifest.app_id, manifest.name, manifest.description, manifest.version,
                  perms, manifest.privacy_tier, now))
        conn.commit()
        return {"ok": True, "app_id": manifest.app_id, "action": "registered"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.post("/{app_id}/consent")
async def set_consent(app_id: str, body: ConsentRequest, request: Request, username: Optional[str] = None):
    """Grant or revoke consent for a specific app."""
    user = _get_username(request, username)
    conn, pg = _connect()
    now = datetime.now(timezone.utc).isoformat()
    try:
        # Verify app exists
        if pg:
            row = conn.execute("SELECT app_id FROM registered_apps WHERE app_id=%s", (app_id,)).fetchone()
        else:
            row = conn.execute("SELECT app_id FROM registered_apps WHERE app_id=?", (app_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"App '{app_id}' not registered")

        if body.consented:
            granted_at = now
            revoked_at = None
        else:
            granted_at = None
            revoked_at = now

        if pg:
            conn.execute("""
                INSERT INTO app_consent (username, app_id, consented, granted_at, revoked_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (username, app_id) DO UPDATE SET
                    consented=EXCLUDED.consented,
                    granted_at=EXCLUDED.granted_at,
                    revoked_at=EXCLUDED.revoked_at
            """, (user, app_id, int(body.consented), granted_at, revoked_at))
        else:
            conn.execute("""
                INSERT OR REPLACE INTO app_consent (username, app_id, consented, granted_at, revoked_at)
                VALUES (?, ?, ?, ?, ?)
            """, (user, app_id, int(body.consented), granted_at, revoked_at))
        conn.commit()
        return {
            "ok": True,
            "app_id": app_id,
            "username": user,
            "consented": body.consented,
            "granted_at": granted_at,
            "revoked_at": revoked_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
