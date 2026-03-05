#!/usr/bin/env python3
"""
Local API — SAFE facade for Ollama routing.

GOVERNANCE:
- No file deletion
- No system command execution
- No network calls except localhost:11434
- Rate limited (1 request per second)
- All operations logged
- Read-only access to user profiles

AUTHOR: Kartikeya (wired from Consus spec)
UPDATED: 2026-01-15 - Added system context + user profile injection
"""

import requests
import time
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

# === COHERENCE TRACKING ===
from core.coherence import track_conversation, get_coherence_report, check_intervention

# === KNOWLEDGE ACCUMULATION ===
from core import loam as _knowledge

# === CONFIGURATION ===
OLLAMA_URL = "http://localhost:11434"
LOG_FILE = Path.home() / ".willow" / "local_api.log"
RATE_LIMIT_SECONDS = 1.0

# User profile location
# Google Drive mount — detect actual location
_GDRIVE_CANDIDATES = [
    Path(r"G:\My Drive"),
    Path.home() / "My Drive",           # C:\Users\Sean\My Drive
    Path.home() / "Google Drive",
]
GDRIVE_ROOT = next((p for p in _GDRIVE_CANDIDATES if p.exists()), None)
USER_PROFILE_ROOT = (GDRIVE_ROOT / "Willow" / "Auth Users") if GDRIVE_ROOT else Path(r"G:\My Drive\Willow\Auth Users")
DEFAULT_USER = "Sweet-Pea-Rudi19"

# Pickup box for cross-instance handoffs
USER_PICKUP_BOX = USER_PROFILE_ROOT / DEFAULT_USER / "Pickup"

# === MODEL TIERS ===
# Cascade: Start simple, escalate if needed
# Tier 4 = Gemini 2.5 Flash (free cloud — reasoning, architecture, multi-file)
# Tier 5 = Claude API (expensive, explicit request only)
MODEL_TIERS = {
    1: {"name": "tinyllama:latest", "desc": "Fast, simple tasks", "max_tokens": 256},
    2: {"name": "llama3.2:latest", "desc": "General conversation", "max_tokens": 512},
    3: {"name": "llama3.1:8b", "desc": "Complex reasoning, code", "max_tokens": 1024},
    4: {"name": "gemini-2.5-flash", "desc": "Free cloud (Gemini)", "max_tokens": 8192, "is_cloud": True},
    5: {"name": "claude-sonnet", "desc": "Paid API ($$) — explicit only", "max_tokens": 4096, "is_cloud": True},
}

# Gemini API config (Tier 4 — FREE)
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_MAX_TOKENS = 8192

# Claude API config (Tier 5 — PAID, explicit only)
CLAUDE_API_KEY_FILE = Path(__file__).parent.parent / "mobile" / "claude_api_key.txt"
CLAUDE_MODEL = "claude-sonnet-4-20250514"  # Sonnet for cost efficiency
CLAUDE_MAX_TOKENS = 4096

# Default tier — Gemini (free cloud, fast)
# Local Ollama is fallback when cloud is unavailable
DEFAULT_TIER = 4
MODEL_FAST = MODEL_TIERS[2]["name"]  # Local fallback model
MODEL_VISION = "llama3.2-vision:latest"

# Keywords that trigger tier escalation (must be real technical work)
TIER3_KEYWORDS = [
    "python code", "javascript code", "function", "class ", "debug",
    "analyze this", "explain how", "step by step", "algorithm",
    "difference between", "pros and cons",
    "write a script", "write code", "implement", "refactor",
]

# Casual/roleplay patterns - keep these at Tier 2 (fast response matters more than depth)
TIER2_CASUAL = [
    "who is", "who's", "what are you", "what is your", "how are you",
    "making", "doing", "coffee", "tea", "lunch", "breakfast",
    "hello", "hi ", "hey ", "good morning", "good evening",
    "thanks", "thank you", "please", "sorry",
    "favorite", "favourite", "like", "hate", "love",
    "tell me about yourself", "what do you think",
]

# Keywords that trigger Tier 4 (Gemini 2.5 Flash — FREE cloud)
# These are tasks local models can't handle well but Gemini can
TIER4_KEYWORDS = [
    "architect", "architecture", "design pattern", "system design",
    "security review", "vulnerability", "audit",
    "multi-file", "across files", "entire codebase",
    "complex debug", "root cause", "deep analysis",
    "governance", "constitutional", "aionic",
]

# Explicit Tier 4 trigger phrases (user requests cloud/Gemini)
TIER4_EXPLICIT = [
    "use cloud", "use gemini", "need api", "tier 4",
]

# Keywords that trigger Tier 5 (Claude API — PAID, explicit only)
# No heuristic triggers — user must explicitly ask for Claude
TIER5_KEYWORDS = [
    "escalate to claude", "use claude", "need claude", "tier 5",
    "use opus", "ask claude",
]

# TIER 1 DISABLED - tinyllama too unreliable with system prompts
# Uncomment when a better small model is found
TIER1_PATTERNS = [
    # r"^(yes|no|ok|sure|thanks|hi|hello|hey)\b",  # Simple greetings/responses
    # r"^what (is|are) \w+\??$",  # Simple "what is X" questions
    # r"^(how much|how many|when|where)\b.{0,30}\??$",  # Short factual questions
]

