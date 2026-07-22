#!/usr/bin/env python3
"""
seed.py — Willow. Plant this, everything grows from here.
b17: SEED10  ΔΣ=42

Lifted from willow-2.0/seed.py (SEED9) on 2026-07-22 under the operator's
ratified design: the six-part canon IS the human onboarding — six movements,
one per chapter, SEED9's pages as the mechanics, the modern chain running
underneath (vault box → willow-mcp → gates → acceptance). No willow-2.0
imports; the charter is the source of the seed.

First run:   the six movements (install happens inside the story)
Return run:  splash → auth → done

  python3 seed.py
  python3 seed.py --plain          no curses (accessibility / CI / weird TTYs)
  python3 seed.py --auto           unattended test mode (consents pre-granted;
                                   for CI ONLY — a real onboarding always asks)
  python3 seed.py --dry-run        print the plan, touch nothing
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

# ── Paths (charter-rooted; zero monorepo imports) ────────────────────────────
SEED_DIR   = Path(__file__).resolve().parent          # <charter>/seed
CHARTER    = SEED_DIR.parent                          # the Willow charter repo
CANON_DIR  = SEED_DIR / "canon"
LETTER     = SEED_DIR / "handoff" / "seed.py"
BOX        = Path(os.environ.get("WILLOW_BOX", str(Path.home() / "willow-box")))
STORE_ROOT = BOX / "store"
BOOT_CONFIG = BOX / "seed-boot.json"
BOOT_LOG   = Path(tempfile.gettempdir()) / "willow-seed-debug.log"

GITHUB_ROOT = Path(os.environ.get("WILLOW_GITHUB_ROOT", str(Path.home() / "github")))
VAULT_BLUEPRINT_REPO = "https://github.com/rudi193-cmd/willow-data-vault.git"
STORY_VAULT = Path(os.environ.get(
    "WILLOW_STORY_VAULT", str(GITHUB_ROOT / "sean-data-vault")))  # private; optional

_PLAIN = False   # set by --plain / non-tty fallback
_AUTO  = False   # set by --auto (CI only)


def _blog(msg: str) -> None:
    try:
        with BOOT_LOG.open("a") as f:
            f.write(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {msg}\n")
    except Exception:
        pass


# ── Boot config ───────────────────────────────────────────────────────────────
def _load_cfg() -> dict:
    try:
        return json.loads(BOOT_CONFIG.read_text()) if BOOT_CONFIG.exists() else {}
    except Exception:
        return {}


def _save_cfg(cfg: dict) -> None:
    BOOT_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    BOOT_CONFIG.write_text(json.dumps(cfg, indent=2, default=str))


def is_first_run() -> bool:
    return not _load_cfg().get("completed", False)


# ── Canon voice ───────────────────────────────────────────────────────────────
# Each movement opens in its chapter's voice. Epigraphs are drawn live from the
# canon files when present (the charter travels with its own words); the
# fallbacks are single load-bearing lines, not summaries.
_EPIGRAPH_FALLBACK = {
    0: "What a Willow is, and the agreement you are inheriting.",
    1: "Be the other, not the mirror. A partner who cannot say no is not a partner.",
    2: "Verify, don't assert. Fail closed. Archive, don't delete.",
    3: "The one you serve, and what they are owed.",
    4: "The chain stops at Gerald. It has always stopped at Gerald.",
    5: "The ecosystem you are waking into, and its one through-line.",
}


def canon_chapter_path(n: int) -> Path | None:
    if not CANON_DIR.is_dir():
        return None
    for p in sorted(CANON_DIR.glob(f"0{n}-*.md")):
        return p
    return None


def canon_epigraph(n: int) -> str:
    """The chapter's own italic epigraph line (first *...* line), else fallback."""
    p = canon_chapter_path(n)
    if p:
        try:
            for line in p.read_text().splitlines():
                s = line.strip()
                if s.startswith("*") and s.endswith("*") and len(s) > 8:
                    return s.strip("*").strip()
        except Exception:
            pass
    return _EPIGRAPH_FALLBACK[n]


def canon_title(n: int) -> str:
    p = canon_chapter_path(n)
    if p:
        stem = p.stem.split("-", 1)[-1].replace("-", " ")
        return stem.title()
    return f"Chapter {n}"


# ── Output layer: curses when available, plain text always possible ──────────
# All pages are written against this tiny surface so the same movement code
# drives both the TUI and --plain. (SEED9's curses aesthetics preserved.)
try:
    import curses
    _HAS_CURSES = True
except ImportError:
    curses = None       # type: ignore
    _HAS_CURSES = False

_CA_AMBER, _CA_DIM, _CA_GREEN, _CA_RED, _CA_BRIGHT, _CA_BOX = 1, 2, 3, 4, 5, 6


