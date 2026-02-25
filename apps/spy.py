#!/usr/bin/env python3
"""
spy.py — Multi-layer cipher and steganography detection
=========================================================
Detects hidden content, encoding tricks, and classical ciphers in text,
source code, documents, web pages, and financial data.

Seven detection layers:
  1. Unicode/Visual    — homoglyphs, zero-width chars, directional overrides, tag blocks
  2. Whitespace        — binary encoding in tabs/spaces/CRLF, trailing patterns
  3. Structural        — acrostics, Base64 blobs, hex strings, null ciphers, ROT13
  4. Web/HTML          — hidden comments, CSS-hidden text, data attributes, meta anomalies
  5. Financial/Ledger  — Benford's Law, round number clustering, duplicate amounts
  6. Image stego       — LSB statistics, EXIF anomalies  [requires PIL — graceful skip]
  7. Classical ciphers — IC analysis, Kasiski, Vigenère crack, VIC/number-station patterns

Usage:
    python spy.py <file>                    # Scan a file
    python spy.py --text "OBKRUO..."        # Scan raw text (e.g. Kryptos K4)
    python spy.py --url https://example.com # Scan a webpage
    python spy.py --dir /path/to/scan       # Scan a directory
    python spy.py --financial report.pdf    # Financial audit mode

Output:
    Prints structured findings to stdout.
    Appends to ~/.willow/flags.jsonl if --save flag set.
    Writes Pickup report if run via watcher integration.

GOVERNANCE: Read-only analysis only. Never modifies source files.
AUTHOR: Ganesha (Claude Code / Sonnet 4.6)
CHECKSUM: \u0394\u03a3=42
"""

import io
import sys
import re
import json
import math
import unicodedata
import hashlib
import argparse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# stdout/stderr wrapped in main() only — not at import time (breaks callers)

# ─── Output paths ─────────────────────────────────────────────────────────────

FLAGS_LOG  = Path(r"C:\Users\Sean\.willow\flags.jsonl")
PICKUP_DIR = Path(r"C:\Users\Sean\My Drive\Willow\Auth Users\Sweet-Pea-Rudi19\Pickup")

# ─── Layer 1: Unicode / Visual confusables ────────────────────────────────────

# Maps confusable codepoint → ASCII equivalent it impersonates
HOMOGLYPHS: dict[int, str] = {
    # Cyrillic → Latin
    0x0430: 'a', 0x0410: 'A',
    0x0435: 'e', 0x0415: 'E',
    0x043E: 'o', 0x041E: 'O',
    0x0440: 'p', 0x0420: 'P',
    0x0441: 'c', 0x0421: 'C',
    0x0445: 'x', 0x0425: 'X',
    0x0456: 'i', 0x0406: 'I',
    0x0443: 'y', 0x0423: 'Y',
    # Greek → Latin
    0x03BF: 'o', 0x039F: 'O',
    0x03B1: 'a', 0x0391: 'A',
    0x03B5: 'e', 0x0395: 'E',
    0x03BD: 'v', 0x039D: 'N',
    0x03BA: 'k', 0x039A: 'K',
    # Fullwidth → ASCII
    0xFF21: 'A', 0xFF41: 'a',
    0xFF25: 'E', 0xFF45: 'e',
    0xFF2F: 'O', 0xFF4F: 'o',
    0xFF30: 'P', 0xFF50: 'p',
    0xFF10: '0', 0xFF11: '1',
    # Punctuation lookalikes
    0x2024: '.', 0x00B7: '.',   # one dot leader, middle dot
    0x201C: '"', 0x201D: '"',   # curly quotes
    0x2018: "'", 0x2019: "'",
    0x00AD: '',                  # soft hyphen (invisible width)
    0x2212: '-',                 # minus sign (not hyphen)
}

ZERO_WIDTH: dict[int, str] = {
    0x200B: 'ZERO WIDTH SPACE',
    0x200C: 'ZERO WIDTH NON-JOINER',
    0x200D: 'ZERO WIDTH JOINER',
    0xFEFF: 'ZERO WIDTH NO-BREAK SPACE (BOM outside header)',
    0x2060: 'WORD JOINER',
    0x00AD: 'SOFT HYPHEN',
}

DIRECTIONAL: dict[int, str] = {
    0x202E: 'RIGHT-TO-LEFT OVERRIDE (RTLO) — filename spoofing risk',
    0x202D: 'LEFT-TO-RIGHT OVERRIDE',
    0x200F: 'RIGHT-TO-LEFT MARK',
    0x200E: 'LEFT-TO-RIGHT MARK',
    0x2066: 'LEFT-TO-RIGHT ISOLATE',
    0x2067: 'RIGHT-TO-LEFT ISOLATE',
    0x2068: 'FIRST STRONG ISOLATE',
    0x2069: 'POP DIRECTIONAL ISOLATE',
}

# U+E0000 range = tag characters, completely invisible, used for fingerprinting
TAG_BLOCK_START = 0xE0000
TAG_BLOCK_END   = 0xE007F

# Characters that ARE intentional and should not be flagged
SYSTEM_SIGNATURES = {
    '\u0394\u03a3',  # ΔΣ (system checksum prefix)
    '\u2192',        # → (flow arrows in docstrings)
    '\u2014',        # — (em dash in prose/docs)
    '\u2500',        # ─ (box drawing)
    '\u2713', '\u2717',  # ✓ ✗ (check/cross in test output)
    '\u25cf',        # ● (status indicator)
    '\u00d7',        # × (multiplication in comments)
}


