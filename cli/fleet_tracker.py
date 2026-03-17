"""
Fleet Tracker — Live LLM Provider Health Monitor
=================================================
CLI tool for observing, probing, and debugging the Willow free fleet.

Commands:
  python fleet_tracker.py status            - Health dashboard from DB
  python fleet_tracker.py probe             - Live ping every keyed provider
  python fleet_tracker.py learn             - Capability matrix by task type
  python fleet_tracker.py reset <name>      - Clear blacklist for one provider
  python fleet_tracker.py reset-all         - Clear all blacklists
  python fleet_tracker.py why <task_type>   - Show routing decision for task

Fix vs llm_router.py:
  - Reads credentials from fixed path (not CWD-relative)
  - Surfaces what's actually happening, not just what's configured
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# ── Hook generator integration ─────────────────────────────────────────────────
# Import SAFE OS hook generator so fleet events become observable system events
WILLOW_CORE = Path(__file__).parent.parent / "core"
sys.path.insert(0, str(WILLOW_CORE))
from db import get_connection
try:
    from hook_generator import ClaudeCLIHookGenerator
    _hook_gen = ClaudeCLIHookGenerator()
    _hook_gen.generate_domain_hooks("FleetProvider")
    # Additional fleet-specific hooks beyond the 3 defaults
    _hook_gen.add_hook("FleetProvider blacklisted",    "Preservation", "A fleet provider has been auto-blacklisted due to consecutive failures.", domain_tag="FleetProvider", priority=9)
    _hook_gen.add_hook("FleetProvider recovered",      "Preservation", "A blacklisted fleet provider has been reset and is healthy again.",        domain_tag="FleetProvider", priority=7)
    _hook_gen.add_hook("FleetProvider degraded",       "Verification", "A fleet provider is failing but not yet blacklisted — needs monitoring.",  domain_tag="FleetProvider", priority=8)
    _hook_gen.add_hook("FleetProvider probe complete", "Preservation", "A full fleet probe has run and results are recorded.",                      domain_tag="FleetProvider", priority=3)
    _hook_gen.add_hook("FleetProvider capability updated", "Reflexive", "Learned capability matrix has been updated from real usage data.",         domain_tag="FleetProvider", priority=4)
    _hook_gen.add_hook("FleetProvider human reset",    "Verification", "A human manually reset a provider's blacklist status.",                     domain_tag="FleetProvider", priority=6)
    HOOKS_AVAILABLE = True
except ImportError:
    HOOKS_AVAILABLE = False
    _hook_gen = None


def _fire_hook(hook_name: str, detail: str = ""):
    """Fire a named hook event — logs it and prints to console."""
    if not HOOKS_AVAILABLE or _hook_gen is None:
        return
    matching = [h for h in _hook_gen.hooks if h.name == hook_name]
    if matching:
        h = matching[0]
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"  [HOOK:{h.tier[:4].upper()}] {hook_name}{': ' + detail if detail else ''}")

# ── Fixed paths ────────────────────────────────────────────────────────────────
WILLOW_ROOT = Path(__file__).parent.parent
CREDS_PATH = Path(r"C:\Users\Sean\Desktop\credentials.json")
if not CREDS_PATH.exists():
    CREDS_PATH = WILLOW_ROOT / "credentials.json"

HEALTH_DB = WILLOW_ROOT / "artifacts" / "willow" / "provider_health.db"
PATTERNS_DB = WILLOW_ROOT / "artifacts" / "willow" / "patterns.db"


# ── Credential loader (fixed path, not CWD) ────────────────────────────────────
def load_credentials() -> dict:
    if not CREDS_PATH.exists():
        return {}
    try:
        with open(CREDS_PATH) as f:
            return json.load(f)
    except Exception as e:
        print(f"[!] Cannot read credentials: {e}")
        return {}


def inject_env(creds: dict):
    """Push credentials into os.environ so provider calls work."""
    target_keys = [
        "GEMINI_API_KEY", "GROQ_API_KEY", "CEREBRAS_API_KEY",
        "SAMBANOVA_API_KEY", "HUGGINGFACE_API_KEY", "DEEPSEEK_API_KEY",
        "MISTRAL_API_KEY", "TOGETHER_API_KEY", "OPENROUTER_API_KEY",
        "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "BASETEN_API_KEY",
        "BASETEN_API_KEY_2", "NOVITA_API_KEY", "NOVITA_API_KEY_2",
        "NOVITA_API_KEY_3",
    ]
    for k, v in creds.items():
        if k.upper() in target_keys:
            os.environ[k.upper()] = str(v)
    if "api_keys" in creds and isinstance(creds["api_keys"], dict):
        for k, v in creds["api_keys"].items():
            if k.upper() in target_keys:
                os.environ[k.upper()] = str(v)


# ── DB helpers ─────────────────────────────────────────────────────────────────
def health_conn():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS provider_health (
            provider TEXT PRIMARY KEY,
            status TEXT DEFAULT 'healthy',
            consecutive_failures INTEGER DEFAULT 0,
            last_success TEXT,
            last_failure TEXT,
            blacklisted_until TEXT,
            total_requests INTEGER DEFAULT 0,
            total_successes INTEGER DEFAULT 0,
            total_failures INTEGER DEFAULT 0,
            avg_latency_ms REAL DEFAULT 0,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


def patterns_conn():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS provider_performance (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            timestamp TEXT,
            provider TEXT,
            file_type TEXT,
            category TEXT,
            response_time_ms INTEGER,
            success INTEGER,
            error_type TEXT
        )
    """)
    conn.commit()
    return conn