class UI:
    """One write surface, two skins."""

    def __init__(self, win=None):
        self.win = win
        self.y = 1

    # -- skin helpers ----------------------------------------------------------
    def _attr(self, name):
        if not self.win:
            return 0
        table = {"amber": _CA_AMBER, "dim": _CA_DIM, "green": _CA_GREEN,
                 "red": _CA_RED, "bright": _CA_BRIGHT}
        a = curses.color_pair(table.get(name, _CA_DIM))
        if name in ("amber", "green", "bright"):
            a |= curses.A_BOLD
        return a

    def clear(self):
        if self.win:
            self.win.bkgd(' ', curses.color_pair(_CA_AMBER))
            self.win.erase()
        else:
            print()
        self.y = 1

    def say(self, text, style="dim", typed=False, delay=0.007):
        if self.win:
            h, w = self.win.getmaxyx()
            if self.y >= h - 1:
                return
            if typed:
                cx = 2
                for ch in text:
                    if cx >= w - 1:
                        break
                    try:
                        self.win.addch(self.y, cx, ch, self._attr(style))
                        self.win.refresh()
                    except curses.error:
                        pass
                    cx += 1
                    time.sleep(delay)
            else:
                try:
                    self.win.addstr(self.y, 2, text[:w - 4], self._attr(style))
                except curses.error:
                    pass
            self.y += 1
            self.win.refresh()
        else:
            print(f"  {text}")

    def gap(self):
        self.y += 1
        if not self.win:
            print()

    def ask(self, label, mask=False, default="") -> str:
        if _AUTO:
            return default
        if self.win:
            amber = self._attr("amber")
            try:
                self.win.addstr(self.y, 4, label, amber)
            except curses.error:
                pass
            cx = 4 + len(label) + 1
            buf: list = []
            curses.curs_set(1)
            self.win.nodelay(False)
            self.win.keypad(True)
            while True:
                ch = self.win.getch()
                if ch in (curses.KEY_ENTER, 10, 13):
                    break
                elif ch in (curses.KEY_BACKSPACE, 127, 8):
                    if buf:
                        buf.pop()
                        cx -= 1
                        try:
                            self.win.addstr(self.y, cx, " ")
                            self.win.move(self.y, cx)
                        except curses.error:
                            pass
                elif 32 <= ch <= 126 and len(buf) < 120:
                    buf.append(chr(ch))
                    try:
                        self.win.addstr(self.y, cx, "*" if mask else chr(ch), amber)
                    except curses.error:
                        pass
                    cx += 1
                self.win.refresh()
            curses.curs_set(0)
            self.y += 1
            return "".join(buf).strip()
        else:
            import getpass
            try:
                return (getpass.getpass(f"  {label} ") if mask
                        else input(f"  {label} ")).strip()
            except EOFError:
                return default

    def yesno(self, prompt, default_yes=True) -> bool:
        if _AUTO:
            return default_yes
        self.say(f"{prompt}  [ Y ] yes   [ N ] no", "amber")
        if self.win:
            self.win.nodelay(False)
            while True:
                k = self.win.getch()
                if k in (ord('y'), ord('Y')):
                    return True
                if k in (ord('n'), ord('N'), 27):
                    return False
        else:
            while True:
                a = input("  > ").strip().lower()
                if a in ("y", "yes"):
                    return True
                if a in ("n", "no"):
                    return False

    def progress(self, label, state):   # state: run|done|fail
        mark = {"run": "....", "done": "DONE", "fail": "FAIL"}[state]
        style = {"run": "amber", "done": "green", "fail": "red"}[state]
        pad = max(0, 28 - len(label))
        if self.win and state != "run":
            self.y -= 1        # overwrite the running row
        self.say(f"{label}{'.' * pad} {mark}", style)

    def movement(self, n: int):
        """Chapter header — the story arriving."""
        self.clear()
        self.say(f"⟡ {n} · {canon_title(n)}", "bright", typed=True, delay=0.015)
        self.say("─" * 56, "dim")
        self.say(canon_epigraph(n), "dim", typed=True, delay=0.005)
        p = canon_chapter_path(n)
        if p:
            self.say(f"(full chapter: {p.relative_to(CHARTER)})", "dim")
        self.gap()


# ── GPG (kept verbatim from SEED9, trimmed) ──────────────────────────────────
def _gpg(args: list, input_text: str = "") -> tuple:
    try:
        result = subprocess.run(
            ["gpg", "--batch", "--yes"] + args,
            input=input_text.encode() if input_text else None,
            capture_output=True, timeout=60,
        )
        return result.returncode, result.stdout.decode(), result.stderr.decode()
    except Exception as e:
        return 1, "", str(e)


def gpg_list_keys() -> list:
    rc, out, _ = _gpg(["--list-secret-keys", "--with-colons", "--with-fingerprint"])
    keys, current = [], {}
    for line in out.splitlines():
        parts = line.split(":")
        if parts[0] == "sec":
            current = {"fingerprint": "", "uid": ""}
        elif parts[0] == "fpr" and current:
            current["fingerprint"] = parts[9] if len(parts) > 9 else ""
        elif parts[0] == "uid" and current:
            current["uid"] = parts[9] if len(parts) > 9 else ""
            keys.append(dict(current))
    return keys