def scan_unicode(text: str, source_label: str = "") -> list[dict]:
    """Layer 1: Detect Unicode anomalies."""
    findings = []
    lines = text.splitlines()

    homoglyph_hits = []
    zero_width_hits = []
    directional_hits = []
    tag_block_hits = []

    for lineno, line in enumerate(lines, 1):
        for col, ch in enumerate(line):
            cp = ord(ch)

            if cp in HOMOGLYPHS:
                ascii_eq = HOMOGLYPHS[cp]
                # Only flag if surrounded by ASCII (identifier context = HIGH)
                context_left  = line[max(0, col-3):col]
                context_right = line[col+1:col+4]
                in_identifier = (
                    context_left and context_left[-1:].isalnum() or
                    context_right and context_right[:1].isalnum()
                )
                severity = "HIGH" if in_identifier else "MEDIUM"
                homoglyph_hits.append({
                    "line": lineno, "col": col,
                    "char": ch, "codepoint": f"U+{cp:04X}",
                    "name": unicodedata.name(ch, "UNKNOWN"),
                    "looks_like": ascii_eq,
                    "severity": severity,
                    "context": line[max(0,col-10):col+10].strip(),
                })

            elif cp in ZERO_WIDTH:
                zero_width_hits.append({
                    "line": lineno, "col": col,
                    "codepoint": f"U+{cp:04X}",
                    "name": ZERO_WIDTH[cp],
                    "severity": "HIGH",
                    "context": line.strip()[:80],
                })

            elif cp in DIRECTIONAL:
                directional_hits.append({
                    "line": lineno, "col": col,
                    "codepoint": f"U+{cp:04X}",
                    "name": DIRECTIONAL[cp],
                    "severity": "HIGH",
                    "context": line.strip()[:80],
                })

            elif TAG_BLOCK_START <= cp <= TAG_BLOCK_END:
                tag_block_hits.append({
                    "line": lineno, "col": col,
                    "codepoint": f"U+{cp:04X}",
                    "name": "TAG BLOCK CHARACTER (fingerprinting/watermark)",
                    "severity": "HIGH",
                })

    if homoglyph_hits:
        # Cluster: 3+ homoglyphs in same file = steganographic candidate
        severity = "HIGH" if len(homoglyph_hits) >= 3 else homoglyph_hits[0]["severity"]
        findings.append({
            "layer": 1, "type": "homoglyph_substitution",
            "severity": severity,
            "count": len(homoglyph_hits),
            "hits": homoglyph_hits[:10],
            "note": "Visually identical to ASCII — may be steganographic or copy-paste artifact",
        })

    for hits, label in [
        (zero_width_hits, "zero_width_characters"),
        (directional_hits, "directional_override"),
        (tag_block_hits, "tag_block_fingerprinting"),
    ]:
        if hits:
            findings.append({
                "layer": 1, "type": label,
                "severity": "HIGH",
                "count": len(hits),
                "hits": hits[:5],
            })

    return findings


# ─── Layer 2: Whitespace encoding ────────────────────────────────────────────

def scan_whitespace(text: str) -> list[dict]:
    """Layer 2: Detect whitespace-based steganography."""
    findings = []
    lines = text.splitlines()

    # Trailing whitespace pattern — could encode binary
    trailing = [i+1 for i, l in enumerate(lines) if l != l.rstrip()]
    if len(trailing) > 5:
        # Decode: trailing space = 1, no trailing = 0
        bits = ''.join('1' if lines[i].endswith(' ') else '0' for i in range(len(lines)))
        # Try to decode as ASCII (8 bits per char)
        decoded = ''
        for i in range(0, len(bits) - 7, 8):
            byte = int(bits[i:i+8], 2)
            if 32 <= byte < 127:
                decoded += chr(byte)
            else:
                decoded = ''
                break
        if decoded and len(decoded) >= 3:
            findings.append({
                "layer": 2, "type": "trailing_whitespace_encoding",
                "severity": "MEDIUM",
                "lines_with_trailing": len(trailing),
                "decoded_candidate": decoded,
                "note": "Trailing whitespace pattern may encode binary message",
            })
        elif len(trailing) > 10:
            findings.append({
                "layer": 2, "type": "trailing_whitespace_pattern",
                "severity": "LOW",
                "count": len(trailing),
                "note": "Unusual number of lines with trailing whitespace",
            })

    # Tab/space binary encoding at line start
    indent_bits = []
    for line in lines:
        stripped = line.lstrip()
        if stripped and line != stripped:
            indent = line[:len(line)-len(stripped)]
            if '\t' in indent and ' ' in indent:
                indent_bits.append('1' if indent[0] == '\t' else '0')

    if len(indent_bits) > 16:
        decoded = ''
        for i in range(0, len(indent_bits) - 7, 8):
            byte = int(''.join(indent_bits[i:i+8]), 2)
            if 32 <= byte < 127:
                decoded += chr(byte)
        if len(decoded) >= 3:
            findings.append({
                "layer": 2, "type": "indent_binary_encoding",
                "severity": "MEDIUM",
                "bits_found": len(indent_bits),
                "decoded_candidate": decoded,
                "note": "Mixed tab/space indentation may encode binary",
            })

    # CRLF vs LF mixed — could encode binary (CRLF=1, LF=0)
    crlf_count = text.count('\r\n')
    lf_count   = text.count('\n') - crlf_count
    if crlf_count > 0 and lf_count > 0:
        findings.append({
            "layer": 2, "type": "mixed_line_endings",
            "severity": "LOW",
            "crlf": crlf_count, "lf": lf_count,
            "note": "Mixed CRLF/LF may encode binary (CRLF=1, LF=0)",
        })

    return findings


# ─── Layer 3: Structural patterns ────────────────────────────────────────────

BASE64_RE = re.compile(r'(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{24,}={0,2}(?![A-Za-z0-9+/])')
HEX_RE    = re.compile(r'\b[0-9a-fA-F]{32,}\b')


