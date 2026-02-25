"""
decode_ansible.py

Reads "What I Carried - Full Manuscript.pdf", extracts all ANSIBLE [N]: blocks,
and applies the Pip Code Base-6 cipher to decode them.

Cipher rules (from cipher document):
  Symbols: ▪ ▫ ● ○  (and possibly space-separated groups)
  - Split symbol sequence by spaces to get groups
  - Count ONLY filled squares ▪ in each group (▫ is ignored / counts as 0)
  - Collect group counts
  - Pair consecutive nonzero counts: (d1, d2) → d1*6 + d2 = letter index
  - A=1, B=2, ..., Z=26
  Example: ▪ ▪▪▪ → groups [▪] [▪▪▪] → counts [1, 3] → 1*6+3=9 → I

Two strategies attempted:
  A) Only nonzero groups form the digit list
  B) All groups (including zero-count groups) form the digit list
"""

import re
import sys

# ── PDF extraction ─────────────────────────────────────────────────────────────
def extract_text_pdfminer(path: str) -> str:
    from pdfminer.high_level import extract_text
    return extract_text(path)

def extract_text_fitz(path: str) -> str:
    import fitz
    doc = fitz.open(path)
    pages = []
    for page in doc:
        pages.append(page.get_text())
    return "\n".join(pages)

def get_pdf_text(path: str) -> str:
    try:
        text = extract_text_pdfminer(path)
        if text and len(text.strip()) > 100:
            print(f"[INFO] Extracted text via pdfminer.six ({len(text)} chars)")
            return text
    except Exception as e:
        print(f"[WARN] pdfminer failed: {e}")

    try:
        text = extract_text_fitz(path)
        if text and len(text.strip()) > 100:
            print(f"[INFO] Extracted text via PyMuPDF/fitz ({len(text)} chars)")
            return text
    except Exception as e:
        print(f"[WARN] fitz failed: {e}")

    raise RuntimeError("No PDF library could read the file.")

# ── Ansible block extraction ───────────────────────────────────────────────────
ANSIBLE_PATTERN = re.compile(
    r'ANSIBLE\s*\[(\d+)\]\s*:?\s*([▪▫●○\s]+?)(?=ANSIBLE\s*\[|\Z)',
    re.DOTALL | re.UNICODE
)

# Broader fallback: match ANSIBLE N: ... up to next section break
ANSIBLE_PATTERN_FALLBACK = re.compile(
    r'ANSIBLE\s+(\d+)\s*:?\s*([▪▫●○\s]+)',
    re.UNICODE
)

def extract_ansibles(text: str) -> list[tuple[int, str]]:
    """Return list of (number, symbol_string) tuples."""
    results = {}

    for m in ANSIBLE_PATTERN.finditer(text):
        num = int(m.group(1))
        symbols = m.group(2).strip()
        if symbols:
            results[num] = symbols

    # Fallback for individual matches
    if len(results) < 5:
        for m in ANSIBLE_PATTERN_FALLBACK.finditer(text):
            num = int(m.group(1))
            symbols = m.group(2).strip()
            if symbols and num not in results:
                results[num] = symbols

    return sorted(results.items())

# ── Pip Code Base-6 decoder ────────────────────────────────────────────────────
FILLED = '▪'   # counts as 1 per character
EMPTY  = '▫'   # ignored (counts as 0)
# ● and ○ are narrative symbols, not cipher symbols — skip groups that are only those

def index_to_letter(idx: int) -> str:
    """1=A, 2=B, ..., 26=Z.  Returns '?' if out of range."""
    if 1 <= idx <= 26:
        return chr(ord('A') + idx - 1)
    return f'[{idx}]'

def decode_digits(digits: list[int]) -> str:
    """Pair consecutive digits: d1*6 + d2 → letter."""
    letters = []
    i = 0
    while i + 1 < len(digits):
        val = digits[i] * 6 + digits[i + 1]
        letters.append(index_to_letter(val))
        i += 2
    if i < len(digits):
        letters.append(f'(leftover:{digits[i]})')
    return ''.join(letters)

def group_count(group: str) -> int:
    """Count filled squares ▪ in a group."""
    return group.count(FILLED)

def decode_symbol_string(symbol_str: str) -> dict:
    """
    Returns a dict with:
      - groups: list of group strings
      - counts_all: count per group (all groups)
      - counts_nonzero: only nonzero counts
      - decoded_nonzero: decoded using strategy A
      - decoded_all: decoded using strategy B
    """
    # Split on whitespace to get groups
    groups = symbol_str.split()

    # Filter out groups that contain no cipher chars at all (e.g. pure ●○ groups)
    cipher_groups = []
    for g in groups:
        if FILLED in g or EMPTY in g:
            cipher_groups.append(g)
        elif re.search(r'[▪▫]', g):
            cipher_groups.append(g)

    counts_all = [group_count(g) for g in cipher_groups]
    counts_nonzero = [c for c in counts_all if c > 0]

    decoded_nonzero = decode_digits(counts_nonzero)
    decoded_all     = decode_digits(counts_all)

    return {
        "groups":          cipher_groups,
        "counts_all":      counts_all,
        "counts_nonzero":  counts_nonzero,
        "decoded_nonzero": decoded_nonzero,
        "decoded_all":     decoded_all,
    }

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    pdf_path = r"C:/Users/Sean/Downloads/What I Carried - Full Manuscript.pdf"

    print("=" * 70)
    print("ANSIBLE DECODER — Pip Code Base-6")
    print("=" * 70)

    text = get_pdf_text(pdf_path)

    # Dump a small snippet to show what was found near "ANSIBLE"
    idx = text.find("ANSIBLE")
    if idx != -1:
        print(f"\n[DEBUG] First 'ANSIBLE' occurrence at char {idx}:")
        print(repr(text[max(0, idx-20):idx+120]))
    else:
        print("\n[WARN] 'ANSIBLE' not found in extracted text — check PDF encoding")
        # Try showing what characters ARE in the text for diagnosis
        unique_chars = sorted(set(text))
        print(f"[DEBUG] Unique non-ASCII chars in doc: {[c for c in unique_chars if ord(c) > 127][:60]}")

    ansibles = extract_ansibles(text)
    print(f"\n[INFO] Found {len(ansibles)} ANSIBLE block(s)\n")

    if not ansibles:
        print("[WARN] No ANSIBLE blocks extracted.")
        print("[DEBUG] Searching for any 'ANSIBLE' occurrences in raw text...")
        for m in re.finditer(r'ANSIBLE', text, re.IGNORECASE):
            start = m.start()
            print(f"  pos {start}: {repr(text[start:start+200])}")
        return

    for num, sym_str in ansibles:
        result = decode_symbol_string(sym_str)
        print("-" * 70)
        print(f"ANSIBLE [{num}]")
        print(f"  Raw symbols   : {sym_str!r}")
        print(f"  Symbol groups : {result['groups']}")
        print(f"  Counts (all)  : {result['counts_all']}")
        print(f"  Counts (nz)   : {result['counts_nonzero']}")
        print(f"  Decoded [A]   : {result['decoded_nonzero']}  (nonzero groups only)")
        print(f"  Decoded [B]   : {result['decoded_all']}  (all groups including zeros)")

    print("\n" + "=" * 70)
    print("Done.")

if __name__ == "__main__":
    main()