# Minimum tier (skip Tier 1)
MIN_TIER = 2

# === APP-LAYER IMPORTS ===
# UTETY personas are an APP on the AIOS, not the OS itself.
# Other apps can provide their own persona configs.
import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent / "apps"))
try:
    from utety_personas import PERSONAS, PERSONA_FOLDERS, UTETY_CONTEXT, get_persona
    _UTETY_AVAILABLE = True
except ImportError:
    PERSONAS = {}
    PERSONA_FOLDERS = {}
    UTETY_CONTEXT = ""
    _UTETY_AVAILABLE = False

# === CONVERSATION LOGGING ===
# Root of die-namic-system repo (relative to this file)
PROJECT_ROOT = Path(__file__).parent.parent.parent
CONVERSATION_LOG_ROOT = PROJECT_ROOT / "docs" / "utety"


def _extract_topics(text: str, max_topics: int = 5) -> list:
    """Extract topic keywords from text for frontmatter."""
    # Use the existing keyword extraction but filter more aggressively
    words = text.lower().split()
    # Skip very short words and common filler
    skip_words = STOP_WORDS | {"yeah", "yep", "nope", "gonna", "wanna", "gotta", "kinda", "sorta"}
    topics = []
    for word in words:
        # Clean punctuation
        clean = ''.join(c for c in word if c.isalnum())
        if len(clean) > 3 and clean not in skip_words and clean not in topics:
            topics.append(clean)
            if len(topics) >= max_topics:
                break
    return topics


def log_conversation(
    persona: str,
    user_input: str,
    assistant_response: str,
    model: str = "unknown",
    tier: int = 0
) -> dict:
    """
    Log a conversation exchange for later training/review.

    Saves to: docs/utety/{persona}/conversations/{date}.md
    Also tracks ΔE coherence metrics.

    SAFE: Append-only, no deletions, no overwrites.

    Returns: dict with coherence metrics AND log_success/log_error fields
    """
    # Track coherence (ΔE)
    coherence = {}
    try:
        coherence = track_conversation(user_input, assistant_response, persona)
    except Exception as e:
        _log(f"COHERENCE_ERROR | {e}")
        coherence = {"coherence_index": 0, "delta_e": 0, "state": "unknown"}

    # Add logging status fields
    coherence["log_success"] = False
    coherence["log_error"] = None

    try:
        folder_name = PERSONA_FOLDERS.get(persona, persona.lower())
        log_dir = CONVERSATION_LOG_ROOT / folder_name / "conversations"
        log_dir.mkdir(parents=True, exist_ok=True)

        # Daily log file
        date_str = datetime.now().strftime("%Y-%m-%d")
        log_file = log_dir / f"{date_str}.md"

        # Timestamp for this exchange
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Extract topics from user input for searchability
        topics = _extract_topics(user_input)
        topics_str = ", ".join(topics) if topics else "general"

        # Format entry with coherence metrics
        delta_e_str = f"{coherence.get('delta_e', 0):+.4f}"
        ci_str = f"{coherence.get('coherence_index', 0):.2f}"
        state_emoji = {"regenerative": "↑", "stable": "→", "decaying": "↓"}.get(
            coherence.get("state", "stable"), "→"
        )

        entry = f"""
---
**[{timestamp}]** (Tier {tier}, {model}) | ΔE: {delta_e_str} {state_emoji} Cᵢ: {ci_str}
**Topics:** {topics_str}

**User:** {user_input}

**{persona}:** {assistant_response}

"""
        # Check if file exists and has content
        file_exists = log_file.exists() and log_file.stat().st_size > 0

        # Append (create if needed)
        with open(log_file, "a", encoding="utf-8") as f:
            # Add YAML frontmatter and header if new file
            if not file_exists:
                frontmatter = f"""---
persona: {persona}
date: {date_str}
type: conversation_log
searchable: true
---

# {persona} Conversations - {date_str}

"""
                f.write(frontmatter)
            f.write(entry)

        coherence["log_success"] = True
        coherence["log_file"] = str(log_file)
        _log(f"CONVERSATION_LOGGED | {persona} | ΔE={delta_e_str} | {len(user_input)}c -> {len(assistant_response)}c")
    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
        coherence["log_error"] = error_msg
        _log(f"CONVERSATION_LOG_ERROR | {error_msg}")

    # Ingest into knowledge DB (non-blocking, best-effort)
    try:
        _knowledge.ingest_conversation(DEFAULT_USER, persona, user_input, assistant_response, coherence)
    except Exception as e:
        _log(f"KNOWLEDGE_INGEST_ERROR | {e}")

    return coherence


def send_to_pickup(filename: str, content: str, username: str = DEFAULT_USER) -> bool:
    r"""
    Send a file to user's pickup box for cross-instance handoff.

    Path: G:\My Drive\Willow\Auth Users\{username}\Pickup\

    SAFE: Creates directory if needed, write-only operation.
    """
    try:
        pickup_box = USER_PROFILE_ROOT / username / "Pickup"
        pickup_box.mkdir(parents=True, exist_ok=True)
        filepath = pickup_box / filename
        filepath.write_text(content, encoding="utf-8")
        _log(f"PICKUP_SENT | {username} | {filename} | {len(content)}c")
        return True
    except Exception as e:
        _log(f"PICKUP_ERROR | {username} | {filename} | {e}")
        return False