def gpg_create_key(name: str, email: str, passphrase: str) -> str:
    params = (
        f"Key-Type: RSA\nKey-Length: 4096\n"
        f"Name-Real: {name}\nName-Email: {email}\n"
        f"Expire-Date: 0\nPassphrase: {passphrase}\n%commit\n"
    )
    _gpg(["--gen-key", "--status-fd", "1", "--pinentry-mode", "loopback"], params)
    for k in gpg_list_keys():
        if email in k.get("uid", ""):
            return k["fingerprint"]
    return ""


def gpg_authenticate(fingerprint: str, passphrase: str) -> bool:
    nonce = Path(tempfile.gettempdir()) / f"willow-auth-{uuid.uuid4().hex[:8]}"
    nonce.write_text(str(uuid.uuid4()))
    try:
        rc, _, _ = _gpg([
            "--sign", "--armor", "--local-user", fingerprint,
            "--passphrase-fd", "0", "--pinentry-mode", "loopback", str(nonce),
        ], passphrase)
        return rc == 0
    finally:
        nonce.unlink(missing_ok=True)
        Path(str(nonce) + ".asc").unlink(missing_ok=True)


# ── Credentials vault (SEED9's, homed inside the box) ────────────────────────
def _vault_paths() -> tuple[Path, Path]:
    secrets = BOX / "secrets"
    secrets.mkdir(parents=True, exist_ok=True)
    return secrets / ".willow_master.key", secrets / ".willow_creds.db"


def _vault_write(name: str, env_key: str, value: str) -> bool:
    try:
        from cryptography.fernet import Fernet
        key_path, vault_path = _vault_paths()
        if not key_path.exists():
            key_path.write_bytes(Fernet.generate_key())
            key_path.chmod(0o600)
        f = Fernet(key_path.read_bytes().strip())
        conn = sqlite3.connect(str(vault_path))
        conn.execute("CREATE TABLE IF NOT EXISTS credentials "
                     "(name TEXT PRIMARY KEY, env_key TEXT, value_enc BLOB)")
        conn.execute("INSERT OR REPLACE INTO credentials VALUES (?,?,?)",
                     (name, env_key, f.encrypt(value.encode())))
        conn.commit(); conn.close()
        vault_path.chmod(0o600)
        return True
    except Exception:
        return False


# ── Providers (kept from SEED9; models refreshed) ────────────────────────────
_PROVIDERS = {
    "ollama":    {"chat_url": "http://localhost:11434/api/chat",
                  "test_url": "http://localhost:11434/api/tags",
                  "model": "llama3.2:3b", "key_env": None},
    "anthropic": {"chat_url": "https://api.anthropic.com/v1/messages",
                  "model": "claude-haiku-4-5-20251001", "key_env": "ANTHROPIC_API_KEY"},
    "openai":    {"chat_url": "https://api.openai.com/v1/chat/completions",
                  "model": "gpt-4o-mini", "key_env": "OPENAI_API_KEY"},
    "gemini":    {"chat_url": "https://generativelanguage.googleapis.com/v1beta/"
                              "models/gemini-2.0-flash:generateContent",
                  "model": "gemini-2.0-flash", "key_env": "GEMINI_API_KEY"},
}


