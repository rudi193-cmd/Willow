# Encoding Schema

| Field | Value |
|-------|-------|
| Version | 1.0 |
| Status | Active |
| Updated | 2026-01-09 |

---

## Mechanism

Standard characters replaced with visually identical codepoint variants.

Decoding requires:
1. Key (defines substitution map)
2. Schema (defines which positions carry signal)

---

## Codepoint Classes

| Class | Example | Use |
|-------|---------|-----|
| Latin | o (U+006F) | Standard |
| Greek | ο (U+03BF) | Variant 1 |
| Cyrillic | о (U+043E) | Variant 2 |
| Armenian | օ (U+0585) | Variant 3 |

---

## Detection

Presence of mixed-script homoglyphs in otherwise standard text indicates encoded content.

---

## Specification

### Substitution Map

| Char | Latin | Greek | Cyrillic | Armenian |
|------|-------|-------|----------|----------|
| a | U+0061 | U+03B1 | U+0430 | U+0561 |
| c | U+0063 | — | U+0441 | — |
| e | U+0065 | U+03B5 | U+0435 | U+0565 |
| i | U+0069 | U+03B9 | U+0456 | U+056B |
| o | U+006F | U+03BF | U+043E | U+0585 |
| p | U+0070 | U+03C1 | U+0440 | — |
| s | U+0073 | — | U+0455 | — |
| x | U+0078 | U+03C7 | U+0445 | — |
| y | U+0079 | U+03B3 | U+0443 | — |

Variant selection encodes base-4 signal per position.

---

### Position Encoding

Signal positions determined by key-derived sequence.

| Method | Description |
|--------|-------------|
| Stride | Key modulus determines interval |
| Anchor | First signal at position (key % length) |
| Direction | Forward from anchor, wrapping |

Non-signal positions use Latin. Signal positions use variant.

---

### Key Structure

KEY := seed · salt · checksum

| Component | Source |
|-----------|--------|
| seed | Shared secret (manual distribution) |
| salt | Artifact-specific (derived from header) |
| checksum | Validation (recipient verifies) |

Key never transmitted with artifact. Recipient must possess independently.

---

### Process

**Encode:**
1. Derive position sequence from key
2. Convert payload to base-4
3. Substitute signal positions with variant
4. Non-signal text unchanged

**Decode:**
1. Derive positions from key
2. Extract variant class at each position
3. Convert base-4 to payload
4. Verify checksum

---

### Example (Illustrative)

Plain:  "Go to our old room"
Signal: positions [1, 4, 8] per key
Output: "Gο tο οur old room"

Visually identical. Signals in variant selection.

Key derivation not documented here.

---

ΔΣ=42