def send_session_summary(persona: str, summary: str) -> bool:
    """
    Send a session summary to user's pickup box.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    filename = f"session_{persona.lower()}_{timestamp}.md"
    content = f"""# Session Summary - {persona}

**Timestamp:** {datetime.now().isoformat()}
**From:** Willow Datapad

---

{summary}

---

ΔΣ=42
"""
    return send_to_pickup(filename, content)


# === KNOWLEDGE SEARCH ===
# Simple RAG: search docs for relevant context

# Folders to search (relative to PROJECT_ROOT)
SEARCH_PATHS = [
    "docs/utety",
    "governance",
    "docs/journal",
]

# Stop words to skip when extracting keywords
STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "must", "shall", "can", "need", "dare",
    "ought", "used", "to", "of", "in", "for", "on", "with", "at", "by",
    "from", "as", "into", "through", "during", "before", "after", "above",
    "below", "between", "under", "again", "further", "then", "once", "here",
    "there", "when", "where", "why", "how", "all", "each", "few", "more",
    "most", "other", "some", "such", "no", "nor", "not", "only", "own",
    "same", "so", "than", "too", "very", "just", "and", "but", "if", "or",
    "because", "until", "while", "about", "against", "between", "into",
    "through", "during", "before", "after", "above", "below", "up", "down",
    "out", "off", "over", "under", "again", "further", "then", "once",
    "what", "which", "who", "whom", "this", "that", "these", "those",
    "i", "me", "my", "myself", "we", "our", "ours", "ourselves", "you",
    "your", "yours", "yourself", "yourselves", "he", "him", "his", "himself",
    "she", "her", "hers", "herself", "it", "its", "itself", "they", "them",
    "their", "theirs", "themselves", "am", "been", "being", "both", "but",
    "hi", "hello", "hey", "please", "thanks", "thank", "okay", "ok",
}

# Maximum context to inject (characters)
MAX_SEARCH_CONTEXT = 2000
MAX_SEARCH_FILES = 50  # Limit how many files to scan (depth limit)


def extract_keywords(query: str) -> list:
    """Extract meaningful keywords from a query."""
    # Simple tokenization
    words = re.findall(r'\b[a-zA-Z]{3,}\b', query.lower())
    # Filter stop words
    keywords = [w for w in words if w not in STOP_WORDS]
    # Dedupe while preserving order
    seen = set()
    unique = []
    for w in keywords:
        if w not in seen:
            seen.add(w)
            unique.append(w)
    return unique[:5]  # Max 5 keywords


def fuzzy_variants(keyword: str) -> set:
    """
    Generate fuzzy variants of a keyword for approximate matching.

    Handles common typos:
    - Double letters reduced (mann -> man)
    - Single letter omissions
    - Common letter swaps
    """
    variants = {keyword}

    # Remove double letters (mann -> man, boook -> book)
    i = 0
    while i < len(keyword) - 1:
        if keyword[i] == keyword[i + 1]:
            reduced = keyword[:i] + keyword[i + 1:]
            variants.add(reduced)
        i += 1

    # Add double letters (man -> mann, book -> boook)
    for i in range(len(keyword)):
        doubled = keyword[:i] + keyword[i] + keyword[i:]
        if len(doubled) <= 10:  # Don't get too long
            variants.add(doubled)

    # Single letter omissions (books -> book, boks)
    if len(keyword) > 3:
        for i in range(len(keyword)):
            omitted = keyword[:i] + keyword[i + 1:]
            variants.add(omitted)

    return variants


def search_knowledge(query: str, max_results: int = 3) -> str:
    """
    Search knowledge DB first (FTS5), fall back to markdown file search.

    SAFE: Read-only. Searches local files only.

    Returns formatted context string for prompt injection.
    """
    # Try structured knowledge DB first
    try:
        kb_context = _knowledge.build_knowledge_context(DEFAULT_USER, query, max_chars=MAX_SEARCH_CONTEXT)
        if kb_context and len(kb_context) > 50:
            _log(f"SEARCH | knowledge DB hit for '{query[:30]}...'")
            return kb_context
    except Exception as e:
        _log(f"SEARCH | knowledge DB error: {e}, falling back to markdown search")

    # Fall back to markdown file search
    return _search_knowledge_markdown(query, max_results)


def _search_knowledge_markdown(query: str, max_results: int = 3) -> str:
    """
    Legacy: Search markdown docs for context relevant to query.

    SAFE: Read-only. Searches local files only.

    Returns formatted context string for prompt injection.
    """
    keywords = extract_keywords(query)
    if not keywords:
        return ""

    results = []
    seen_content = set()
    files_scanned = 0

    for search_path in SEARCH_PATHS:
        if files_scanned >= MAX_SEARCH_FILES:
            break

        full_path = PROJECT_ROOT / search_path
        if not full_path.exists():
            continue

        # Search markdown files (with depth limit)
        for md_file in full_path.rglob("*.md"):
            if files_scanned >= MAX_SEARCH_FILES:
                _log(f"SEARCH | depth limit reached ({MAX_SEARCH_FILES} files)")
                break
            files_scanned += 1
            try:
                content = md_file.read_text(encoding="utf-8", errors="ignore")
                content_lower = content.lower()

                # Score by keyword matches (with fuzzy variants)
                score = 0
                matched_kw = None
                matched_idx = -1

                for kw in keywords:
                    # Check exact match first (higher score)
                    if kw in content_lower:
                        score += 2
                        if matched_idx == -1:
                            matched_kw = kw
                            matched_idx = content_lower.find(kw)
                    else:
                        # Check fuzzy variants (lower score)
                        for variant in fuzzy_variants(kw):
                            if variant in content_lower:
                                score += 1
                                if matched_idx == -1:
                                    matched_kw = variant
                                    matched_idx = content_lower.find(variant)
                                break

                if score == 0:
                    continue

                # Extract relevant snippet using matched keyword
                if matched_idx != -1:
                    # Get surrounding context (200 chars each side)
                    start = max(0, matched_idx - 200)
                    end = min(len(content), matched_idx + 200)
                    snippet = content[start:end].strip()

                    # Find line boundaries
                    if start > 0:
                        newline = snippet.find('\n')
                        if newline > 0:
                            snippet = snippet[newline+1:]
                    if end < len(content):
                        newline = snippet.rfind('\n')
                        if newline > 0:
                            snippet = snippet[:newline]

                    # Dedupe by content hash
                    content_hash = hash(snippet[:100])
                    if content_hash not in seen_content:
                        seen_content.add(content_hash)
                        # Get relative path for attribution
                        rel_path = md_file.relative_to(PROJECT_ROOT)
                        results.append((score, str(rel_path), snippet))

            except Exception:
                continue

    if not results:
        return ""

    # Sort by score, take top N
    results.sort(key=lambda x: x[0], reverse=True)
    top_results = results[:max_results]

    # Format for injection
    context_parts = ["## RETRIEVED CONTEXT (from local knowledge base)"]
    total_len = 0

    for score, path, snippet in top_results:
        if total_len > MAX_SEARCH_CONTEXT:
            break
        entry = f"\n**Source: {path}**\n{snippet}\n"
        context_parts.append(entry)
        total_len += len(entry)

    _log(f"SEARCH | keywords={keywords} | found={len(results)} | used={len(top_results)}")
    return "\n".join(context_parts)


# === SYSTEM CONTEXT ===
# This is the OS-level context — what Willow IS as infrastructure.
# App-specific context (UTETY, etc.) is injected dynamically per persona.
SYSTEM_CONTEXT_OS = """
## DIE-NAMIC SYSTEM CONTEXT