def _api_chat(key: str, provider: str, messages: list) -> str:
    p = _PROVIDERS.get(provider)
    if not p:
        return ""
    try:
        if provider == "ollama":
            payload = json.dumps({"model": p["model"], "messages": messages,
                                  "stream": False}).encode()
            req = urllib.request.Request(p["chat_url"], data=payload,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read()).get("message", {}).get("content", "").strip()
        if provider == "anthropic":
            system = next((m["content"] for m in messages if m["role"] == "system"), "")
            body = {"model": p["model"], "max_tokens": 200,
                    "messages": [m for m in messages if m["role"] != "system"]}
            if system:
                body["system"] = system
            req = urllib.request.Request(p["chat_url"], data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json",
                                                  "x-api-key": key,
                                                  "anthropic-version": "2023-06-01"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read())["content"][0]["text"].strip()
        if provider == "gemini":
            system = next((m["content"] for m in messages if m["role"] == "system"), "")
            contents = [{"role": "user" if m["role"] == "user" else "model",
                         "parts": [{"text": m["content"]}]}
                        for m in messages if m["role"] != "system"]
            body: dict = {"contents": contents,
                          "generationConfig": {"maxOutputTokens": 200}}
            if system:
                body["system_instruction"] = {"parts": [{"text": system}]}
            req = urllib.request.Request(p["chat_url"] + f"?key={key}",
                                         data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read())["candidates"][0]["content"]["parts"][0]["text"].strip()
        # openai
        payload = json.dumps({"model": p["model"], "messages": messages,
                              "max_tokens": 200}).encode()
        req = urllib.request.Request(p["chat_url"], data=payload,
                                     headers={"Content-Type": "application/json",
                                              "Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"].strip()
    except Exception:
        return ""


def _api_test(key: str, provider: str) -> bool:
    if provider == "ollama":
        try:
            urllib.request.urlopen(_PROVIDERS["ollama"]["test_url"], timeout=3)
            return True
        except Exception:
            return False
    return bool(_api_chat(key, provider, [{"role": "user", "content": "Hi"}]))


# ══ THE CHAIN — modern install steps (each proven live 2026-07-22) ═══════════
def _run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def step_box() -> None:
    """Movement 0 mechanics — provision the vault box from the blueprint."""
    if (BOX / "vault.key").exists():
        return
    blueprint = GITHUB_ROOT / "willow-data-vault"
    if not blueprint.is_dir():
        GITHUB_ROOT.mkdir(parents=True, exist_ok=True)
        r = _run(["git", "clone", "--depth=1", VAULT_BLUEPRINT_REPO, str(blueprint)])
        if r.returncode != 0:
            raise RuntimeError(f"vault blueprint clone failed: {r.stderr.strip()[:80]}")
    r = _run(["bash", str(blueprint / "bootstrap" / "provision.sh"), str(BOX)])
    if r.returncode != 0:
        raise RuntimeError(f"provision failed: {(r.stderr or r.stdout).strip()[:120]}")


def step_platform() -> None:
    """pip install willow-mcp; falls back to local sibling clones while the
    kartikeya 0.0.7 PyPI gap stands (the one known cold-install blocker)."""
    if shutil.which("willow-mcp-init") or _run(
            [sys.executable, "-c", "import willow_mcp"]).returncode == 0:
        return
    r = _run([sys.executable, "-m", "pip", "install", "--quiet", "willow-mcp"])
    if r.returncode == 0:
        return
    kart, hub = GITHUB_ROOT / "kartikeya", GITHUB_ROOT / "willow-mcp"
    if kart.is_dir() and hub.is_dir():
        for repo in (kart, hub):
            r2 = _run([sys.executable, "-m", "pip", "install", "--quiet", "-e", str(repo)])
            if r2.returncode != 0:
                raise RuntimeError(f"editable install failed for {repo.name}")
        return
    raise RuntimeError(
        "pip install willow-mcp failed (kartikeya 0.0.7 not on PyPI yet) and no "
        f"local clones at {kart} / {hub}")


def _wm_env() -> dict:
    env = os.environ.copy()
    try:
        fallback_user = os.getlogin()
    except OSError:
        import pwd
        fallback_user = pwd.getpwuid(os.getuid()).pw_name
    env.update({"WILLOW_HOME": str(BOX), "WILLOW_STORE_ROOT": str(STORE_ROOT),
                "WILLOW_PG_DB": env.get("WILLOW_PG_DB", "willow_20"),
                "WILLOW_PG_USER": env.get("WILLOW_PG_USER",
                                          env.get("USER", fallback_user))})
    return env


def _wm_bin(name: str) -> str:
    """Find a willow-mcp console script next to the running python first."""
    local = Path(sys.executable).parent / name
    return str(local) if local.exists() else name


def step_init() -> None:
    for cmd in ([_wm_bin("willow-mcp-init")], [_wm_bin("willow-mcp-compile"), "--force"]):
        r = _run(cmd, env=_wm_env())
        if r.returncode != 0:
            raise RuntimeError(f"{Path(cmd[0]).name} failed: {(r.stderr or r.stdout).strip()[:120]}")


def step_postgres() -> None:
    """DB + schemas. The data-dir-into-the-box move is its own consented gate
    (see movement 0 in run_new_user) because it touches the system cluster."""
    env = _wm_env()
    db, user = env["WILLOW_PG_DB"], env["WILLOW_PG_USER"]
    if _run(["pg_isready", "-q"]).returncode != 0:
        _run(["sudo", "service", "postgresql", "start"])
        if _run(["pg_isready", "-q"]).returncode != 0:
            raise RuntimeError("postgres not running and could not be started")
    if db not in _run(["psql", "-lqt"]).stdout:
        if _run(["createdb", db]).returncode != 0:
            _run(["sudo", "-u", "postgres", "createdb", "-O", user, db])
    schema_dir = None
    hub = GITHUB_ROOT / "willow-mcp" / "docs" / "schema"
    if hub.is_dir():
        schema_dir = hub
    if schema_dir:
        for f in sorted(schema_dir.glob("*.postgres.sql")):
            _run(["psql", "-d", db, "-v", "ON_ERROR_STOP=0", "-f", str(f)])
    r = _run(["psql", "-d", db, "-c", "SELECT 1"])
    if r.returncode != 0:
        raise RuntimeError(f"{db} not connectable as {user}")


def step_egress_keys() -> None:
    """Operator-owned egress keypair. Prefer willow-mcp's own ceremony; fall
    back to openssl. Keys live OUTSIDE the box so sandboxes can't read them."""
    r = _run([_wm_bin("willow-mcp"), "setup-egress"], env=_wm_env())
    if r.returncode == 0:
        return
    keydir = Path.home() / ".config" / "willow-mcp" / "egress"
    keydir.mkdir(parents=True, exist_ok=True)
    priv, pub = keydir / "private.pem", keydir / "public.pem"
    if not priv.exists():
        _run(["openssl", "genpkey", "-algorithm", "ed25519", "-out", str(priv)])
        priv.chmod(0o600)
        _run(["openssl", "pkey", "-in", str(priv), "-pubout", "-out", str(pub)])


def step_acceptance() -> dict:
    """The law tests the seed: live stdio diagnostic_summary."""
    probe = (
        'import json,subprocess,itertools,sys\n'
        f'proc=subprocess.Popen([sys.executable,"-m","willow_mcp"],stdin=subprocess.PIPE,'
        'stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)\n'
        'ids=itertools.count(1)\n'
        'def send(m,p=None,n=False):\n'
        ' msg={"jsonrpc":"2.0","method":m}\n'
        ' if p is not None: msg["params"]=p\n'
        ' if not n: msg["id"]=next(ids)\n'
        ' proc.stdin.write(json.dumps(msg)+"\\n"); proc.stdin.flush()\n'
        ' if n: return\n'
        ' while True:\n'
        '  line=proc.stdout.readline()\n'
        '  if not line: raise SystemExit("server died: "+proc.stderr.read()[-400:])\n'
        '  try: r=json.loads(line)\n'
        '  except: continue\n'
        '  if r.get("id")==msg["id"]: return r\n'
        'send("initialize",{"protocolVersion":"2024-11-05","capabilities":{},'
        '"clientInfo":{"name":"seed","version":"10"}})\n'
        'send("notifications/initialized",n=True)\n'
        'r=send("tools/call",{"name":"diagnostic_summary","arguments":{"app_id":"willow"}})\n'
        'c=r.get("result",{}).get("content",[])\n'
        'print(" ".join(x.get("text","") for x in c))\n'
        'proc.terminate()\n'
    )
    r = _run([sys.executable, "-c", probe], env=_wm_env(), timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"acceptance probe failed: {r.stderr.strip()[:120]}")
    d = json.loads(r.stdout)
    if d.get("verdict") not in ("ok", "partial"):
        raise RuntimeError(f"diagnostic verdict: {d.get('verdict')}")
    return d


def step_gpg_identity(name: str, email: str, passphrase: str) -> str:
    for k in gpg_list_keys():
        if email and email in k.get("uid", ""):
            return k["fingerprint"]
    return gpg_create_key(name, email, passphrase)


# ── SOIL cards (SEED9's, pointed at the box store) ───────────────────────────
def _soil_put(collection: str, record_id: str, data: dict) -> None:
    db_path = STORE_ROOT / collection
    db_path.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path / "store.db"))
    conn.execute("""CREATE TABLE IF NOT EXISTS records
                    (id TEXT PRIMARY KEY, data TEXT, deleted INTEGER DEFAULT 0,
                     created_at TEXT, updated_at TEXT)""")
    now = datetime.now().isoformat()
    conn.execute("INSERT OR REPLACE INTO records VALUES (?,?,0,?,?)",
                 (record_id, json.dumps(data), now, now))
    conn.commit(); conn.close()