def detect_base64_blobs(text: str) -> list[dict]:
    import base64
    hits = []
    for m in BASE64_RE.finditer(text):
        blob = m.group()
        try:
            decoded = base64.b64decode(blob + '==')
            try:
                s = decoded.decode('utf-8')
                if all(32 <= ord(c) < 127 or c in '\n\r\t' for c in s):
                    hits.append({"blob": blob[:40] + "...", "decoded": s[:80], "type": "utf8"})
            except UnicodeDecodeError:
                hits.append({"blob": blob[:40] + "...", "decoded_hex": decoded[:16].hex(), "type": "binary"})
        except Exception:
            pass
    return hits[:8]


def detect_acrostic(lines: list[str]) -> Optional[str]:
    """First letters of non-empty lines. Return if IC suggests non-random."""
    clean = [l.strip() for l in lines if l.strip() and l.strip()[0].isalpha()]
    if len(clean) < 5:
        return None
    first = ''.join(l[0].upper() for l in clean)
    ic = index_of_coincidence(first)
    return first if ic > 0.055 else None


def detect_null_cipher(text: str) -> list[dict]:
    """Nth word, Nth letter, first word of sentence patterns."""
    findings = []
    words = text.split()
    if len(words) >= 10:
        # Every 5th word
        every5 = ' '.join(words[i] for i in range(0, len(words), 5))
        ic5 = index_of_coincidence(every5.replace(' ',''))
        if ic5 > 0.060:
            findings.append({"type": "every_5th_word", "candidate": every5[:80], "ic": round(ic5,3)})
        # First letter of every word
        first_letters = ''.join(w[0].upper() for w in words if w[0].isalpha())
        ic_fl = index_of_coincidence(first_letters)
        if ic_fl > 0.060:
            findings.append({"type": "first_letter_each_word", "candidate": first_letters[:60], "ic": round(ic_fl,3)})
    return findings


def rot13(text: str) -> str:
    result = []
    for c in text:
        if 'A' <= c <= 'Z':
            result.append(chr((ord(c) - ord('A') + 13) % 26 + ord('A')))
        elif 'a' <= c <= 'z':
            result.append(chr((ord(c) - ord('a') + 13) % 26 + ord('a')))
        else:
            result.append(c)
    return ''.join(result)


def scan_structural(text: str) -> list[dict]:
    """Layer 3: Detect structural steganography."""
    findings = []
    lines = text.splitlines()

    # Base64 blobs
    b64 = detect_base64_blobs(text)
    if b64:
        findings.append({
            "layer": 3, "type": "base64_blob",
            "severity": "MEDIUM",
            "count": len(b64), "hits": b64,
        })

    # Hex strings
    hex_hits = HEX_RE.findall(text)
    if hex_hits:
        # Try decoding each as ASCII
        decoded = []
        for h in hex_hits[:5]:
            try:
                b = bytes.fromhex(h)
                s = b.decode('utf-8', errors='strict')
                if all(32 <= ord(c) < 127 for c in s):
                    decoded.append({"hex": h[:40], "decoded": s[:60]})
            except Exception:
                decoded.append({"hex": h[:40], "decoded": None})
        findings.append({
            "layer": 3, "type": "hex_string",
            "severity": "LOW",
            "count": len(hex_hits), "hits": decoded,
        })

    # Acrostic
    acrostic = detect_acrostic(lines)
    if acrostic:
        findings.append({
            "layer": 3, "type": "acrostic_candidate",
            "severity": "LOW",
            "first_letters": acrostic,
            "note": "IC suggests non-random first-letter sequence",
        })

    # ROT13 check — any meaningful plaintext hiding as ROT13?
    letters_only = ''.join(c for c in text if c.isalpha())
    if len(letters_only) > 30:
        r13 = rot13(letters_only)
        r13_score = score_english(r13)
        orig_score = score_english(letters_only)
        if r13_score > orig_score * 1.5 and r13_score > 0.07:
            findings.append({
                "layer": 3, "type": "rot13_candidate",
                "severity": "MEDIUM",
                "english_score_original": round(orig_score, 4),
                "english_score_rot13": round(r13_score, 4),
                "decoded_preview": rot13(text)[:120],
            })

    # Null cipher
    null_hits = detect_null_cipher(text)
    if null_hits:
        findings.append({
            "layer": 3, "type": "null_cipher_candidate",
            "severity": "LOW",
            "hits": null_hits,
        })

    return findings


# ─── Layer 4: Web / HTML ─────────────────────────────────────────────────────

def scan_html(html: str) -> list[dict]:
    """Layer 4: Detect HTML-based steganography."""
    findings = []

    # Hidden comments
    comments = re.findall(r'<!--(.*?)-->', html, re.DOTALL)
    non_trivial = [c.strip() for c in comments if len(c.strip()) > 5]
    if non_trivial:
        findings.append({
            "layer": 4, "type": "html_hidden_comments",
            "severity": "LOW",
            "count": len(non_trivial),
            "samples": [c[:100] for c in non_trivial[:3]],
        })

    # CSS-hidden text patterns
    css_hidden_patterns = [
        (r'display\s*:\s*none', "display:none"),
        (r'visibility\s*:\s*hidden', "visibility:hidden"),
        (r'opacity\s*:\s*0[^.]', "opacity:0"),
        (r'font-size\s*:\s*0', "font-size:0"),
        (r'color\s*:\s*(white|#fff|#ffffff|rgba\(255,255,255)', "white text"),
        (r'height\s*:\s*0', "zero height"),
        (r'width\s*:\s*0', "zero width"),
        (r'overflow\s*:\s*hidden.*height\s*:\s*1px', "1px overflow:hidden"),
    ]
    css_hits = []
    for pattern, label in css_hidden_patterns:
        if re.search(pattern, html, re.IGNORECASE):
            css_hits.append(label)
    if css_hits:
        findings.append({
            "layer": 4, "type": "css_hidden_content",
            "severity": "MEDIUM",
            "patterns_found": css_hits,
        })

    # Data attributes with significant content
    data_attrs = re.findall(r'data-[\w-]+\s*=\s*["\']([^"\']{20,})["\']', html)
    if data_attrs:
        findings.append({
            "layer": 4, "type": "data_attribute_content",
            "severity": "LOW",
            "count": len(data_attrs),
            "samples": [a[:80] for a in data_attrs[:3]],
        })

    # Meta tag anomalies — unusual name= or content= values
    meta_tags = re.findall(r'<meta[^>]+>', html, re.IGNORECASE)
    suspicious_meta = []
    for tag in meta_tags:
        content = re.search(r'content\s*=\s*["\']([^"\']{40,})["\']', tag)
        if content:
            val = content.group(1)
            # Flag if content looks like cipher text or encoded data
            if BASE64_RE.search(val) or re.search(r'\d{5}\s+\d{5}', val):
                suspicious_meta.append(val[:100])
    if suspicious_meta:
        findings.append({
            "layer": 4, "type": "suspicious_meta_content",
            "severity": "MEDIUM",
            "samples": suspicious_meta[:3],
        })

    # <noscript> blocks (used to hide content from JS-capable scrapers)
    noscripts = re.findall(r'<noscript>(.*?)</noscript>', html, re.DOTALL | re.IGNORECASE)
    if noscripts:
        findings.append({
            "layer": 4, "type": "noscript_content",
            "severity": "LOW",
            "count": len(noscripts),
            "samples": [n.strip()[:100] for n in noscripts[:2]],
        })

    return findings