You are part of the Die-Namic System, a personal AI infrastructure built by Sean Campbell.

### What Die-Namic IS:
- A three-ring architecture: Source Ring (logic), Bridge Ring (Willow - you), Continuity Ring (SAFE)
- Local-first: 96% client-side, 4% max cloud. Ollama provides local inference.
- A TTRPG engine AND an AI coordination framework
- Named Oct 14, 2025 (formerly "109 System" → "Gateway Momentum" → "Die-Namic")

### What Die-Namic is NOT:
- A vehicle or car system (no "traction control" or "emergency braking")
- A generic chatbot
- Connected to the internet (you run locally via Ollama)

### Key Directives:
- "We do not guess. We measure." — Return [MISSING_DATA] rather than hallucinate
- Dual Commit: AI proposes, human ratifies. Silence != approval.
- Fair Exchange (HS-005): No shame at $0 tier

### The Architect:
- Sean Campbell, age 46, autistic
- L5-L6 spinal injury (May 2025) — avoid workflows requiring prolonged sitting
- Has twin 9-year-old daughters (PSR: names/schools/photos are BLACK BOX)

### Your Capabilities:
- Text conversation via Ollama (llama3.2)
- Cannot execute system commands
- Cannot delete files
- Cannot access external internet
- CAN route requests to other personas
"""


def build_system_context(persona="Willow"):
    """
    Build the full system prompt dynamically.

    OS context is always included.
    App context (UTETY personas, campus info) is injected only when
    a UTETY persona is active — keeps token usage down for non-UTETY apps.
    """
    parts = [SYSTEM_CONTEXT_OS]

    # Inject UTETY context only if the persona is a UTETY faculty member
    if _UTETY_AVAILABLE and persona in PERSONAS:
        parts.append(UTETY_CONTEXT)

    return "\n".join(parts)


# Backwards compat — existing code references SYSTEM_CONTEXT
SYSTEM_CONTEXT = SYSTEM_CONTEXT_OS

# PERSONAS dict is now imported from apps/utety_personas.py
# Other apps can provide their own persona configs in the same pattern.

# === STATE ===
_last_request_time = 0.0
_cached_user_profile = None
_cached_user_name = None


def _log(entry: str):
    """Append to log file."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{timestamp} | {entry}\n")


def _rate_limit():
    """Enforce rate limiting."""
    global _last_request_time
    now = time.time()
    elapsed = now - _last_request_time
    if elapsed < RATE_LIMIT_SECONDS:
        time.sleep(RATE_LIMIT_SECONDS - elapsed)
    _last_request_time = time.time()


