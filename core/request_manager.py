"""
Request Manager — Rate limiting queue + response cache for LLM calls.

Wraps llm_router.ask() with:
1. Per-provider sliding window rate limiting (no more 429s)
2. Response cache with TTL (identical prompts reuse last response)

Usage:
    from core.request_manager import ask
    response = ask("your prompt", preferred_tier="free")
"""

import hashlib
import logging
import threading
import time
from collections import deque
from pathlib import Path
from typing import Optional

log = logging.getLogger("request_manager")

# Provider RPM limits (requests per minute)
PROVIDER_RPM = {
    "Groq": 30,
    "Cerebras": 30,
    "Google Gemini": 15,
    "SambaNova": 10,
    "HuggingFace Inference": 5,
    "Mistral": 1,
    "Ollama": 999,
    "Anthropic Claude": 50,
    "OpenAI": 60,
}

# Sliding window: track timestamps of recent requests per provider
_windows: dict[str, deque] = {name: deque() for name in PROVIDER_RPM}
_window_lock = threading.Lock()

# Response cache: {prompt_hash: (response_obj, timestamp, hits)}
_cache: dict = {}
_cache_lock = threading.Lock()

# Stats
_stats = {
    "cache_hits": 0,
    "cache_misses": 0,
    "queue_waits": 0,
    "provider_calls": {}
}
_stats_lock = threading.Lock()


def _hash_prompt(prompt: str) -> str:
    """Normalize and hash a prompt for cache key."""
    return hashlib.sha256(prompt.strip().lower().encode()).hexdigest()


def _cache_get(prompt_hash: str, ttl: int):
    """Return cached response if valid, else None."""
    with _cache_lock:
        entry = _cache.get(prompt_hash)
        if entry is None:
            return None
        response, timestamp, hits = entry
        if time.time() - timestamp > ttl:
            del _cache[prompt_hash]
            return None
        # Update hit count
        _cache[prompt_hash] = (response, timestamp, hits + 1)
        return response


def _cache_put(prompt_hash: str, response):
    """Store response in cache."""
    with _cache_lock:
        _cache[prompt_hash] = (response, time.time(), 0)


def _evict_cache(max_entries: int = 1000):
    """Remove oldest entries if cache grows too large."""
    with _cache_lock:
        if len(_cache) > max_entries:
            # Sort by timestamp, remove oldest 20%
            sorted_keys = sorted(_cache.keys(),
                                key=lambda k: _cache[k][1])
            for k in sorted_keys[:max_entries // 5]:
                del _cache[k]


def _can_call(provider: str) -> bool:
    """Check if provider is under its RPM limit."""
    rpm = PROVIDER_RPM.get(provider, 10)
    now = time.time()
    with _window_lock:
        window = _windows.get(provider, deque())
        # Remove timestamps older than 60 seconds
        while window and now - window[0] > 60:
            window.popleft()
        return len(window) < rpm


def _record_call(provider: str):
    """Record a call timestamp for rate limiting."""
    now = time.time()
    with _window_lock:
        if provider not in _windows:
            _windows[provider] = deque()
        _windows[provider].append(now)


def _wait_until_available(provider: str, timeout: int = 60) -> bool:
    """Block until provider is under rate limit. Returns False on timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _can_call(provider):
            return True
        rpm = PROVIDER_RPM.get(provider, 10)
        wait = max(0.5, 60 / rpm)  # minimum wait based on rate
        log.debug(f"{provider} rate limited, waiting {wait:.1f}s")
        time.sleep(wait)
    return False


def ask(prompt: str, preferred_tier: str = "free",
        use_cache: bool = True, cache_ttl: int = 300):
    """
    Route prompt through rate-limited, cached LLM mesh.

    Args:
        prompt: The prompt to send
        preferred_tier: "free", "cheap", or "paid"
        use_cache: Return cached response if available
        cache_ttl: Cache TTL in seconds (default 5 minutes)

    Returns:
        RouterResponse (same as llm_router.ask) or None
    """
    try:
        from core import llm_router
    except ImportError:
        import llm_router

    # 1. Check cache
    if use_cache:
        prompt_hash = _hash_prompt(prompt)
        cached = _cache_get(prompt_hash, cache_ttl)
        if cached is not None:
            with _stats_lock:
                _stats["cache_hits"] += 1
            log.debug(f"Cache hit for prompt ({len(prompt)} chars)")
            return cached

    with _stats_lock:
        _stats["cache_misses"] += 1

    # 2. Get available providers in priority order
    available = llm_router.get_available_providers()
    priority = []
    if preferred_tier in available:
        priority.extend(available[preferred_tier])
    if preferred_tier != "free": priority.extend(available.get("free", []))
    if preferred_tier != "cheap": priority.extend(available.get("cheap", []))
    if preferred_tier != "paid": priority.extend(available.get("paid", []))

    # Separate Ollama (local fallback)
    cloud = [p for p in priority if p.name != "Ollama"]
    ollama = [p for p in priority if p.name == "Ollama"]

    # 3. Find first non-rate-limited provider
    response = None
    for provider in cloud:
        if _can_call(provider.name):
            _record_call(provider.name)
            with _stats_lock:
                _stats["provider_calls"][provider.name] = \
                    _stats["provider_calls"].get(provider.name, 0) + 1
            response = llm_router.ask(prompt, preferred_tier=preferred_tier)
            if response:
                break
        else:
            log.debug(f"{provider.name} at rate limit, skipping")

    # 4. If all cloud providers rate-limited, queue on best option
    if response is None and cloud:
        with _stats_lock:
            _stats["queue_waits"] += 1
        # Wait for whichever provider clears first
        for provider in cloud:
            log.info(f"All providers busy, queuing on {provider.name}...")
            if _wait_until_available(provider.name, timeout=30):
                _record_call(provider.name)
                response = llm_router.ask(prompt, preferred_tier=preferred_tier)
                if response:
                    break

    # 5. Last resort: Ollama
    if response is None and ollama:
        log.info("All cloud providers exhausted, using Ollama")
        _record_call("Ollama")
        response = llm_router.ask(prompt, preferred_tier="free")

    # 6. Cache the result
    if response and use_cache:
        _cache_put(prompt_hash, response)
        _evict_cache()

    return response


def get_stats() -> dict:
    """Return request manager statistics."""
    with _stats_lock:
        stats = dict(_stats)

    # Add current rate limit status
    now = time.time()
    rate_status = {}
    with _window_lock:
        for provider, window in _windows.items():
            recent = sum(1 for t in window if now - t < 60)
            limit = PROVIDER_RPM.get(provider, 10)
            rate_status[provider] = {
                "calls_last_minute": recent,
                "limit": limit,
                "available": recent < limit
            }
    stats["rate_status"] = rate_status
    stats["cache_size"] = len(_cache)
    return stats


def clear_cache():
    """Clear the response cache."""
    with _cache_lock:
        _cache.clear()
    log.info("Response cache cleared")