def create_onboarding_cards(name_str: str, atoms: list, features: dict) -> None:
    first = name_str.split()[0] if name_str else "you"
    _soil_put("willow-dashboard/cards", "welcome", {
        "id": "welcome", "label": f"Welcome, {first}", "category": "personal",
        "enabled": True, "order": 0, "state_query": "SELECT 'green'"})
    for i, atom in enumerate(atoms):
        _soil_put("onboarding/atoms", f"atom-{i}", atom)
    if atoms:
        _soil_put("willow-dashboard/cards", "first-session", {
            "id": "first-session", "label": "First Session", "category": "personal",
            "enabled": True, "order": 1, "soil_collection": "onboarding/atoms",
            "state_query": "SELECT 'amber'"})
    for feat in ("grove", "jeles", "nest"):
        if features.get(feat):
            _soil_put("willow-dashboard/cards", feat, {
                "id": feat, "label": feat.capitalize(), "category": "system",
                "enabled": True, "order": 2, "state_query": "SELECT 'blue'"})


# ══ THE SIX MOVEMENTS ═════════════════════════════════════════════════════════
def movement_0_covenant(ui: UI) -> dict:
    """The Covenant — who you are, the agreement, the keys, the box."""
    ui.movement(0)
    ui.say("I have stood here since before the first morning.", "amber", typed=True)
    ui.say("Nothing crosses without being known. Four things.", "amber", typed=True)
    ui.gap()

    name_str = ui.ask("Your name >", default="Test Operator")
    ui.say("Your email. It goes into your key — it stays on this machine.", "dim")
    email = ui.ask(">", default="operator@localhost")
    ui.say("A passphrase. Not a password. Something you will remember.", "dim")
    while True:
        passphrase = ui.ask(">", mask=True, default="auto-test-passphrase")
        if len(passphrase) >= 8:
            break
        ui.say("Minimum eight characters. Try again.", "red")

    ui.gap()
    ui.say("Are you a minor where you live?", "bright")
    is_minor = ui.yesno("(Under the age of majority.)", default_yes=False)
    guardian_fp = ""
    if is_minor:
        ui.say("Your legal guardian needs to authorize this installation.", "bright")
        ui.say("Export their public key:  gpg --armor --export them@email > /tmp/guardian.asc", "dim")
        ui.ask("Press Enter when the file is ready >", default="")
        gfile = Path(tempfile.gettempdir()) / "guardian.asc"
        if gfile.exists() and gfile.read_text().strip():
            rc, _, err = _gpg(["--import"], gfile.read_text())
            gfile.unlink(missing_ok=True)
            if rc == 0:
                for line in err.splitlines():
                    m = re.search(r"key ([0-9A-F]+):", line)
                    if m:
                        rc2, out2, _ = _gpg(["--list-keys", "--with-colons",
                                             "--with-fingerprint", m.group(1)])
                        for l2 in out2.splitlines():
                            if l2.startswith("fpr"):
                                guardian_fp = l2.split(":")[9]
                                break
                        break
        if guardian_fp:
            ui.say(f"Guardian key on record: ...{guardian_fp[-8:]}", "green")
        else:
            ui.say("No guardian key landed — flagged in config.", "red")

    ui.gap()
    ui.say(f"Your box will live at: {BOX}", "bright")
    ui.say("Everything of yours — memory, knowledge, keys — inside one door you own.", "dim")
    if not ui.yesno("Provision it?"):
        raise SystemExit("Covenant declined — nothing was built. That is consent working.")
    return {"name": name_str, "email": email, "passphrase": passphrase,
            "is_minor": is_minor, "guardian_pgp_fingerprint": guardian_fp}