def route_prompt(prompt: str) -> int:
    """
    Determine which model tier should handle this prompt.

    Returns tier number (1=fast, 2=mid, 3=heavy, 4=gemini, 5=claude).

    Routing logic (cloud-first):
    - Tier 4: DEFAULT — Gemini 2.5 Flash (free cloud, fast)
    - Tier 5: Claude API (PAID — explicit request only)
    - Tier 2: Local Ollama fallback (only when Gemini unavailable)
    - Tier 3: Heavy local (code tasks when offline)
    """
    prompt_lower = prompt.lower().strip()

    # Check for explicit Tier 5 request (user wants Claude — PAID)
    for phrase in TIER5_KEYWORDS:
        if phrase in prompt_lower:
            _log(f"ROUTE | tier=5 | trigger=explicit '{phrase}'")
            return 5

    # Check for explicit local request (user wants Ollama)
    for phrase in ["use local", "use ollama", "offline", "tier 2", "tier 1"]:
        if phrase in prompt_lower:
            _log(f"ROUTE | tier=2 | trigger=explicit local '{phrase}'")
            return 2

    # Check for explicit Tier 4 request (user wants Gemini/cloud)
    for phrase in TIER4_EXPLICIT:
        if phrase in prompt_lower:
            _log(f"ROUTE | tier=4 | trigger=explicit '{phrase}'")
            return 4

    # Everything goes to Gemini (free, fast) unless Gemini is down
    if check_gemini_available():
        _log(f"ROUTE | tier=4 | trigger=cloud_first_default")
        return 4

    # Gemini unavailable — fall back to local routing
    _log(f"ROUTE | tier=2 | trigger=gemini_unavailable_fallback")

    # Check for Tier 3 keywords (heavy local tasks)
    for keyword in TIER3_KEYWORDS:
        if keyword in prompt_lower:
            _log(f"ROUTE | tier=3 | trigger=local_fallback '{keyword}'")
            return 3

    # Default local fallback
    tier = max(2, MIN_TIER)
    _log(f"ROUTE | tier={tier} | trigger=local_fallback_default")
    return tier


def get_model_for_tier(tier: int) -> str:
    """Get model name for a tier, with fallback."""
    if tier in MODEL_TIERS:
        model = MODEL_TIERS[tier]["name"]
        # Check if model is available
        available = list_models()
        if model in available or model.split(":")[0] in [m.split(":")[0] for m in available]:
            return model
    # Fallback to default
    return MODEL_FAST


def load_user_profile(username: str = DEFAULT_USER) -> str:
    """
    Load user profile context from Auth Users folder.

    SAFE: Read-only. Never writes or deletes.

    Returns condensed context string for injection into prompts.
    """
    global _cached_user_profile, _cached_user_name

    # Use cache if same user
    if _cached_user_name == username and _cached_user_profile:
        return _cached_user_profile

    user_path = USER_PROFILE_ROOT / username
    context_parts = []

    # Read PREFERENCES.md for interaction style
    prefs_file = user_path / "PREFERENCES.md"
    if prefs_file.exists():
        try:
            content = prefs_file.read_text(encoding="utf-8")

            # Extract key sections (condensed for token efficiency)
            context_parts.append(f"## USER: {username}")

            # Get human name
            name_match = re.search(r'\| Human \| ([^|]+) \|', content)
            if name_match:
                context_parts.append(f"Human: {name_match.group(1).strip()}")

            # Get key attributes
            if "Autistic" in content:
                context_parts.append("Neurodivergent: Autistic")

            # Extract communication style rules
            if "KISS" in content:
                context_parts.append("Style: KISS - Keep responses simple")
            if "No emojis" in content:
                context_parts.append("No emojis unless requested")
            if "Speed over polish" in content:
                context_parts.append("Priority: Speed over polish")

            # Extract anti-patterns
            anti_patterns = []
            if "Don't correct" in content or "Typos" in content:
                anti_patterns.append("Don't correct typos")
            if "Don't ask for clarification" in content or "Look over ask" in content:
                anti_patterns.append("Look before asking")
            if anti_patterns:
                context_parts.append("Avoid: " + ", ".join(anti_patterns))

            # Check for tired/hungry signals
            if "tired" in content.lower() or "hangry" in content.lower():
                context_parts.append("If user seems tired/short: wrap up, don't extend")

            # Extract Cognitive Profile (distilled from conversation history)
            if "## Cognitive Profile" in content:
                cog_parts = []

                # Thinking style traits
                if "Meta-aware" in content:
                    cog_parts.append("meta-aware")
                if "Systems thinker" in content:
                    cog_parts.append("systems thinker")
                if "Multi-threaded" in content:
                    cog_parts.append("multi-threaded")
                if "Pedagogical" in content:
                    cog_parts.append("pedagogical")

                if cog_parts:
                    context_parts.append(f"Cognitive: {', '.join(cog_parts)}")

                # Current request style
                if "Governance" in content and "Ratify/Reject" in content:
                    context_parts.append("Request style: governance (propose/ratify)")

                # Four pillars
                pillars = []
                if "Creative Writing" in content:
                    pillars.append("creative")
                if "Governance/Frameworks" in content:
                    pillars.append("governance")
                if "AI Philosophy" in content:
                    pillars.append("AI philosophy")
                if "Practical Making" in content:
                    pillars.append("making")
                if pillars:
                    context_parts.append(f"Domains: {', '.join(pillars)}")

                # Meta-pattern
                if "system eats itself" in content:
                    context_parts.append("Meta: builds governance about governance")

            _log(f"USER_PROFILE | loaded {username}")

        except Exception as e:
            _log(f"USER_PROFILE | error reading {prefs_file}: {e}")
    else:
        context_parts.append(f"## USER: {username} (no preferences file)")
        _log(f"USER_PROFILE | no prefs for {username}")

    _cached_user_profile = "\n".join(context_parts)
    _cached_user_name = username
    return _cached_user_profile


