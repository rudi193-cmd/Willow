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
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.db import get_connection

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
    """Open knowledge DB (Postgres only)."""
    return get_connection()


def _row_to_dict(row, keys) -> dict:
    """Convert a DB row to dict."""
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
    conn = _connect()
    try:
        apps_rows = conn.execute(
            "SELECT app_id, name, description, version, privacy_tier FROM registered_apps ORDER BY name"
        ).fetchall()
        consent_rows = conn.execute(
            "SELECT app_id, consented, granted_at, revoked_at FROM app_consent WHERE username=?",
            (user,)
        ).fetchall()

        consent_map = {}
        for r in consent_rows:
            consent_map[r[0]] = {"consented": bool(r[1]), "granted_at": r[2], "revoked_at": r[3]}

        apps = []
        for r in apps_rows:
            app_id, name, description, version, privacy_tier = r[0], r[1], r[2], r[3], r[4]
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
    conn = _connect()
    now = datetime.now(timezone.utc).isoformat()
    try:
        perms = json.dumps(manifest.permissions or [])
        conn.execute("""
            INSERT INTO registered_apps (app_id, name, description, version, permissions, privacy_tier, registered_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (app_id) DO UPDATE SET
                name=EXCLUDED.name, description=EXCLUDED.description,
                version=EXCLUDED.version, permissions=EXCLUDED.permissions,
                privacy_tier=EXCLUDED.privacy_tier
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
    conn = _connect()
    now = datetime.now(timezone.utc).isoformat()
    try:
        row = conn.execute("SELECT app_id FROM registered_apps WHERE app_id=?", (app_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"App '{app_id}' not registered")

        if body.consented:
            granted_at = now
            revoked_at = None
        else:
            granted_at = None
            revoked_at = now

        conn.execute("""
            INSERT INTO app_consent (username, app_id, consented, granted_at, revoked_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (username, app_id) DO UPDATE SET
                consented=EXCLUDED.consented,
                granted_at=EXCLUDED.granted_at,
                revoked_at=EXCLUDED.revoked_at
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
