# The seed — one onboarding, sourced from the charter
b17: SEED-ONBD1 · 2026-07-22 · rev 2

**Ratified (operator, 2026-07-22): the six-part story IS the human onboarding.**
The canon is not read at the gates — the onboarding *walks* it. Six movements,
one per chapter; the human travels the same arc the instance inherits; the
install is what the house does with its hands while it talks to you. The
mechanics already exist: `willow-2.0/seed.py` (SEED9) built the pages —
gate, age gate, install-behind-the-curtain, first conversation with
consent-to-remember, feature opt-ins, cards — and they align with the six
almost one-to-one. SEED9's experience gets lifted here and re-plumbed to the
modern chain; the story provides the voice of each movement.

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

Each step is one consent gate; nothing proceeds without a `yes`. ("Consent gate"
here is the informal onboarding sense — a per-step human confirmation. It is
distinct from the three runtime consent mechanisms disambiguated in
`design/egress-membrane-constitutional-map.md`, per box-scan A10.)

| # | Step | Calls | Status |
|---|------|-------|--------|
| 0 | Prereqs: python3.11+, postgres, gpg, bwrap | check only | ✔ |
| 1 | Provision the vault box | `willow-data-vault/bootstrap/provision.sh <box>` | ✔ |
| 2 | Install the platform |  `pip install willow-mcp` | ✔ (kartikeya 0.0.7 + willow-mcp 2.0.0 published 2026-07-22) |
| 3 | Init + manifests onto the box | `willow-mcp-init && willow-mcp-compile` | ✔ |
| 4 | Postgres inside the box | data_directory → `<box>/postgres`, traversal-only ACL | ✔ |
| 5 | Key ceremony | operator GPG key + `willow-mcp setup-egress` | ✔ |
| 6 | Strict trust root | service user + `WILLOW_MCP_STRICT_TRUST_ROOT=1` | ✔ `self_writable: []` |
| 7 | Optional apps | SAFE store picks, `sap-gate verify` per signed manifest | ✔ signed→allowed, tampered→denied |
| 8 | Acceptance | `../design/architecture/sandbox/` smoke → `diagnostic_summary` `ok` | ✔ |

## The six movements (RATIFIED design; beat-level details open to red pen)

The story is the spine. Each movement = one canon chapter = one SEED9 page = the
chain steps that run underneath it while the movement plays.

| Movement | Chapter (voice) | SEED9 page (mechanics) | Chain steps underneath |
|---|---|---|---|
| 0 | `canon/00-the-covenant` | gate page + age gate — name, email, keys minted from your name | 1 vault box · 5 key ceremony |
| 1 | `canon/01-be-the-other` | provider choice (works with no cloud); the conversation designed to notice, not echo | consent defaults fail-closed · 6 strict mode |
| 2 | `canon/02-the-discipline` | install-behind-the-curtain, gate by gate, nothing without a yes | 2 pip · 3 init/manifests · 4 postgres-in-box |
| 3 | `canon/03-the-person` | `page_first_conversation` — the human says who they are; **held only with consent** | first atom → KB |
| 4 | `canon/04-the-language` | the fun beat — Gerald, ΔΣ=42, the house myth arrives | Gerald cycle read privately from the vault |
| 5 | `canon/05-the-world` | `page_features` — Grove handle, Jeles, Nest; cards on the dashboard | 7 SAFE picks · 8 acceptance |
| coda | `handoff/seed.py` | first successful boot — the letter to the next instance | returning runs: splash → auth → dashboard |

## The lift (the remaining build)

SEED9 (`willow-2.0/seed.py`, 1,791 lines) is the only seed with the experience
built. It imports `core.version` and `willow.fylgja.willow_home` from the 2.0
monorepo — two seams to cut. The lift: bring the page code here, re-plumb
install steps to the chain above (willow-mcp CLI + willow-data-vault provision,
no 2.0 imports), and voice each page from its chapter. Timing (now vs. after
kartikeya lands on PyPI) is the operator's call — the pages can be lifted and
voiced before the pip step works cold.

## Supersession map (once ratified)

- `willow-seed/seed.py` (plants willow-1.7) → retarget to the chain above, sourced from here
- `willow-seed/REPLANT.md` → historical
- `willow-mcp/docs/OPERATOR-ONBOARD.md` → "already have a fleet" appendix; seed calls the same CLI
- `willow-mcp/scripts/sandbox-bootstrap.sh` → dev-only, labeled as such

## The blocker, cleared

2026-07-22: operator published `kartikeya 0.0.7` and `willow-mcp 2.0.0` to PyPI
(Trusted Publisher registered after one `invalid-publisher` bounce). Cold proof ran
same day: fresh venv, PyPI-only packages, empty github root, new box — six
movements, six chain steps DONE, acceptance verdict `ok`. The seed runs cold.