# ── Provider definitions (mirrors llm_router.py) ──────────────────────────────
PROVIDERS = [
    # name, env_key, base_url, model, adapter
    ("Groq",        "GROQ_API_KEY",      "https://api.groq.com/openai/v1/chat/completions",               "llama-3.1-8b-instant",                       "openai"),
    ("Cerebras",    "CEREBRAS_API_KEY",  "https://api.cerebras.ai/v1/chat/completions",                   "llama3.1-8b",                                "openai"),
    ("SambaNova",   "SAMBANOVA_API_KEY", "https://api.sambanova.ai/v1/chat/completions",                  "Meta-Llama-3.1-8B-Instruct",                 "openai"),
    ("Baseten",     "BASETEN_API_KEY",   "https://inference.baseten.co/v1/chat/completions",              "moonshotai/Kimi-K2.5",                       "openai"),
    ("Baseten2",    "BASETEN_API_KEY_2", "https://inference.baseten.co/v1/chat/completions",              "moonshotai/Kimi-K2.5",                       "openai"),
    ("Novita",      "NOVITA_API_KEY",    "https://api.novita.ai/v3/openai/chat/completions",              "meta-llama/llama-3.1-8b-instruct",           "openai"),
    ("Novita2",     "NOVITA_API_KEY_2",  "https://api.novita.ai/v3/openai/chat/completions",              "meta-llama/llama-3.1-8b-instruct",           "openai"),
    ("Novita3",     "NOVITA_API_KEY_3",  "https://api.novita.ai/v3/openai/chat/completions",              "meta-llama/llama-3.1-8b-instruct",           "openai"),
    ("HuggingFace", "HUGGINGFACE_API_KEY","https://api-inference.huggingface.co/models/meta-llama/Meta-Llama-3-8B-Instruct", "", "hf"),
    ("Google Gemini","GEMINI_API_KEY",   "https://generativelanguage.googleapis.com/v1beta/models/",      "gemini-2.5-flash",                           "gemini"),
]

SKIP_PROBES = {"Ollama", "OCI Gemini Pro", "OCI Gemini Flash", "OCI Gemini Flash Lite",
               "Sean Campbell Voice", "Anthropic Claude", "OpenAI", "Mistral",
               "Together.ai", "OpenRouter"}