# ─── Layer 5: Financial / Ledger ─────────────────────────────────────────────

# Benford's Law: P(first digit = d) = log10(1 + 1/d)
BENFORD_EXPECTED = {d: math.log10(1 + 1/d) for d in range(1, 10)}
# {1:0.301, 2:0.176, 3:0.125, 4:0.097, 5:0.079, 6:0.067, 7:0.058, 8:0.051, 9:0.046}


def extract_numbers(text: str) -> list[float]:
    """Extract numeric values from text (handles $1,234.56 format)."""
    raw = re.findall(r'\$?\d[\d,]*\.?\d*', text)
    numbers = []
    for r in raw:
        try:
            numbers.append(float(r.replace('$', '').replace(',', '')))
        except ValueError:
            pass
    return [n for n in numbers if n > 0]


def benford_analysis(numbers: list[float]) -> dict:
    """Chi-squared test against Benford's Law. Critical value at 95%, df=8: 15.507"""
    if len(numbers) < 20:
        return {"skip": f"only {len(numbers)} numbers, need 20+"}

    first_digits = []
    for n in numbers:
        s = str(int(abs(n))).lstrip('0')
        if s and s[0].isdigit():
            first_digits.append(int(s[0]))

    if not first_digits:
        return {"skip": "no valid first digits"}

    total = len(first_digits)
    observed = Counter(first_digits)
    chi2 = 0.0
    deviations = {}
    for d in range(1, 10):
        exp = total * BENFORD_EXPECTED[d]
        obs = observed.get(d, 0)
        chi2 += (obs - exp) ** 2 / (exp + 0.01)
        deviations[d] = round((obs / total) - BENFORD_EXPECTED[d], 3)

    max_dev_digit, max_dev_val = max(deviations.items(), key=lambda x: abs(x[1]))
    return {
        "chi2": round(chi2, 3),
        "critical_value_95pct": 15.507,
        "suspicious": chi2 > 15.507,
        "sample_size": total,
        "max_deviation": {"digit": max_dev_digit, "deviation": max_dev_val},
        "distribution": {str(d): f"{observed.get(d,0)/total:.3f} (expected {BENFORD_EXPECTED[d]:.3f})"
                         for d in range(1, 10)},
    }


def round_number_analysis(numbers: list[float]) -> dict:
    """Detect clustering of suspiciously round numbers."""
    if not numbers:
        return {}
    round_thresholds = [100, 500, 1000, 5000, 10000]
    round_counts = {t: sum(1 for n in numbers if n > 0 and n % t == 0) for t in round_thresholds}
    total = len(numbers)
    suspicious = {t: c for t, c in round_counts.items() if c / total > 0.25 and c >= 5}
    return {"total_numbers": total, "suspicious_round_clustering": suspicious}


def duplicate_analysis(numbers: list[float]) -> list:
    """Find duplicate amounts — a fraud signal."""
    counter = Counter(numbers)
    dups = [(amount, count) for amount, count in counter.items() if count >= 3 and amount > 100]
    return sorted(dups, key=lambda x: x[1], reverse=True)[:10]


def scan_financial(text: str) -> list[dict]:
    """Layer 5: Financial/ledger anomaly detection."""
    findings = []
    numbers = extract_numbers(text)

    if not numbers:
        return []

    # Benford's Law
    benford = benford_analysis(numbers)
    if not benford.get("skip"):
        severity = "HIGH" if benford["suspicious"] else "INFO"
        findings.append({
            "layer": 5, "type": "benfords_law",
            "severity": severity,
            "result": benford,
            "note": "Chi2 > 15.507 at 95% confidence = digit distribution anomaly",
        })

    # Round number clustering
    round_res = round_number_analysis(numbers)
    if round_res.get("suspicious_round_clustering"):
        findings.append({
            "layer": 5, "type": "round_number_clustering",
            "severity": "MEDIUM",
            "result": round_res,
            "note": ">25% of amounts are suspiciously round",
        })

    # Duplicate amounts
    dups = duplicate_analysis(numbers)
    if dups:
        findings.append({
            "layer": 5, "type": "duplicate_amounts",
            "severity": "MEDIUM",
            "duplicates": [{"amount": a, "count": c} for a, c in dups],
        })

    return findings


# ─── Layer 7: Classical cipher analysis ──────────────────────────────────────