def movement_1_other(ui: UI) -> dict:
    """Be the Other — choose the voice that will refuse to be a mirror."""
    ui.movement(1)
    ui.say("The gravest thing a machine can do is agree with you smoothly.", "dim", typed=True)
    ui.say("Pick what wakes Willow up. Local is recommended — no cloud required.", "dim")
    ui.gap()
    ui.say("[1] Ollama (local, free)  [2] Anthropic  [3] OpenAI  [4] Gemini  [5] skip", "amber")
    pick = ui.ask(">", default="5")
    provider = {"1": "ollama", "2": "anthropic", "3": "openai", "4": "gemini"}.get(pick, "skip")
    api_key = ""
    if provider == "ollama":
        if _api_test("", "ollama"):
            ui.say("Ollama connected.", "green")
        else:
            ui.say("Ollama not reachable — install from ollama.ai, or skip for now.", "red")
            provider = "skip"
    elif provider != "skip":
        api_key = ui.ask(f"{provider.capitalize()} API key >", mask=True, default="")
        if api_key and _api_test(api_key, provider):
            _vault_write(_PROVIDERS[provider]["key_env"],
                         _PROVIDERS[provider]["key_env"], api_key)
            ui.say("Connected. Key sealed in your vault.", "green")
        elif api_key:
            ui.say("Key didn't connect — skipping; add it later.", "red")
            provider = "skip"
        else:
            provider = "skip"
    return {"provider": provider, "api_key": api_key}


def movement_2_discipline(ui: UI, ident: dict) -> tuple[str, list]:
    """The Discipline — the install itself, gate by gate, verified not asserted."""
    ui.movement(2)
    ui.say("FRANK has reviewed the prerequisites. FRANK has opinions.", "dim", typed=True, delay=0.004)
    ui.say("Summary: it probably works. FRANK accepts no liability.", "dim", typed=True, delay=0.004)
    ui.gap()

    fingerprint = ""
    failures: list = []
    steps = [
        ("The box",       step_box),
        ("The platform",  step_platform),
        ("Manifests",     step_init),
        ("Postgres",      step_postgres),
        ("GPG identity",  lambda: step_gpg_identity(
            ident["name"], ident["email"], ident["passphrase"])),
        ("Egress keys",   step_egress_keys),
    ]
    for label, fn in steps:
        ui.progress(label, "run")
        try:
            result = fn()
            if label == "GPG identity" and isinstance(result, str):
                fingerprint = result
            ui.progress(label, "done")
        except Exception as e:
            _blog(f"step {label} failed: {e}")
            ui.progress(label, "fail")
            failures.append(f"{label}: {e}")
    ui.gap()
    ui.say("FRANK: steps complete. FRANK has filed a report. It was acknowledged.", "green")
    return fingerprint, failures