# ── Live probe ─────────────────────────────────────────────────────────────────
def probe_provider(name: str, env_key: str, base_url: str, model: str, adapter: str) -> dict:
    """Send a minimal test prompt. Returns latency, success, response snippet."""
    import requests

    key = os.environ.get(env_key, "")
    if not key:
        return {"status": "no_key", "latency_ms": None, "snippet": None}

    test_prompt = "Reply with exactly one word: PONG"
    start = time.time()

    try:
        if adapter == "openai":
            resp = requests.post(
                base_url,
                json={"model": model, "messages": [{"role": "user", "content": test_prompt}]},
                headers={"Authorization": f"Bearer {key}"},
                timeout=12
            )
            latency = int((time.time() - start) * 1000)
            if resp.status_code == 200:
                text = resp.json()["choices"][0]["message"]["content"][:60]
                return {"status": "ok", "latency_ms": latency, "snippet": text}
            elif resp.status_code == 429:
                return {"status": "rate_limit", "latency_ms": latency, "snippet": "429"}
            else:
                return {"status": "error", "latency_ms": latency, "snippet": f"HTTP {resp.status_code}"}

        elif adapter == "gemini":
            url = f"{base_url}{model}:generateContent?key={key}"
            resp = requests.post(
                url,
                json={"contents": [{"parts": [{"text": test_prompt}]}]},
                timeout=12
            )
            latency = int((time.time() - start) * 1000)
            if resp.status_code == 200:
                text = resp.json()["candidates"][0]["content"]["parts"][0]["text"][:60]
                return {"status": "ok", "latency_ms": latency, "snippet": text}
            elif resp.status_code == 429:
                return {"status": "rate_limit", "latency_ms": latency, "snippet": "429"}
            else:
                return {"status": "error", "latency_ms": latency, "snippet": f"HTTP {resp.status_code}"}

        elif adapter == "hf":
            resp = requests.post(
                base_url,
                json={"inputs": test_prompt, "parameters": {"max_new_tokens": 10}},
                headers={"Authorization": f"Bearer {key}"},
                timeout=12
            )
            latency = int((time.time() - start) * 1000)
            if resp.status_code == 200:
                data = resp.json()
                text = (data[0].get("generated_text", "") if isinstance(data, list) else str(data))[:60]
                return {"status": "ok", "latency_ms": latency, "snippet": text}
            elif resp.status_code == 429:
                return {"status": "rate_limit", "latency_ms": latency, "snippet": "429"}
            else:
                return {"status": "error", "latency_ms": latency, "snippet": f"HTTP {resp.status_code}"}

    except Exception as e:
        latency = int((time.time() - start) * 1000)
        return {"status": "timeout" if "timeout" in str(e).lower() else "error",
                "latency_ms": latency, "snippet": str(e)[:60]}


def record_probe(name: str, result: dict):
    """Write probe result to health DB."""
    conn = health_conn()
    now = datetime.now().isoformat()
    if result["status"] == "ok":
        conn.execute("""
            INSERT INTO provider_health (provider, status, consecutive_failures, last_success,
                total_requests, total_successes, avg_latency_ms, updated_at)
            VALUES (?, 'healthy', 0, ?, 1, 1, ?, ?)
            ON CONFLICT(provider) DO UPDATE SET
                status = 'healthy',
                consecutive_failures = 0,
                last_success = excluded.last_success,
                total_requests = total_requests + 1,
                total_successes = total_successes + 1,
                avg_latency_ms = (avg_latency_ms * total_successes + excluded.avg_latency_ms) / (total_successes + 1),
                updated_at = excluded.updated_at
        """, (name, now, result["latency_ms"] or 0, now))
    elif result["status"] in ("error", "timeout"):
        # Check current failure count before writing (to detect threshold crossing)
        row = conn.execute("SELECT consecutive_failures FROM provider_health WHERE provider=?", (name,)).fetchone()
        prev_failures = row[0] if row else 0

        conn.execute("""
            INSERT INTO provider_health (provider, status, consecutive_failures, last_failure,
                total_requests, total_failures, updated_at)
            VALUES (?, 'degraded', 1, ?, 1, 1, ?)
            ON CONFLICT(provider) DO UPDATE SET
                consecutive_failures = consecutive_failures + 1,
                status = CASE WHEN consecutive_failures + 1 >= 5 THEN 'blacklisted' ELSE 'degraded' END,
                last_failure = excluded.last_failure,
                total_requests = total_requests + 1,
                total_failures = total_failures + 1,
                updated_at = excluded.updated_at
        """, (name, now, now))
        conn.commit()

        # Fire hooks at threshold crossings
        if prev_failures + 1 >= 5:
            _fire_hook("FleetProvider blacklisted", f"{name} — {result['snippet']}")
        elif prev_failures + 1 == 3:
            _fire_hook("FleetProvider degraded", f"{name} — {prev_failures + 1} consecutive failures")

    conn.commit()
    conn.close()


