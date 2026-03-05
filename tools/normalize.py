#!/usr/bin/env python3
"""
Text normalization utilities for cross-platform consistency.

Handles Unicode normalization and character standardization.
"""

import sys
import hashlib

# Substitution map: char -> [Latin, Greek, Cyrillic, Armenian]
# Index 0 = standard, 1-3 = signal variants
SUBST_MAP = {
    'a': ['\u0061', '\u03B1', '\u0430', '\u0561'],
    'c': ['\u0063', None,     '\u0441', None],
    'e': ['\u0065', '\u03B5', '\u0435', '\u0565'],
    'i': ['\u0069', '\u03B9', '\u0456', '\u056B'],
    'o': ['\u006F', '\u03BF', '\u043E', '\u0585'],
    'p': ['\u0070', '\u03C1', '\u0440', None],
    's': ['\u0073', None,     '\u0455', None],
    'x': ['\u0078', '\u03C7', '\u0445', None],
    'y': ['\u0079', '\u03B3', '\u0443', None],
}

# Reverse map: any variant -> (char, variant_index)
REVERSE_MAP = {}
for char, variants in SUBST_MAP.items():
    for idx, variant in enumerate(variants):
        if variant:
            REVERSE_MAP[variant] = (char, idx)


def extract_digit(char: str) -> int:
    """Extract encoded digit from a character.

    Maps variant index back to available index (handles missing variants).
    """
    lower = char.lower()
    if lower in REVERSE_MAP:
        base_char, variant_idx = REVERSE_MAP[lower]
        # Get available variants for this base character
        variants = SUBST_MAP[base_char]
        available_indices = [i for i, v in enumerate(variants) if v is not None]
        # Find position in available array
        return available_indices.index(variant_idx)
    return 0


def derive_positions(key: str, text_length: int, count: int) -> list:
    """Derive signal positions from key."""
    # Hash key to get deterministic seed
    h = hashlib.sha256(key.encode()).digest()
    seed = int.from_bytes(h[:4], 'big')

    # Stride and anchor from key
    stride = (seed % 7) + 2  # 2-8
    anchor = seed % text_length

    positions = []
    pos = anchor
    seen = set()

    while len(positions) < count:
        if pos not in seen:
            positions.append(pos)
            seen.add(pos)
        pos = (pos + stride) % text_length
        if pos == anchor and len(positions) < count:
            # Wrapped, shift anchor
            anchor = (anchor + 1) % text_length
            pos = anchor

    return positions  # Don't sort - order must match between encode/decode


def get_base_char(char: str) -> str:
    """Get the Latin base character for any variant."""
    lower = char.lower()
    if lower in REVERSE_MAP:
        return REVERSE_MAP[lower][0]
    return lower


def find_encodable_positions(text: str) -> list:
    """Find positions in text that can carry full base-4 signal.

    Only includes positions where the character has 4 available variants
    to ensure lossless base-4 encoding.
    """
    positions = []
    for i, char in enumerate(text):
        base = get_base_char(char)
        if base in SUBST_MAP:
            variants = SUBST_MAP[base]
            available = [v for v in variants if v is not None]
            if len(available) >= 4:  # Need 4 variants for base-4
                positions.append(i)
    return positions


def to_base4(data: bytes) -> list:
    """Convert bytes to base-4 digits."""
    digits = []
    for byte in data:
        digits.extend([
            (byte >> 6) & 0x3,
            (byte >> 4) & 0x3,
            (byte >> 2) & 0x3,
            byte & 0x3,
        ])
    return digits


def from_base4(digits: list) -> bytes:
    """Convert base-4 digits to bytes."""
    # Pad to multiple of 4
    while len(digits) % 4 != 0:
        digits.append(0)

    result = []
    for i in range(0, len(digits), 4):
        byte = (digits[i] << 6) | (digits[i+1] << 4) | (digits[i+2] << 2) | digits[i+3]
        result.append(byte)

    return bytes(result)