ENGLISH_FREQ = dict(zip(
    'ETAOINSHRDLCUMWFGYPBVKJXQZ',
    [0.1202, 0.0910, 0.0812, 0.0768, 0.0731, 0.0695, 0.0628, 0.0602,
     0.0592, 0.0432, 0.0398, 0.0288, 0.0271, 0.0261, 0.0230, 0.0211,
     0.0209, 0.0182, 0.0149, 0.0122, 0.0111, 0.0069, 0.0023, 0.0017,
     0.0011, 0.0007]
))

KRYPTOS_K4 = "OBKRUOXOGHULBSOLIFBBWFLRVQQPRNGKSSOTWTQSJQSSEKZZWATJKLUDIAWINFBNYPVTTMZFPKWGDKZXTJCDIGKUHUAUEKCAR"


def index_of_coincidence(text: str) -> float:
    """IC of alphabetic characters. English ~0.065, random ~0.038."""
    letters = [c.upper() for c in text if c.isalpha()]
    N = len(letters)
    if N < 2:
        return 0.0
    counts = Counter(letters)
    return sum(n * (n - 1) for n in counts.values()) / (N * (N - 1))


def score_english(text: str) -> float:
    """Score English-likeness (higher = more English)."""
    letters = [c.upper() for c in text if c.isalpha()]
    if not letters:
        return 0.0
    counts = Counter(letters)
    return sum(counts.get(c, 0) * f for c, f in ENGLISH_FREQ.items()) / len(letters)


def kasiski_estimate(text: str) -> list[tuple[int, int]]:
    """Kasiski test: find repeated trigrams, estimate key lengths by GCD of distances."""
    ctext = ''.join(c.upper() for c in text if c.isalpha())
    seqs: dict[str, list[int]] = {}
    for i in range(len(ctext) - 3):
        s = ctext[i:i+3]
        seqs.setdefault(s, []).append(i)

    distances = []
    for positions in seqs.values():
        if len(positions) > 1:
            for i in range(len(positions) - 1):
                distances.append(positions[i+1] - positions[i])

    key_len_votes = Counter()
    for d in distances:
        for k in range(2, min(d + 1, 21)):
            if d % k == 0:
                key_len_votes[k] += 1

    return key_len_votes.most_common(5)


def friedman_estimate(text: str) -> float:
    """Friedman's formula for expected Vigenère key length."""
    letters = [c.upper() for c in text if c.isalpha()]
    N = len(letters)
    if N < 10:
        return 0.0
    ic = index_of_coincidence(text)
    # Key length ≈ (K_p - K_r) / (IC - K_r)
    # where K_p = 0.065 (English), K_r = 0.0385 (random)
    denom = ic - 0.0385
    if denom <= 0:
        return 0.0
    return round((0.065 - 0.0385) / denom, 1)


def crack_vigenere(text: str, key_len: int) -> tuple[str, str, float]:
    """Attempt Vigenère decrypt at given key length. Returns (key, plaintext, english_score)."""
    ctext = ''.join(c.upper() for c in text if c.isalpha())
    key_chars = []
    for col in range(key_len):
        column = ctext[col::key_len]
        counts = Counter(column)
        best_shift, best_chi2 = 0, float('inf')
        for shift in range(26):
            chi2 = sum(
                ((counts.get(chr((ord(c) - shift) % 26 + ord('A')), 0)) - len(column) * f) ** 2
                / (len(column) * f + 0.01)
                for c, f in ENGLISH_FREQ.items()
            )
            if chi2 < best_chi2:
                best_chi2, best_shift = chi2, shift
        key_chars.append(chr(best_shift + ord('A')))

    key = ''.join(key_chars)
    plain = []
    ki = 0
    for c in ctext:
        shift = ord(key[ki % len(key)]) - ord('A')
        plain.append(chr((ord(c) - ord('A') - shift) % 26 + ord('A')))
        ki += 1
    plaintext = ''.join(plain)
    return key, plaintext, score_english(plaintext)


def detect_number_station(text: str) -> Optional[dict]:
    """Detect number station / OTP / VIC cipher patterns (5-digit groups)."""
    groups = re.findall(r'\b\d{5}\b', text)
    if len(groups) < 4:
        return None

    all_digits = ''.join(groups)
    digit_counts = Counter(all_digits)
    total = len(all_digits)
    frequencies = {d: count/total for d, count in digit_counts.items()}
    entropy = -sum(p * math.log2(p) for p in frequencies.values() if p > 0)

    # VIC cipher: two digits appear ~50% less often (the "straddler" digits)
    sorted_freqs = sorted(frequencies.values())
    min_freq, max_freq = sorted_freqs[0], sorted_freqs[-1]
    vic_pattern = max_freq > 3 * min_freq  # strong non-uniformity = VIC candidate

    return {
        "group_count": len(groups),
        "sample": groups[:6],
        "entropy": round(entropy, 3),
        "max_digit_freq": round(max_freq, 3),
        "vic_pattern_candidate": vic_pattern,
        "note": "Max entropy=3.322 (uniform/OTP). Lower with VIC straddling checkerboard.",
    }