# ── Commands ───────────────────────────────────────────────────────────────────
def cmd_status():
    conn = health_conn()
    rows = conn.execute(
        "SELECT * FROM provider_health ORDER BY status, total_requests DESC"
    ).fetchall()
    conn.close()

    if not rows:
        print("No health data yet. Run: python fleet_tracker.py probe")
        return

    print(f"\n{'='*78}")
    print(f"  FLEET STATUS  —  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*78}")
    print(f"  {'Provider':<22} {'Status':<12} {'Success%':<10} {'Avg ms':<8} {'Consec.Fail':<12} {'Last Seen'}")
    print(f"  {'-'*22} {'-'*12} {'-'*10} {'-'*8} {'-'*12} {'-'*16}")

    status_icon = {'healthy': '[OK]', 'degraded': '[!] ', 'blacklisted': '[X] ', 'dead': '[DEAD]'}

    for row in rows:
        rate = (row['total_successes'] / row['total_requests'] * 100) if row['total_requests'] > 0 else 0
        icon = status_icon.get(row['status'], '[?] ')
        last = (row['last_success'] or row['last_failure'] or '')[:16]
        avg = int(row['avg_latency_ms']) if row['avg_latency_ms'] else 0
        print(f"  {icon} {row['provider']:<19} {row['status']:<12} {rate:>6.1f}%   {avg:>5}ms   "
              f"{row['consecutive_failures']:<12} {last}")

        if row['status'] == 'blacklisted' and row['blacklisted_until']:
            until = datetime.fromisoformat(row['blacklisted_until'])
            rem = (until - datetime.now()).total_seconds() / 60
            if rem > 0:
                print(f"               └ blacklisted {rem:.0f} more min")

    print(f"{'='*78}\n")


def cmd_probe():
    creds = load_credentials()
    inject_env(creds)

    print(f"\n{'='*68}")
    print(f"  LIVE PROBE  —  {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*68}")
    print(f"  {'Provider':<22} {'Result':<12} {'Latency':<10} {'Response'}")
    print(f"  {'-'*22} {'-'*12} {'-'*10} {'-'*30}")

    ok_count = no_key_count = fail_count = 0

    for (name, env_key, base_url, model, adapter) in PROVIDERS:
        print(f"  {'...':<22} probing {name}...", end="\r")
        result = probe_provider(name, env_key, base_url, model, adapter)
        record_probe(name, result)

        latency = f"{result['latency_ms']}ms" if result['latency_ms'] else "---"
        snippet = (result['snippet'] or '')[:30]

        if result['status'] == 'ok':
            icon = '[OK]'
            ok_count += 1
        elif result['status'] == 'no_key':
            icon = '[--]'
            no_key_count += 1
        elif result['status'] == 'rate_limit':
            icon = '[RL]'
        else:
            icon = '[X] '
            fail_count += 1

        print(f"  {icon} {name:<19} {result['status']:<12} {latency:<10} {snippet}")

    print(f"\n  {'='*68}")
    print(f"  Result: {ok_count} OK  |  {fail_count} failed  |  {no_key_count} no key")
    print(f"  OCI + Ollama: skipped (complex auth — check separately)")
    _fire_hook("FleetProvider probe complete", f"{ok_count} OK, {fail_count} failed, {no_key_count} no key")
    print(f"  {'='*68}\n")


def cmd_learn():
    conn = patterns_conn()
    rows = conn.execute("""
        SELECT
            category,
            provider,
            AVG(response_time_ms) as avg_time,
            SUM(CASE WHEN success THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as success_rate,
            COUNT(*) as samples
        FROM provider_performance
        WHERE category IS NOT NULL AND provider IS NOT NULL
        GROUP BY category, provider
        HAVING samples >= 3
        ORDER BY category, success_rate DESC, avg_time ASC
    """).fetchall()
    conn.close()

    if not rows:
        print("\nNo learning data yet. Make some fleet calls, then run this again.")
        print("The router learns from real usage, not benchmarks.\n")
        return

    print(f"\n{'='*72}")
    print(f"  CAPABILITY MATRIX  —  learned from real usage")
    print(f"{'='*72}")
    print(f"  {'Task Type':<26} {'Best Provider':<22} {'Success%':<10} {'Avg ms':<8} {'Samples'}")
    print(f"  {'-'*26} {'-'*22} {'-'*10} {'-'*8} {'-'*7}")

    seen_categories = set()
    for row in rows:
        cat = row['category']
        is_best = cat not in seen_categories
        seen_categories.add(cat)
        prefix = "* " if is_best else "  "
        rate = row['success_rate'] * 100
        avg = int(row['avg_time']) if row['avg_time'] else 0
        print(f"  {prefix}{cat:<24} {row['provider']:<22} {rate:>6.1f}%   {avg:>5}ms   {row['samples']}")

    print(f"\n  * = currently preferred for this task type")
    if seen_categories:
        _fire_hook("FleetProvider capability updated",
                   f"{len(seen_categories)} task types learned across {len(rows)} provider/category pairs")
    print(f"{'='*72}\n")