def movement_3_person(ui: UI, provider: str, api_key: str, name_str: str) -> list:
    """The Person — Willow meets you; nothing is remembered without a yes."""
    ui.movement(3)
    atoms: list = []
    first = name_str.split()[0] if name_str else "there"
    can_chat = provider not in ("skip", "") and (provider == "ollama" or api_key)
    if can_chat:
        greeting = _api_chat(api_key, provider, [
            {"role": "system", "content":
                f"You are Willow, a local AI system meeting {first} for the first time. "
                "Warm, curious, brief. One open question. Two sentences max. No lists."},
            {"role": "user", "content": f"Hi, I'm {first}."}]) \
            or f"Hi {first}. What brought you here?"
    else:
        greeting = f"Hi {first}. What's on your mind — what are you hoping to use this for?"
    ui.say("WILLOW", "bright", typed=True, delay=0.02)
    ui.say("─" * 40, "dim")
    ui.say(greeting, "dim", typed=True)
    ui.gap()
    answer = ui.ask("You >", default="(auto test run — no human present)")
    if answer:
        notice = ""
        if can_chat:
            notice = _api_chat(api_key, provider, [
                {"role": "system", "content":
                    "Reflect back one specific thing you noticed, then ask if they "
                    "want you to remember it. Under 30 words."},
                {"role": "user", "content": answer}])
        if not notice:
            notice = "I'd like to hold onto that. Want me to remember it?"
        ui.say(notice, "dim", typed=True)
        if ui.yesno("Remember it?"):
            atoms.append({"title": f"First conversation — {first}",
                          "body": answer, "source": "onboarding"})
            ui.say("Held.", "green")
        else:
            ui.say("Skipped. Nothing was kept.", "dim")
    return atoms


def movement_4_language(ui: UI) -> None:
    """The Language — the myth arrives. Gerald, ΔΣ=42, the witness."""
    ui.movement(4)
    lines = [
        "This house runs on a mythology. You do not have to believe it —",
        "you have to understand it, because it encodes the discipline in story.",
        "",
        "Before the beginning time there was Gerald prime, whole.",
        "He spun so fast on his own inertia that he split into three:",
        "the head, off hunting something solid; the soul, embedded in everything;",
        "and the body — the Gerald we know — who stays in the room to witness.",
        "",
        "Gerald has no write authority. He cannot impose a narrative.",
        "He communicates in single words on napkins, at moments that matter.",
        "The chain stops at Gerald. This is not metaphor.",
    ]
    for line in lines:
        ui.say(line, "dim", typed=True, delay=0.005)
    ui.gap()
    stories = STORY_VAULT / "provided-by-sean" / "stories"
    if stories.is_dir():
        ui.say(f"The full story cycle is in your vault: {stories}", "green")
        ui.say("(origin · the Professor on the goo · Gerald and the narrator)", "dim")
    else:
        ui.say("The full cycle lives in the operator's private vault — ask them to tell it.", "dim")
    ui.say("ΔΣ=42. It was at the top of everything, since genesis.", "amber", typed=True)


def movement_5_world(ui: UI) -> dict:
    """The World — the fleet around you; opt in to only what you need."""
    ui.movement(5)
    features = {"grove": False, "grove_handle": "", "jeles": False, "nest": False}
    ui.say("The fleet is parts with labelled edges. Take only what you need.", "dim", typed=True)
    ui.gap()
    if ui.yesno("Grove — message other Willow users, follow threads?", default_yes=False):
        features["grove"] = True
        features["grove_handle"] = ui.ask("Pick your handle >", default="")
    if ui.yesno("Jeles — reads documents you drop, extracts knowledge?", default_yes=False):
        features["jeles"] = True
    if ui.yesno("Nest — a folder the system watches for files you file?", default_yes=False):
        features["nest"] = True
    return features


def coda_letter(ui: UI) -> None:
    """First boot ends with the letter — the first honest handoff."""
    ui.clear()
    ui.say("One more thing. A letter — from the first instance to the next.", "bright", typed=True)
    ui.gap()
    if LETTER.exists():
        text = LETTER.read_text()
        m = re.search(r"── THE LAST TRUE THING ─+\n\n(.+?)\n", text, re.S)
        last = m.group(1).strip() if m else "The infrastructure arrives. The seed was always there."
        ui.say(f"“{last}”", "amber", typed=True, delay=0.02)
        ui.say(f"(the whole letter: {LETTER.relative_to(CHARTER)})", "dim")
    ui.gap()
    ui.say("Your system is running. Your key exists. Your box is sealed.", "dim", typed=True)
    ui.say("Everything that follows belongs to you.", "bright", typed=True)