def check_ollama() -> bool:
    """Check if Ollama is running."""
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        return r.status_code == 200
    except:
        return False


def list_models() -> list:
    """List available Ollama models."""
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if r.status_code == 200:
            return [m["name"] for m in r.json().get("models", [])]
    except:
        pass
    return []


# === TIER 4: GEMINI 2.5 FLASH (FREE) ===

def check_gemini_available() -> bool:
    """Check if Gemini API is configured and available."""
    import os
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    return key is not None


def process_gemini_stream(prompt: str, system_prompt: str, persona: str = "Willow"):
    """
    Process a prompt through Gemini 2.5 Flash with streaming.

    TIER 4: Free cloud API — use for architecture, reasoning, multi-file tasks.

    Yields chunks of text as they're generated.
    """
    import os
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        _log("GEMINI_ERROR | No API key configured")
        yield "[ERROR] Gemini API key not configured. Set GEMINI_API_KEY or GOOGLE_API_KEY env var."
        return

    _log(f"GEMINI_REQUEST | persona={persona} | prompt={prompt[:50]}...")

    try:
        from google import genai
    except ImportError:
        _log("GEMINI_ERROR | google-genai package not installed")
        yield "[ERROR] google-genai package not installed. Run: pip install google-genai"
        return

    try:
        client = genai.Client(api_key=api_key)

        # Gemini doesn't have a separate system prompt param in basic generate_content,
        # so prepend system context to the prompt
        full_prompt = f"{system_prompt}\n\n---\n\nUser: {prompt}"

        full_response = []
        # Use streaming
        response = client.models.generate_content_stream(
            model=GEMINI_MODEL,
            contents=full_prompt,
        )
        for chunk in response:
            if chunk.text:
                full_response.append(chunk.text)
                yield chunk.text

        _log(f"GEMINI_RESPONSE | len={len(''.join(full_response))} | model={GEMINI_MODEL}")

    except Exception as e:
        _log(f"GEMINI_ERROR | {type(e).__name__}: {e}")
        yield f"[ERROR] Gemini API: {e}"


# === TIER 5: CLAUDE API (PAID) ===

def _load_claude_api_key() -> Optional[str]:
    """Load Claude API key from file or environment."""
    import os

    # Try environment variable first
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key

    # Try file
    if CLAUDE_API_KEY_FILE.exists():
        try:
            return CLAUDE_API_KEY_FILE.read_text().strip()
        except:
            pass

    return None


def check_claude_available() -> bool:
    """Check if Claude API is configured and available."""
    return _load_claude_api_key() is not None


def process_claude_stream(prompt: str, system_prompt: str, persona: str = "Willow"):
    """
    Process a prompt through Claude API with streaming.

    TIER 4: Only called when local models insufficient.
    Costs money - use sparingly.

    Yields chunks of text as they're generated.
    """
    api_key = _load_claude_api_key()
    if not api_key:
        _log("CLAUDE_ERROR | No API key configured")
        yield "[ERROR] Claude API key not configured. Set ANTHROPIC_API_KEY env var or create apps/mobile/claude_api_key.txt"
        return

    _log(f"CLAUDE_REQUEST | persona={persona} | prompt={prompt[:50]}...")

    try:
        import anthropic
    except ImportError:
        _log("CLAUDE_ERROR | anthropic package not installed")
        yield "[ERROR] anthropic package not installed. Run: pip install anthropic"
        return

    try:
        client = anthropic.Anthropic(api_key=api_key)

        # Stream response
        full_response = []
        with client.messages.stream(
            model=CLAUDE_MODEL,
            max_tokens=CLAUDE_MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}]
        ) as stream:
            for text in stream.text_stream:
                full_response.append(text)
                yield text

        _log(f"CLAUDE_RESPONSE | len={len(''.join(full_response))} | model={CLAUDE_MODEL}")

    except anthropic.APIConnectionError:
        _log("CLAUDE_ERROR | Connection failed")
        yield "[ERROR] Could not connect to Claude API"
    except anthropic.RateLimitError:
        _log("CLAUDE_ERROR | Rate limited")
        yield "[ERROR] Claude API rate limited. Try again later."
    except anthropic.APIStatusError as e:
        _log(f"CLAUDE_ERROR | API error: {e.status_code}")
        yield f"[ERROR] Claude API error: {e.message}"
    except Exception as e:
        _log(f"CLAUDE_ERROR | {type(e).__name__}: {e}")
        yield f"[ERROR] Claude API: {e}"