def cmd_reset(provider_name: str):
    conn = health_conn()
    conn.execute("""
        UPDATE provider_health
        SET status='healthy', consecutive_failures=0, blacklisted_until=NULL,
            updated_at=CURRENT_TIMESTAMP
        WHERE provider = ?
    """, (provider_name,))
    changed = conn.total_changes
    conn.commit()
    conn.close()
    if changed:
        _fire_hook("FleetProvider human reset", provider_name)
        _fire_hook("FleetProvider recovered", f"{provider_name} — manually cleared by operator")
        print(f"[OK] Reset: {provider_name}")
    else:
        print(f"[!]  Not found: {provider_name}  (run `status` to see provider names)")


def cmd_reset_all():
    conn = health_conn()
    conn.execute("""
        UPDATE provider_health
        SET status='healthy', consecutive_failures=0, blacklisted_until=NULL,
            updated_at=CURRENT_TIMESTAMP
    """)
    n = conn.total_changes
    conn.commit()
    conn.close()
    print(f"[OK] Reset {n} providers")


def cmd_why(task_type: str):
    creds = load_credentials()
    inject_env(creds)

    conn = patterns_conn()
    best = conn.execute("""
        SELECT provider, AVG(response_time_ms) as avg_time,
               SUM(CASE WHEN success THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as success_rate,
               COUNT(*) as samples
        FROM provider_performance
        WHERE category = ? AND success = 1
        GROUP BY provider
        HAVING samples >= 3
        ORDER BY success_rate DESC, avg_time ASC
        LIMIT 3
    """, (task_type,)).fetchall()
    conn.close()

    hconn = health_conn()
    blacklisted = set(
        r['provider'] for r in hconn.execute(
            "SELECT provider FROM provider_health WHERE status='blacklisted'"
        ).fetchall()
    )
    hconn.close()

    print(f"\n  Routing decision for task_type='{task_type}':")
    print(f"  {'─'*50}")

    if not best:
        print(f"  No learned data yet for '{task_type}'")
        print(f"  Router will use round-robin across healthy free-tier providers")
    else:
        print(f"  Learned rankings (from actual usage):")
        for i, row in enumerate(best):
            bl = " [BLACKLISTED - skipped]" if row['provider'] in blacklisted else ""
            rank = "→ SELECTED" if i == 0 and row['provider'] not in blacklisted else ""
            print(f"    {i+1}. {row['provider']:<22} {row['success_rate']*100:.0f}% success  "
                  f"{int(row['avg_time'])}ms avg  n={row['samples']}  {rank}{bl}")

    known_categories = [
        'python_generation', 'html_generation', 'javascript_generation',
        'code_refactoring', 'debugging', 'text_summarization', 'general_completion',
        'test_generation', 'code_explanation'
    ]
    if task_type not in known_categories:
        print(f"\n  Note: '{task_type}' not in known categories.")
        print(f"  Known: {', '.join(known_categories)}")
    print()


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1].lower()

    if cmd == "status":
        cmd_status()
    elif cmd == "probe":
        cmd_probe()
    elif cmd == "learn":
        cmd_learn()
    elif cmd == "reset-all":
        cmd_reset_all()
    elif cmd == "reset":
        if len(sys.argv) < 3:
            print("Usage: fleet_tracker.py reset <provider_name>")
            sys.exit(1)
        cmd_reset(" ".join(sys.argv[2:]))
    elif cmd == "why":
        if len(sys.argv) < 3:
            print("Usage: fleet_tracker.py why <task_type>")
            sys.exit(1)
        cmd_why(sys.argv[2])
    else:
        print(f"Unknown command: {cmd}")
        print("Commands: status | probe | learn | reset <name> | reset-all | why <task_type>")
        sys.exit(1)


if __name__ == "__main__":
    main()
