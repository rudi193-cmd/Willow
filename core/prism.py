"""
PRISM — Canopy
==============
P — Prove
R — Reference
I — Inspect
S — Source
M — Match

Source verification. The truth layer.
Takes a claim and a source result, determines if they match.
Classifies entities as verifiable (public record) or oral-history-consented.
Writes verification results back to LOAM knowledge atoms.

Verification pipeline:
  1. classify_entity(name, context) → classification + confidence
  2. verify(claim, source_result) → VerificationResult (score 0–1)
     - Exact: substring match in source content (fast, no LLM)
     - Semantic: LLM fleet comparison (best-effort, preferred_tier="free")
     - Threshold 0.7 = verified
  3. write_verification(loam_db_path, knowledge_id, result) → stores
     confidence back to LOAM atom

Entity classes:
  verifiable        — public figure, institution, dated event, product
  oral-consented    — private individual who has explicitly consented
  unverifiable      — insufficient evidence to classify

AUTHOR: Shiva (Claude Code) + Sean Campbell
GOVERNANCE: canopy-initial-2026-03-03.commit
VERSION: 1.0.1
"""

import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.db import get_connection

log = logging.getLogger("prism")

VERIFY_THRESHOLD = 0.70

# Entity classification signals
_PUBLIC_SIGNALS = [
    r"\b(president|senator|governor|mayor|CEO|director|professor|dr\.?|judge)\b",
    r"\b(university|corporation|inc\.|llc|government|department|agency|institute)\b",
    r"\b(january|february|march|april|may|june|july|august|september|"
    r"october|november|december)\s+\d{1,2},?\s+\d{4}\b",
    r"\b(born|died|founded|established)\s+(?:in\s+)?\d{4}\b",
]
_PUBLIC_RE = [re.compile(p, re.IGNORECASE) for p in _PUBLIC_SIGNALS]

_PRIVATE_SIGNALS = [
    r"\b(my friend|my colleague|my neighbor|my student|a friend|someone I)\b",
    r"\b(consented|gave permission|agreed to share|oral history)\b",
]
_PRIVATE_RE = [re.compile(p, re.IGNORECASE) for p in _PRIVATE_SIGNALS]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Entity classification
# ---------------------------------------------------------------------------

