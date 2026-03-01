"""
Auth Routes — Local-first login for Willow/SAFE
================================================
Endpoints:
  POST /api/auth/login   — scrypt verify passphrase → issue HMAC token
  POST /api/auth/verify  — re-derive HMAC + expiry check → {valid, username, display_name, expires_at}
  POST /api/auth/logout  — client-side only; returns 200 as UX hook

Token format: base64(username).base64(expires_iso).hmac_hex
  - stdlib only (hmac + hashlib.scrypt) — no pip installs
  - stateless — server re-derives signature on verify

Config:
  WILLOW_AUTH_SECRET env var (default: "willow-local-secret-change-me")
  DEFAULT_DURATION_HOURS = 4, MAX_DURATION_HOURS = 24

CHECKSUM: ΔΣ=42
"""

import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ── Config ──────────────────────────────────────────────────────────────────
USERS_PATH = Path(__file__).parent.parent / "data" / "users.json"
SECRET = os.environ.get("WILLOW_AUTH_SECRET", "willow-local-secret-change-me")
DEFAULT_DURATION_HOURS = 4
MAX_DURATION_HOURS = 24


# ── Helpers ─────────────────────────────────────────────────────────────────

def _load_users() -> dict:
    if not USERS_PATH.exists():
        return {}
    return json.loads(USERS_PATH.read_text())["users"]


def _verify_passphrase(passphrase: str, stored: str) -> bool:
    """stored format: salt_hex:hash_hex (scrypt)"""
    try:
        salt_hex, hash_hex = stored.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.scrypt(passphrase.encode(), salt=salt, n=16384, r=8, p=1)
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False


def _make_token(username: str, duration_hours: int) -> tuple[str, str]:
    """Returns (token, expires_iso)."""
    expires = datetime.now(timezone.utc) + timedelta(hours=duration_hours)
    expires_iso = expires.isoformat()
    u_b64 = base64.b64encode(username.encode()).decode()
    e_b64 = base64.b64encode(expires_iso.encode()).decode()
    sig = hmac.new(SECRET.encode(), f"{u_b64}.{e_b64}".encode(), hashlib.sha256).hexdigest()
    return f"{u_b64}.{e_b64}.{sig}", expires_iso


def _parse_token(token: str) -> dict | None:
    """Returns {username, expires_at} if valid and not expired, else None."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        u_b64, e_b64, sig = parts
        expected = hmac.new(SECRET.encode(), f"{u_b64}.{e_b64}".encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        username = base64.b64decode(u_b64).decode()
        expires_iso = base64.b64decode(e_b64).decode()
        if datetime.now(timezone.utc) > datetime.fromisoformat(expires_iso):
            return None
        return {"username": username, "expires_at": expires_iso}
    except Exception:
        return None


# ── Models ───────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    passphrase: str
    duration_hours: int = DEFAULT_DURATION_HOURS


class VerifyRequest(BaseModel):
    token: str


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/login")
async def login(req: LoginRequest):
    users = _load_users()
    if req.username not in users:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user = users[req.username]
    if not user.get("active", True):
        raise HTTPException(status_code=403, detail="Account inactive")
    stored_hash = user.get("passphrase_hash", "")
    if stored_hash == "SETUP_REQUIRED":
        raise HTTPException(status_code=503, detail="Auth not configured — run setup_auth.py")
    if not _verify_passphrase(req.passphrase, stored_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    duration = min(max(1, req.duration_hours), MAX_DURATION_HOURS)
    token, expires_at = _make_token(req.username, duration)
    return {
        "token": token,
        "username": req.username,
        "display_name": user.get("display_name", req.username),
        "expires_at": expires_at,
    }


@router.post("/verify")
async def verify(req: VerifyRequest):
    result = _parse_token(req.token)
    if result is None:
        return {"valid": False}
    users = _load_users()
    username = result["username"]
    display_name = users.get(username, {}).get("display_name", username)
    return {
        "valid": True,
        "username": username,
        "display_name": display_name,
        "expires_at": result["expires_at"],
    }


@router.post("/logout")
async def logout():
    """Client-side token clearing only — no server state."""
    return {"ok": True}