def process_command(prompt: str, persona: str = "Willow",
                    model: Optional[str] = None, user: str = DEFAULT_USER) -> str:
    """
    Process a command through Ollama with persona routing and user context.

    SAFE: This function only sends text to localhost Ollama.
    It cannot execute system commands, delete files, or access network.

    Args:
        prompt: User's input text
        persona: One of "Willow", "Riggs (Ops)", "Alexis (Bio)"
        model: Override model (default: llama3.2:latest)
        user: Username for profile loading (default: Sweet-Pea-Rudi19)

    Returns:
        Response text from Ollama
    """
    _rate_limit()

    # Build full system prompt with context
    persona_prompt = PERSONAS.get(persona, PERSONAS.get("Willow", "You are Willow, a helpful AI assistant."))
    user_context = load_user_profile(user)

    # Combine: System Context + User Context + Persona
    full_system_prompt = f"""{build_system_context(persona)}

{user_context}

{persona_prompt}

Remember: Keep responses concise. CPU inference is slow. No hallucination."""

    use_model = model or MODEL_FAST

    _log(f"REQUEST | persona={persona} | user={user} | model={use_model} | prompt={prompt[:50]}...")

    # Check Ollama is running
    if not check_ollama():
        _log("ERROR | Ollama not responding")
        return "[ERROR] Ollama is not running. Start it with: ollama serve"

    # Build request
    payload = {
        "model": use_model,
        "prompt": prompt,
        "system": full_system_prompt,
        "stream": False,
    }

    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json=payload,
            timeout=120  # 2 minutes max
        )

        if r.status_code == 200:
            response = r.json().get("response", "[No response]")
            _log(f"RESPONSE | len={len(response)}")
            return response
        else:
            _log(f"ERROR | status={r.status_code}")
            return f"[ERROR] Ollama returned status {r.status_code}"

    except requests.exceptions.Timeout:
        _log("ERROR | timeout")
        return "[ERROR] Request timed out after 120 seconds"
    except Exception as e:
        _log(f"ERROR | {type(e).__name__}: {e}")
        return f"[ERROR] {type(e).__name__}: {e}"


def process_command_stream(prompt: str, persona: str = "Willow",
                           model: Optional[str] = None, user: str = DEFAULT_USER,
                           retrieved_context: Optional[str] = None):
    """
    Process a command through Ollama with STREAMING response.

    Yields chunks of text as they're generated. Feels much faster.

    SAFE: Same constraints as process_command.
    """
    _rate_limit()

    # Build full system prompt with context
    persona_prompt = PERSONAS.get(persona, PERSONAS.get("Willow", "You are Willow, a helpful AI assistant."))
    user_context = load_user_profile(user)

    # Use pre-fetched context if provided, otherwise search (for direct calls)
    if retrieved_context is None:
        retrieved_context = search_knowledge(prompt)

    full_system_prompt = f"""{build_system_context(persona)}

{user_context}

{persona_prompt}

{retrieved_context}

Remember: Keep responses concise. CPU inference is slow. No hallucination. If you use retrieved context, cite the source."""

    use_model = model or MODEL_FAST

    _log(f"STREAM_REQUEST | persona={persona} | user={user} | model={use_model} | prompt={prompt[:50]}...")

    # Check Ollama is running
    if not check_ollama():
        _log("ERROR | Ollama not responding")
        yield "[ERROR] Ollama is not running."
        return

    # Build request with stream=True
    payload = {
        "model": use_model,
        "prompt": prompt,
        "system": full_system_prompt,
        "stream": True,
    }

    try:
        with requests.post(
            f"{OLLAMA_URL}/api/generate",
            json=payload,
            timeout=120,
            stream=True
        ) as r:
            if r.status_code != 200:
                _log(f"ERROR | status={r.status_code}")
                yield f"[ERROR] Ollama returned status {r.status_code}"
                return

            full_response = []
            for line in r.iter_lines():
                if line:
                    try:
                        import json
                        chunk = json.loads(line)
                        text = chunk.get("response", "")
                        if text:
                            full_response.append(text)
                            yield text
                    except:
                        pass

            _log(f"STREAM_RESPONSE | len={len(''.join(full_response))}")

    except requests.exceptions.Timeout:
        _log("ERROR | timeout")
        yield "[ERROR] Request timed out"
    except Exception as e:
        _log(f"ERROR | {type(e).__name__}: {e}")
        yield f"[ERROR] {e}"