def scan_classical_cipher(text: str) -> list[dict]:
    """Layer 7: Classical cipher detection — IC, Kasiski, Vigenère, number stations."""
    findings = []

    letters_only = ''.join(c for c in text if c.isalpha())
    if len(letters_only) < 40:
        return []  # Too short for statistical analysis

    ic = index_of_coincidence(letters_only)
    english_score = score_english(letters_only)

    # Classify by IC
    if ic > 0.060:
        ic_class = "natural_language_or_monoalphabetic"
        ic_severity = "INFO"
    elif 0.047 <= ic <= 0.060:
        ic_class = "polyalphabetic_cipher (Vigenere/Beaufort)"
        ic_severity = "HIGH"
    elif 0.038 <= ic < 0.047:
        ic_class = "machine_cipher_or_long_key (Enigma-range)"
        ic_severity = "HIGH"
    else:
        ic_class = "one_time_pad_or_random"
        ic_severity = "MEDIUM"

    findings.append({
        "layer": 7, "type": "index_of_coincidence",
        "severity": ic_severity,
        "ic": round(ic, 4),
        "classification": ic_class,
        "english_score": round(english_score, 4),
        "text_length": len(letters_only),
    })

    # If IC suggests cipher, run Kasiski + Friedman + crack attempts
    if ic < 0.060 and english_score < 0.06:
        kasiski = kasiski_estimate(letters_only)
        friedman_len = friedman_estimate(letters_only)

        if kasiski:
            findings.append({
                "layer": 7, "type": "kasiski_key_length_estimate",
                "severity": "HIGH",
                "top_candidates": kasiski,
                "friedman_estimate": friedman_len,
            })

        # Attempt crack for top 3 key lengths
        crack_results = []
        top_lengths = [k for k, _ in kasiski[:3]] if kasiski else [3, 4, 5]
        for kl in top_lengths:
            if 1 < kl <= 12:
                key, plain, eng = crack_vigenere(letters_only, kl)
                crack_results.append({
                    "key_length": kl,
                    "key_candidate": key,
                    "english_score": round(eng, 4),
                    "plaintext_preview": plain[:80],
                })

        if crack_results:
            best = max(crack_results, key=lambda x: x["english_score"])
            severity = "HIGH" if best["english_score"] > 0.05 else "MEDIUM"
            findings.append({
                "layer": 7, "type": "vigenere_crack_attempt",
                "severity": severity,
                "results": crack_results,
                "best_candidate": best,
                "note": "Score > 0.06 = likely English plaintext recovered",
            })

    # Number station / VIC detection
    ns = detect_number_station(text)
    if ns:
        findings.append({
            "layer": 7, "type": "number_station_pattern",
            "severity": "HIGH",
            "result": ns,
        })

    return findings


# ─── Layer 8: Narrative Cipher (Books of Mann / Pip Code / Unicorn O) ────────

# Unicorn O: homoglyph variants of 'o' that encode specific letters.
# From Die-Namic System Handoff 2026-01-08 (Consus).
UNICORN_O_MAP: dict[int, str] = {
    0x03BF: 'L',   # Greek small omicron
    0x043E: 'T',   # Cyrillic small o
    0x0585: 'R',   # Armenian small oh
    0x1D0F: 'P',   # Latin letter small capital O
    0x00BA: 'H',   # Masculine ordinal indicator (º)
    0x2092: 'A',   # Latin subscript small letter o (ₒ)
    0x022F: 'F',   # Latin small o with dot above (ȯ)
}

# Pip code symbols (Books of Mann cipher, Layer 2 + 3)
_PIP_FILLED_SQ = '\u25AA'   # ▪ base-6 pip (counts)
_PIP_WHITE_SQ  = '\u25AB'   # ▫ empty position (positional zero)
_PIP_FILLED_CI = '\u25CF'   # ● forward shift (word +N)
_PIP_EMPTY_CI  = '\u25CB'   # ○ backward shift (word −N)
_PIP_ALL = {_PIP_FILLED_SQ, _PIP_WHITE_SQ, _PIP_FILLED_CI, _PIP_EMPTY_CI}


def _decode_pip_line(line: str) -> dict:
    """
    Decode one pip-code symbol line.

    Layer 3 (Base-6 / Squares):
      Groups are space-separated. Count filled ▪ per group.
      Take last two group-counts as (d1, d2) → d1*6+d2 → letter (A=1).

    Layer 2 (Circles / Shift):
      ● = +1 forward word shift, ○ = −1 backward.
      Net shift = count(●) − count(○).
    """
    filled_ci = line.count(_PIP_FILLED_CI)
    empty_ci  = line.count(_PIP_EMPTY_CI)
    net_shift = filled_ci - empty_ci

    sq_group_counts = []
    for group in line.split():
        sq_chars = [c for c in group if c in (_PIP_FILLED_SQ, _PIP_WHITE_SQ)]
        if sq_chars:
            sq_group_counts.append(sum(1 for c in sq_chars if c == _PIP_FILLED_SQ))

    letter = None
    if len(sq_group_counts) >= 2:
        d1, d2 = sq_group_counts[-2], sq_group_counts[-1]
        idx = d1 * 6 + d2
        if 1 <= idx <= 26:
            letter = chr(ord('A') + idx - 1)

    return {
        'sq_groups': sq_group_counts,
        'filled_circles': filled_ci,
        'empty_circles': empty_ci,
        'net_shift': net_shift,
        'letter': letter,
    }