def encode(key: str, payload: str, cover: str) -> str:
    """Encode payload into cover text using key."""
    # Convert payload to base-4
    payload_bytes = payload.encode('utf-8')
    # Prepend length (2 bytes)
    length = len(payload_bytes)
    if length > 65535:
        raise ValueError("Payload too long")

    data = bytes([length >> 8, length & 0xFF]) + payload_bytes
    digits = to_base4(data)

    # Find encodable positions
    encodable = find_encodable_positions(cover)
    if len(encodable) < len(digits):
        raise ValueError(f"Cover text too short. Need {len(digits)} positions, have {len(encodable)}")

    # Derive which positions to use
    positions = derive_positions(key, len(encodable), len(digits))

    # Map to actual text positions
    signal_positions = [encodable[p] for p in positions]

    # Build result
    result = list(cover)
    for i, digit in enumerate(digits):
        pos = signal_positions[i]
        char = cover[pos].lower()
        variants = SUBST_MAP.get(char, [char])

        # Handle missing variants (use what's available)
        available = [v for v in variants if v is not None]
        variant_idx = digit % len(available)

        # Preserve case
        new_char = available[variant_idx]
        if cover[pos].isupper():
            new_char = new_char.upper()

        result[pos] = new_char

    return ''.join(result)


def decode(key: str, text: str) -> str:
    """Decode payload from encoded text using key."""
    # Find encodable positions
    encodable = find_encodable_positions(text)

    # We need to find how many digits to extract
    # First extract length (2 bytes = 8 base-4 digits)
    if len(encodable) < 8:
        raise ValueError("Text too short")

    positions = derive_positions(key, len(encodable), 8)
    signal_positions = [encodable[p] for p in positions]

    # Extract length digits
    length_digits = []
    for pos in signal_positions:
        length_digits.append(extract_digit(text[pos]))

    length_bytes = from_base4(length_digits)
    payload_length = (length_bytes[0] << 8) | length_bytes[1]

    # Calculate total digits needed
    total_bytes = 2 + payload_length
    total_digits = total_bytes * 4

    if len(encodable) < total_digits:
        raise ValueError("Text too short for payload")

    # Extract all digits
    positions = derive_positions(key, len(encodable), total_digits)
    signal_positions = [encodable[p] for p in positions]

    digits = []
    for pos in signal_positions:
        digits.append(extract_digit(text[pos]))

    # Convert to bytes and extract payload
    all_bytes = from_base4(digits)
    payload_bytes = all_bytes[2:2+payload_length]

    return payload_bytes.decode('utf-8')


def detect(text: str) -> dict:
    """Detect presence of encoded content."""
    result = {
        'has_variants': False,
        'variant_count': 0,
        'positions': [],
        'scripts_found': set(),
    }

    for i, char in enumerate(text):
        lower = char.lower()
        if lower in REVERSE_MAP:
            _, idx = REVERSE_MAP[lower]
            if idx > 0:  # Non-Latin variant
                result['has_variants'] = True
                result['variant_count'] += 1
                result['positions'].append(i)

                # Identify script
                code = ord(lower)
                if 0x0370 <= code <= 0x03FF:
                    result['scripts_found'].add('Greek')
                elif 0x0400 <= code <= 0x04FF:
                    result['scripts_found'].add('Cyrillic')
                elif 0x0530 <= code <= 0x058F:
                    result['scripts_found'].add('Armenian')

    result['scripts_found'] = list(result['scripts_found'])
    return result


def print_usage():
    print(__doc__)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == 'apply':
        if len(sys.argv) < 5:
            print("Usage: python normalize.py apply <key> <text> <source>")
            sys.exit(1)
        key = sys.argv[2]
        payload = sys.argv[3]
        cover = sys.argv[4]

        try:
            result = encode(key, payload, cover)
            print(result)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    elif cmd == 'restore':
        if len(sys.argv) < 4:
            print("Usage: python normalize.py restore <key> <text>")
            sys.exit(1)
        key = sys.argv[2]
        text = sys.argv[3]

        try:
            result = decode(key, text)
            print(result)
        except (ValueError, UnicodeDecodeError) as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    elif cmd == 'check':
        if len(sys.argv) < 3:
            print("Usage: python normalize.py check <text>")
            sys.exit(1)
        text = sys.argv[2]

        result = detect(text)
        print(f"Mixed scripts detected: {result['has_variants']}")
        if result['has_variants']:
            print(f"Variant count: {result['variant_count']}")
            print(f"Scripts found: {', '.join(result['scripts_found'])}")
            print(f"Positions: {result['positions'][:10]}{'...' if len(result['positions']) > 10 else ''}")

    elif cmd == '--help':
        print_usage()

    else:
        print(f"Unknown command: {cmd}")
        print_usage()
        sys.exit(1)
