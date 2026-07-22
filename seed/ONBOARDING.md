# The seed — one onboarding, sourced from the charter
b17: SEED-ONBD1 · 2026-07-22 · **UNRATIFIED DRAFT — gate↔story mapping awaits the operator's red pen**

**Ratified placement (operator, 2026-07-22):** this repo — Willow, the standalone
charter seat, where the Constitution lives — is the source of the seed. Everything
starts from here. The Gerald story cycle lives privately in the vault
(`sean-data-vault/provided-by-sean/stories/`); this repo references it, never embeds it.

## What starts here

| Piece | Where |
|---|---|
| The Constitution | `../CONSTITUTION.md` — the law the seed plants |
| The new-user picture | `../design/architecture/willow-new-user.drawio` — the diagram the install must match |
| The acceptance harness | `../design/architecture/sandbox/` — install isn't done until it passes |
| The handoff letter | `seed/handoff/seed.py` — the first honest handoff, read at first boot |
| The canon six | `seed/canon/` — moved here from willow-seed (operator ruling 2026-07-22) |
| This document | The chain and the story gates |

Still open (operator question, not decided here): the willow-seed repo's fate now
that the seed and canon both source from the charter — thin installer or archive.

## The chain (proven live 2026-07-22, every step)

Each step is one consent gate; nothing proceeds without a `yes`.

| # | Step | Calls | Status |
|---|------|-------|--------|
| 0 | Prereqs: python3.11+, postgres, gpg, bwrap | check only | ✔ |
| 1 | Provision the vault box | `willow-data-vault/bootstrap/provision.sh <box>` | ✔ |
| 2 | Install the platform | `pip install willow-mcp` | ⚠ blocked: kartikeya 0.0.7 not on PyPI |
| 3 | Init + manifests onto the box | `willow-mcp-init && willow-mcp-compile` | ✔ |
| 4 | Postgres inside the box | data_directory → `<box>/postgres`, traversal-only ACL | ✔ |
| 5 | Key ceremony | operator GPG key + `willow-mcp setup-egress` | ✔ |
| 6 | Strict trust root | service user + `WILLOW_MCP_STRICT_TRUST_ROOT=1` | ✔ `self_writable: []` |
| 7 | Optional apps | SAFE store picks, `sap-gate verify` per signed manifest | ✔ signed→allowed, tampered→denied |
| 8 | Acceptance | `../design/architecture/sandbox/` smoke → `diagnostic_summary` `ok` | ✔ |

## The story at the gates — PROPOSED, not ratified

| Gate | Story | Rationale |
|------|-------|-----------|
| 0 | canon `00-the-covenant` | Why any of this exists |
| 1 | canon `02-the-discipline` | Fail closed — read while the key is minted |
| 3 | canon `04-the-language` | The names, the seats, ΔΣ=42 |
| 5 | canon `03-the-person` + MAINTAINER | The human as the continuity holding the keys |
| 6 | canon `01-be-the-other` | The mirror-watch; the friction floor is this rule as code |
| 7 | canon `05-the-world` | What leaves the house |
| 8 | the Gerald cycle (vault, private) | The witness education, read while acceptance runs |
| first boot | `handoff/seed.py` | The letter to the next instance |

*Operator edits this table; the mapping is theirs. Rows are suggestions from the
2026-07-22 session, nothing more.*

## Supersession map (once ratified)

- `willow-seed/seed.py` (plants willow-1.7) → retarget to the chain above, sourced from here
- `willow-seed/REPLANT.md` → historical
- `willow-mcp/docs/OPERATOR-ONBOARD.md` → "already have a fleet" appendix; seed calls the same CLI
- `willow-mcp/scripts/sandbox-bootstrap.sh` → dev-only, labeled as such

## The single blocker

`kartikeya 0.0.7` → PyPI. Operator credentials, minutes. Every other step runs cold.