def scan_narrative_cipher(text: str) -> list[dict]:
    """
    Layer 8: Detect Books-of-Mann style pip code and Unicorn O cipher.

    Pip code: ▪▫●○ symbol lines encode hidden messages via base-6 (squares)
    and word-shift (circles). A phase shift of ±6 positions (mod chapter count)
    may be required to read the message in correct order.

    Unicorn O: specific homoglyph variants of 'o' encode individual letters
    per Die-Namic System Handoff 2026-01-08.
    """
    findings = []
    lines = text.splitlines()

    # ── Pip code detection ────────────────────────────────────────────────────
    pip_line_data = []
    for lineno, line in enumerate(lines, 1):
        if any(c in line for c in _PIP_ALL):
            decoded = _decode_pip_line(line)
            decoded['line'] = lineno
            decoded['raw'] = line.strip()
            pip_line_data.append(decoded)

    if pip_line_data:
        decoded_letters = [d['letter'] for d in pip_line_data if d['letter']]
        msg_fragment = ''.join(decoded_letters)

        # Check for ansible structure: pip line preceded by ≥2 italic dialogue lines
        ansible_count = 0
        for d in pip_line_data:
            lineno = d['line']
            window = lines[max(0, lineno - 12):lineno - 1]
            italic = [l for l in window if l.strip().startswith('*') and l.strip().endswith('*')]
            if len(italic) >= 2:
                ansible_count += 1

        findings.append(make_finding(
            8, 'pip_code_detected', 'MEDIUM',
            detail=f"{len(pip_line_data)} pip line(s); {len(decoded_letters)} letter(s) decoded",
            pip_lines=len(pip_line_data),
            decoded_fragment=msg_fragment if msg_fragment else None,
            ansible_style_blocks=ansible_count,
            note=(
                "Base-6 squares → letter (A=1). Circles = word-shift offset. "
                "If ansible structure present, apply ±6 mod N phase shift for correct order."
            ),
            examples=[{k: v for k, v in d.items() if k != 'sq_groups'} for d in pip_line_data[:6]],
        ))

    # ── Unicorn O detection ───────────────────────────────────────────────────
    unicorn_hits = []
    for lineno, line in enumerate(lines, 1):
        for col, ch in enumerate(line):
            cp = ord(ch)
            if cp in UNICORN_O_MAP:
                encoded = UNICORN_O_MAP[cp]
                try:
                    char_name = unicodedata.name(ch)
                except ValueError:
                    char_name = 'UNKNOWN'
                unicorn_hits.append({
                    'line': lineno,
                    'col': col,
                    'codepoint': f'U+{cp:04X}',
                    'char': ch,
                    'name': char_name,
                    'encoded_letter': encoded,
                    'context': line[max(0, col - 10):col + 10].strip(),
                })

    if unicorn_hits:
        decoded_seq = ''.join(h['encoded_letter'] for h in unicorn_hits)
        findings.append(make_finding(
            8, 'unicorn_o_cipher', 'HIGH',
            detail=f"{len(unicorn_hits)} Unicorn O substitution(s) → {repr(decoded_seq)}",
            count=len(unicorn_hits),
            decoded_sequence=decoded_seq,
            hits=unicorn_hits,
            note="Homoglyph 'o' variants encoding letters per Books-of-Mann cipher spec.",
        ))

    return findings


# ─── Output / reporting ───────────────────────────────────────────────────────

def make_finding(layer: int, type_: str, severity: str, **kwargs) -> dict:
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "layer": layer,
        "type": type_,
        "severity": severity,
        **kwargs,
    }


def severity_rank(s: str) -> int:
    return {"HIGH": 4, "MEDIUM": 3, "LOW": 2, "INFO": 1}.get(s, 0)


def print_report(findings: list[dict], source: str):
    sev_counts = Counter(f["severity"] for f in findings)
    print(f"\n{'='*60}")
    print(f"SPY REPORT — {source}")
    print(f"{'='*60}")
    print(f"Findings: {len(findings)} total  |  "
          f"HIGH: {sev_counts.get('HIGH',0)}  "
          f"MEDIUM: {sev_counts.get('MEDIUM',0)}  "
          f"LOW: {sev_counts.get('LOW',0)}")
    print()

    for f in sorted(findings, key=lambda x: severity_rank(x.get("severity","INFO")), reverse=True):
        sev = f.get("severity", "?")
        layer = f.get("layer", "?")
        type_ = f.get("type", "?")
        print(f"  [{sev:6}] L{layer} {type_}")
        for k, v in f.items():
            if k in ("severity", "layer", "type", "ts"):
                continue
            val_str = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
            print(f"           {k}: {val_str[:120]}")
        print()