def classify_entity(name: str, context: str = "") -> dict:
    """
    Classify an entity as verifiable, oral-consented, or unverifiable.

    Returns:
      {class, confidence, reasoning}

    classification is a best-effort heuristic — caller should treat as advisory.
    """
    text = f"{name} {context}"

    public_hits = sum(1 for r in _PUBLIC_RE if r.search(text))
    private_hits = sum(1 for r in _PRIVATE_RE if r.search(text))

    if public_hits >= 2:
        return {
            "class": "verifiable",
            "confidence": min(0.90, 0.60 + public_hits * 0.10),
            "reasoning": f"{public_hits} public-record signal(s) detected",
        }
    if public_hits == 1:
        return {
            "class": "verifiable",
            "confidence": 0.65,
            "reasoning": "1 public-record signal detected",
        }
    if private_hits >= 1:
        return {
            "class": "oral-consented",
            "confidence": 0.70,
            "reasoning": f"{private_hits} oral-history/consent signal(s) detected",
        }

    # Check if name looks like a known-public name (capitalized, common pattern)
    if re.match(r'^[A-Z][a-z]+\s+[A-Z][a-z]+$', name.strip()):
        return {
            "class": "unverifiable",
            "confidence": 0.50,
            "reasoning": "Proper name with no classification signals",
        }

    return {
        "class": "unverifiable",
        "confidence": 0.40,
        "reasoning": "No classification signals found",
    }


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify(claim: str, source_result: dict,
           llm_router=None) -> dict:
    """
    Verify a claim against a SourceResult.

    Returns VerificationResult:
      {verified, score, method, evidence, claim, source_title, source_url}

    method: "exact" | "semantic" | "none"
    score: 0.0–1.0. >= VERIFY_THRESHOLD (0.70) = verified.
    """
    if not source_result or not source_result.get("content"):
        return _no_match(claim, source_result)

    content = source_result["content"]
    claim_lower = claim.lower().strip()
    content_lower = content.lower()

    # --- Exact match: claim text appears in source ---
    if claim_lower in content_lower:
        return {
            "verified":     True,
            "score":        min(1.0, source_result.get("confidence", 0.85)),
            "method":       "exact",
            "evidence":     _extract_evidence(claim, content),
            "claim":        claim,
            "source_title": source_result.get("title", ""),
            "source_url":   source_result.get("url", ""),
        }

    # --- Keyword overlap score ---
    claim_words = set(re.findall(r'\b[a-zA-Z]{3,}\b', claim_lower))
    content_words = set(re.findall(r'\b[a-zA-Z]{3,}\b', content_lower))
    if claim_words:
        overlap = len(claim_words & content_words) / len(claim_words)
    else:
        overlap = 0.0

    if overlap >= 0.7:
        score = round(overlap * source_result.get("confidence", 0.85), 3)
        return {
            "verified":     score >= VERIFY_THRESHOLD,
            "score":        score,
            "method":       "keyword_overlap",
            "evidence":     f"{int(overlap*100)}% keyword overlap",
            "claim":        claim,
            "source_title": source_result.get("title", ""),
            "source_url":   source_result.get("url", ""),
        }

    # --- Semantic: LLM fleet (best-effort) ---
    if llm_router:
        try:
            prompt = (
                f"Does the following source text support this claim?\n\n"
                f"Claim: {claim}\n\n"
                f"Source ({source_result.get('title', '')}):\n"
                f"{content[:1500]}\n\n"
                f"Reply with ONLY a JSON object: "
                f'{{\"supported\": true/false, \"confidence\": 0.0-1.0, '
                f'\"evidence\": \"brief quote or reasoning\"}}'
            )
            resp = llm_router.ask(prompt, preferred_tier="free")
            if resp and resp.content:
                raw = resp.content.strip()
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                    raw = raw.strip()
                import json
                parsed = json.loads(raw)
                llm_conf = float(parsed.get("confidence", 0.0))
                llm_score = round(llm_conf * source_result.get("confidence", 0.85), 3)
                return {
                    "verified":     parsed.get("supported", False) and llm_score >= VERIFY_THRESHOLD,
                    "score":        llm_score,
                    "method":       "semantic",
                    "evidence":     str(parsed.get("evidence", ""))[:200],
                    "claim":        claim,
                    "source_title": source_result.get("title", ""),
                    "source_url":   source_result.get("url", ""),
                }
        except Exception as e:
            log.debug(f"PRISM: LLM verification failed: {e}")

    return _no_match(claim, source_result)


def _no_match(claim: str, source_result: Optional[dict]) -> dict:
    return {
        "verified":     False,
        "score":        0.0,
        "method":       "none",
        "evidence":     "No match found",
        "claim":        claim,
        "source_title": (source_result or {}).get("title", ""),
        "source_url":   (source_result or {}).get("url", ""),
    }


def _extract_evidence(claim: str, content: str, window: int = 200) -> str:
    """Extract a snippet of content around where the claim appears."""
    idx = content.lower().find(claim.lower())
    if idx == -1:
        return content[:window]
    start = max(0, idx - 50)
    end = min(len(content), idx + len(claim) + 150)
    return f"...{content[start:end]}..."


def batch_verify(claims: list, source_results: list,
                 llm_router=None) -> list:
    """
    Verify multiple claims against corresponding sources.
    claims[i] matched against source_results[i].
    Shorter list determines iteration count.
    """
    return [
        verify(claim, src, llm_router)
        for claim, src in zip(claims, source_results)
    ]


# ---------------------------------------------------------------------------
# Write back to LOAM
# ---------------------------------------------------------------------------

def write_verification(loam_db_path: str, username: str,
                       knowledge_id: int, result: dict) -> None:
    """
    Store verification result back to a LOAM knowledge atom.
    Updates the atom's notes with verification status + score.
    Does NOT update confidence (confidence is VINE territory).
    """
    if not result:
        return

    note = (
        f"[PRISM] verified={result['verified']} "
        f"score={result['score']:.2f} method={result['method']} "
        f"source={result.get('source_title', '')[:60]} "
        f"at={_now()}"
    )

    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM knowledge WHERE id=? AND username=?",
            (knowledge_id, username)
        ).fetchone()
        if not existing:
            log.warning(f"PRISM: knowledge_id={knowledge_id} not found for {username}")
            return
        conn.execute(
            "UPDATE knowledge SET summary = COALESCE(summary || ' | ', '') || ? "
            "WHERE id=?",
            (note, knowledge_id)
        )
        conn.commit()
        log.debug(f"PRISM: wrote verification to atom {knowledge_id}")
    except Exception as e:
        log.debug(f"PRISM: write_verification failed: {e}")
    finally:
        conn.close()