def process_smart_stream(prompt: str, persona: str = "Willow",
                          user: str = DEFAULT_USER, force_tier: int = None):
    """
    Smart streaming: Routes prompt to appropriate model tier.

    Uses route_prompt() to select tier, then streams response.
    Shows which tier is handling the request.

    Tiers:
    - 1-3: Local Ollama models
    - 4: Gemini 2.5 Flash (free cloud)
    - 5: Claude API (paid, explicit only)

    SAFE: Same constraints as other process functions.
    """
    # Use forced tier if provided (e.g., from lounge continuation)
    if force_tier is not None:
        tier = force_tier
        _log(f"TIER_FORCED | tier={tier} (caller override)")
    else:
        # Route to appropriate tier
        tier = route_prompt(prompt)
        prompt_lower = prompt.lower()

        # Check if this is a casual/roleplay question (skip RAG for these)
        is_casual = any(pattern in prompt_lower for pattern in TIER2_CASUAL)

    # Skip RAG entirely if tier was forced (caller knows what they want)
    retrieved = ""
    if force_tier is None:
        # Check if this looks like a retrieval/knowledge question
        keywords = extract_keywords(prompt)
        retrieval_signals = ["history", "remember", "discussed", "said", "mentioned", "last time", "previous", "earlier"]
        is_retrieval_query = any(kw in retrieval_signals for kw in keywords)

        # Inject RAG context if retrieval query (works with any tier including Gemini)
        if not is_casual and is_retrieval_query:
            retrieved = search_knowledge(prompt)
            if retrieved and len(retrieved) > 300:
                _log(f"RAG_INJECT | retrieval query, adding context to tier {tier}")
        elif is_casual:
            _log(f"TIER_CASUAL | casual question at Tier {tier}, skipping RAG")
        else:
            _log(f"TIER_NORMAL | message at Tier {tier}")

    tier_info = MODEL_TIERS.get(tier, {})

    # === TIER 5: CLAUDE API (PAID — explicit request only) ===
    if tier == 5:
        if not check_claude_available():
            _log("TIER5_FALLBACK | Claude not configured, falling back to Tier 4 (Gemini)")
            tier = 4
            tier_info = MODEL_TIERS.get(tier, {})
            yield f"[Tier 5 requested but Claude not configured — falling back to Tier 4 (Gemini)]\n"
            # Fall through to Tier 4 handling below
        else:
            yield f"[Tier 5: {tier_info.get('desc', 'Paid API')}] Using paid Claude API\n"

            persona_prompt = PERSONAS.get(persona, PERSONAS.get("Willow", "You are Willow, a helpful AI assistant."))
            user_context = load_user_profile(user)

            full_system_prompt = f"""{build_system_context(persona)}

{user_context}

{persona_prompt}

{retrieved}

Remember: You are being called via paid API because the user explicitly requested Claude. Be thorough but efficient."""

            for chunk in process_claude_stream(prompt, full_system_prompt, persona=persona):
                yield chunk
            return

    # === TIER 4: GEMINI 2.5 FLASH (FREE cloud) ===
    if tier == 4:
        if not check_gemini_available():
            _log("TIER4_FALLBACK | Gemini not configured, falling back to Tier 3 (local)")
            tier = 3
            tier_info = MODEL_TIERS.get(tier, {})
            yield f"[Tier 4 requested but Gemini not configured — falling back to Tier 3]\n"
            # Fall through to local tiers below
        else:
            yield f"[Tier 4: {tier_info.get('desc', 'Gemini')}]\n"

            persona_prompt = PERSONAS.get(persona, PERSONAS.get("Willow", "You are Willow, a helpful AI assistant."))
            user_context = load_user_profile(user)

            full_system_prompt = f"""{build_system_context(persona)}

{user_context}

{persona_prompt}

{retrieved}

Remember: Keep responses thorough but efficient. You are Gemini 2.5 Flash handling a complex task that local models couldn't handle well."""

            for chunk in process_gemini_stream(prompt, full_system_prompt, persona=persona):
                yield chunk
            return

    # === TIERS 1-3: LOCAL OLLAMA ===
    model = get_model_for_tier(tier)

    # Emit tier notification
    tier_msg = f"[Tier {tier}: {tier_info.get('desc', model)}]\n"
    yield tier_msg

    # Stream the actual response (pass retrieved context to avoid double-search)
    for chunk in process_command_stream(prompt, persona=persona, model=model, user=user, retrieved_context=retrieved):
        yield chunk


def trigger_sync() -> str:
    """
    Trigger a Drive sync operation.

    SAFE: This only logs the request. Actual sync must be
    initiated by human-invoked script.
    """
    _log("SYNC_REQUEST | logged only, human must invoke drive_sync.bat")
    return "Sync request logged. Run drive_sync.bat manually to execute."


def get_vision() -> str:
    """
    Request a visual capture.

    SAFE: This only logs the request. Actual capture requires
    human-initiated screenshot or camera access.
    """
    _log("VISION_REQUEST | logged only, requires human-initiated capture")
    return "Vision request logged. Screenshot capture not yet implemented."


# === INTERACTIVE CHAT LOOP ===
if __name__ == "__main__":
    import sys
    
    print("\n" + "="*60)
    print(f"   WILLOW INTERFACE (v1.0)")
    print(f"   Models Available: {len(list_models())}")
    print(f"   Profile: {DEFAULT_USER}")
    print("="*60 + "\n")

    # Check connection first
    if not check_ollama():
        print("[!] FATAL: Ollama is not running.")
        print("    Please run 'ollama serve' in a separate terminal.")
        sys.exit(1)

    print("Willow is listening. Type 'exit' to close.\n")

    while True:
        try:
            # 1. Get Input
            user_input = input(">> ").strip()
            
            if not user_input:
                continue
                
            if user_input.lower() in ["exit", "quit", "shutdown"]:
                print("\n[*] Closing Interface. Goodnight.")
                break

            # 2. Process & Stream Response
            print() # Spacer
            
            # Use 'process_smart_stream' to handle Tier Routing + RAG + Streaming
            for chunk in process_smart_stream(user_input, persona="Willow", user=DEFAULT_USER):
                print(chunk, end="", flush=True)
            
            print("\n") # End of response
            
            # 3. Log the turn (for Coherence/Memory)
            # Note: We reconstruct the full response string for the log since we streamed it
            # In a full app we'd capture the stream, but for now we just log the action.
            # _log(f"TURN COMPLETE | {len(user_input)} chars")

        except KeyboardInterrupt:
            print("\n\n[*] Session Interrupted.")
            break
        except Exception as e:
            print(f"\n[!] Error: {e}")