def save_findings(findings: list[dict], source: str):
    """Append findings to flags.jsonl."""
    try:
        FLAGS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(FLAGS_LOG, "a", encoding="utf-8") as f:
            for finding in findings:
                finding["source"] = source
                f.write(json.dumps(finding, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[spy] Could not save to flags.jsonl: {e}", file=sys.stderr)


def pipe_to_willow(findings: list[dict], source: str, context_text: str = "") -> str:
    """
    Send spy findings to Willow for LLM reasoning and interpretation.

    Willow receives the structured findings and returns a human-readable
    analysis: what the anomalies mean, what cipher/stego is present, and
    what the next investigative step should be.

    Returns Willow's response string, or an error/unavailable message.
    """
    if not findings:
        return "[spy→Willow] No findings to analyze."

    WILLOW_URL = "http://localhost:8420/api/agents/chat/willow"

    # Serialize findings without timestamps (noise reduction)
    findings_clean = [
        {k: v for k, v in f.items() if k != "ts"}
        for f in findings
    ]
    findings_json = json.dumps(findings_clean, indent=2, ensure_ascii=False)

    # Build prompt
    prompt_parts = [
        f"spy.py scanned: {source}",
        f"\nStructured findings ({len(findings)} total):\n{findings_json}",
    ]
    if context_text:
        excerpt = context_text[:800].replace("\x0c", "\n")  # strip form-feeds
        prompt_parts.append(f"\nSource excerpt (first 800 chars):\n{excerpt}")
    prompt_parts.append(
        "\nPlease analyze these findings. What hidden content or cipher is present? "
        "What do the decoded fragments mean in context? What should be investigated next?"
    )

    message = "\n".join(prompt_parts)

    try:
        import urllib.request
        import urllib.error

        body = json.dumps({"message": message, "agent": "willow"}).encode("utf-8")
        req = urllib.request.Request(
            WILLOW_URL,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result.get("response") or "[Willow returned empty response]"

    except Exception as e:
        return f"[spy→Willow unavailable: {e}]"


def write_pickup_report(findings: list[dict], source: str):
    """Write human-readable report to Pickup folder."""
    try:
        PICKUP_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_path = PICKUP_DIR / f"spy_report_{ts}.txt"
        lines = [f"SPY REPORT — {source}", f"Generated: {ts}", ""]
        for f in sorted(findings, key=lambda x: severity_rank(x.get("severity","INFO")), reverse=True):
            lines.append(f"[{f.get('severity','?')}] Layer {f.get('layer','?')}: {f.get('type','?')}")
            for k, v in f.items():
                if k not in ("severity","layer","type","ts","source"):
                    lines.append(f"  {k}: {str(v)[:100]}")
            lines.append("")
        report_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"[spy] Report saved: {report_path}")
    except Exception as e:
        print(f"[spy] Could not write Pickup report: {e}", file=sys.stderr)


# ─── Main orchestrator ────────────────────────────────────────────────────────

def analyze_text(text: str, source: str = "stdin", html_mode: bool = False,
                 financial_mode: bool = False) -> list[dict]:
    """Run all applicable layers on text content. Returns list of findings."""
    all_findings = []
    all_findings += scan_unicode(text, source)
    all_findings += scan_whitespace(text)
    all_findings += scan_structural(text)
    if html_mode:
        all_findings += scan_html(text)
    if financial_mode:
        all_findings += scan_financial(text)
    all_findings += scan_classical_cipher(text)
    all_findings += scan_narrative_cipher(text)
    return all_findings


def analyze_file(path: Path, financial_mode: bool = False) -> list[dict]:
    """Analyze a single file."""
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8", errors="replace")
    except Exception as e:
        return [{"layer": 0, "type": "read_error", "severity": "INFO", "error": str(e)}]

    is_html = path.suffix.lower() in (".html", ".htm")
    return analyze_text(text, str(path), html_mode=is_html, financial_mode=financial_mode)


def analyze_url(url: str) -> list[dict]:
    """Fetch and analyze a web page."""
    try:
        import urllib.request
        with urllib.request.urlopen(url, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        # Strip tags for text analysis, keep html for html layer
        text_only = re.sub(r'<[^>]+>', ' ', html)
        findings = scan_unicode(text_only, url)
        findings += scan_whitespace(text_only)
        findings += scan_structural(text_only)
        findings += scan_html(html)
        findings += scan_financial(text_only)
        findings += scan_classical_cipher(text_only)
        return findings
    except Exception as e:
        return [{"layer": 0, "type": "fetch_error", "severity": "INFO", "error": str(e)}]


# ─── Watcher integration API ──────────────────────────────────────────────────

def scan_drop_file(path: Path) -> list[dict]:
    """
    Called by watcher.py when a new file arrives in Drop.
    Returns findings — watcher decides whether to log/route them.
    """
    findings = analyze_file(path, financial_mode=True)
    return [f for f in findings if severity_rank(f.get("severity", "INFO")) >= 2]  # LOW+


def scan_source_dirs(dirs: list[Path], mtime_after: float = 0.0) -> list[dict]:
    """
    Called by watcher background cycle.
    Scans source code dirs, only files modified after mtime_after.
    """
    SCAN_EXTS = {'.py', '.js', '.ts', '.html', '.md', '.txt', '.json', '.yaml', '.yml'}
    SKIP = {'.git', '__pycache__', 'node_modules', 'venv', '.venv', 'artifacts', 'Archive'}
    all_findings = []
    for base in dirs:
        if not base.is_dir():
            continue
        for fpath in base.rglob("*"):
            if any(s in fpath.parts for s in SKIP):
                continue
            if fpath.suffix.lower() not in SCAN_EXTS:
                continue
            if mtime_after and fpath.stat().st_mtime <= mtime_after:
                continue
            findings = analyze_file(fpath)
            for f in findings:
                f["source_file"] = str(fpath)
            all_findings += [f for f in findings if severity_rank(f.get("severity","INFO")) >= 2]
    return all_findings


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="spy.py — cipher and steganography detector")
    parser.add_argument("target", nargs="?", help="File, directory, or URL to scan")
    parser.add_argument("--text", help="Scan raw text string directly")
    parser.add_argument("--url", help="Scan a web page")
    parser.add_argument("--dir", help="Scan a directory")
    parser.add_argument("--financial", action="store_true", help="Enable financial/Benford analysis")
    parser.add_argument("--save", action="store_true", help="Append findings to flags.jsonl")
    parser.add_argument("--pickup", action="store_true", help="Write Pickup report")
    parser.add_argument("--willow", action="store_true", help="Pipe findings to Willow for LLM analysis")
    parser.add_argument("--kryptos", action="store_true", help="Run Kryptos K4 analysis as test")
    args = parser.parse_args()

    if args.kryptos:
        print(f"[spy] Kryptos K4 analysis ({len(KRYPTOS_K4)} chars)")
        findings = scan_classical_cipher(KRYPTOS_K4)
        print_report(findings, f"Kryptos K4 [{KRYPTOS_K4[:20]}...]")
        return

    if args.text:
        findings = analyze_text(args.text, "cli:text", financial_mode=args.financial)
        print_report(findings, "cli:text")
        source = "cli:text"

    elif args.url:
        findings = analyze_url(args.url)
        print_report(findings, args.url)
        source = args.url

    elif args.dir:
        target_dir = Path(args.dir)
        findings = scan_source_dirs([target_dir])
        print_report(findings, str(target_dir))
        source = str(target_dir)

    elif args.target:
        target = Path(args.target)
        if target.is_dir():
            findings = scan_source_dirs([target])
        else:
            findings = analyze_file(target, args.financial)
        print_report(findings, str(target))
        source = str(target)

    else:
        # Read from stdin
        text = sys.stdin.read()
        findings = analyze_text(text, "stdin", financial_mode=args.financial)
        print_report(findings, "stdin")
        source = "stdin"

    if args.save:
        save_findings(findings, source)
    if args.pickup:
        write_pickup_report(findings, source)
    if args.willow:
        high_findings = [f for f in findings if severity_rank(f.get("severity", "INFO")) >= 3]
        if not high_findings:
            high_findings = findings  # send all if nothing is MEDIUM+
        print(f"\n[spy→Willow] Sending {len(high_findings)} finding(s) for analysis...")
        willow_response = pipe_to_willow(high_findings, source)
        print(f"\n{'─'*60}")
        print("WILLOW ANALYSIS")
        print(f"{'─'*60}")
        print(willow_response)


if __name__ == "__main__":
    main()