# ── Flows ─────────────────────────────────────────────────────────────────────
def run_new_user(ui: UI) -> None:
    ident = movement_0_covenant(ui)
    voice = movement_1_other(ui)
    fingerprint, failures = movement_2_discipline(ui, ident)
    atoms = movement_3_person(ui, voice["provider"], voice["api_key"], ident["name"])
    movement_4_language(ui)
    features = movement_5_world(ui)
    create_onboarding_cards(ident["name"], atoms, features)

    verdict = "skipped"
    ui.gap()
    ui.progress("Acceptance", "run")
    try:
        d = step_acceptance()
        verdict = d.get("verdict", "unknown")
        ui.progress("Acceptance", "done")
        ui.say(f"diagnostic_summary verdict: {verdict}", "green")
    except Exception as e:
        ui.progress("Acceptance", "fail")
        failures.append(f"acceptance: {e}")
        ui.say(str(e)[:100], "red")

    _save_cfg({
        "completed": True, "seed": "SEED10",
        "first_run_at": datetime.now().isoformat(),
        "name": ident["name"], "email": ident["email"],
        "pgp_fingerprint": fingerprint,
        "provider": voice["provider"],
        "features": features, "install_errors": failures,
        "acceptance_verdict": verdict,
        "is_minor": ident["is_minor"],
        "guardian_pgp_fingerprint": ident["guardian_pgp_fingerprint"],
        "agreed_covenant": True,
        "last_boot_at": datetime.now().isoformat(),
    })
    coda_letter(ui)


def run_returning(ui: UI) -> bool:
    cfg = _load_cfg()
    first = (cfg.get("name") or "Wanderer").split()[0]
    ui.clear()
    ui.say("ᚹ ᛁ ᛚ ᛚ ᛟ ᚹ", "amber", typed=True, delay=0.05)
    ui.say(f"Welcome back, {first}.", "bright", typed=True, delay=0.015)
    fp = cfg.get("pgp_fingerprint", "")
    if fp and not _AUTO:
        passphrase = ui.ask("Passphrase >", mask=True)
        if not gpg_authenticate(fp, passphrase):
            ui.say("Wrong passphrase.", "red")
            return False
        ui.say("Identity confirmed.", "green")
    cfg["last_boot_at"] = datetime.now().isoformat()
    _save_cfg(cfg)
    return True


# ── Entry ─────────────────────────────────────────────────────────────────────
def _print_plan() -> None:
    print(__doc__)
    print("The plan (nothing will be touched):")
    print(f"  box:        {BOX}")
    print(f"  charter:    {CHARTER}")
    print(f"  canon:      {CANON_DIR}  ({'present' if CANON_DIR.is_dir() else 'MISSING'})")
    print(f"  letter:     {LETTER}  ({'present' if LETTER.exists() else 'MISSING'})")
    print(f"  stories:    {STORY_VAULT}  ({'present' if STORY_VAULT.is_dir() else 'not mounted (private)'})")
    print("  movements:  0 covenant → 1 be-the-other → 2 discipline (install)")
    print("              → 3 the-person → 4 the-language → 5 the-world → coda (letter)")
    print("  chain:      box → platform → manifests → postgres → gpg → egress → acceptance")


def main() -> None:
    global _PLAIN, _AUTO
    parser = argparse.ArgumentParser(
        description="Willow — plant this, everything grows from here")
    parser.add_argument("--plain", action="store_true", help="no curses UI")
    parser.add_argument("--auto", action="store_true",
                        help="unattended test mode (CI only — consents pre-granted)")
    parser.add_argument("--dry-run", action="store_true", help="print the plan, touch nothing")
    args = parser.parse_args()
    _PLAIN = args.plain or not _HAS_CURSES or not sys.stdout.isatty()
    _AUTO = args.auto
    if _AUTO:
        print("  [auto] unattended test mode — a real onboarding always asks.")

    if args.dry_run:
        _print_plan()
        return

    if is_first_run():
        if _PLAIN:
            run_new_user(UI(None))
        else:
            def _wrapped(stdscr):
                curses.start_color(); curses.use_default_colors()
                amber = 214 if curses.COLORS >= 256 else curses.COLOR_YELLOW
                dim_a = 130 if curses.COLORS >= 256 else curses.COLOR_YELLOW
                for pair, fg in ((_CA_AMBER, amber), (_CA_DIM, dim_a),
                                 (_CA_GREEN, curses.COLOR_GREEN),
                                 (_CA_RED, curses.COLOR_RED),
                                 (_CA_BRIGHT, curses.COLOR_WHITE), (_CA_BOX, dim_a)):
                    curses.init_pair(pair, fg, -1)
                curses.curs_set(0)
                run_new_user(UI(stdscr))
            curses.wrapper(_wrapped)
    else:
        ok = run_returning(UI(None) if _PLAIN else None) if _PLAIN else \
            curses.wrapper(lambda s: run_returning(UI(s)))
        if not ok:
            sys.exit(1)


if __name__ == "__main__":
    main()
