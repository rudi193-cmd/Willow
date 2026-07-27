# Handoff — box-audit remediation (2026-07-27)

Current status of the 2026-07-24 fleet box scan (`design/box-scan-2026-07-24.md`).
**Supersedes** `handoff-2026-07-25-box-audit-remediation.md` — that doc froze at
the first day's fixes; this one reflects the state after the second remediation
push closed the remaining hardening findings and most of the duplication.

**Bottom line:** every **B (hardening)** finding is remediated except low-latent
**B16**. On the **A (duplication)** side, A1–A8 and A10 are done; only **A9**
(trust-model unification) and low-severity **A11** remain. What's left is not a
live vulnerability — it's one architectural refactor, low-severity cleanup, and
a set of **operator/owner actions** to switch on controls that shipped
off-by-default.

## Landed since 2026-07-25

Off-by-default where it changes live behavior (fleet enforce-flag convention),
or purely additive/test+CI — so nothing broke on merge.

| Finding | Fix | PR |
|---|---|---|
| **B9** unauth `0.0.0.0` bind | public-ledger + vision-board default to `127.0.0.1`; wider bind via env override only; drift-guard | safe-app-store #106 |
| **B13** promotion-gate attestation gaps | dynamic import-time egress (`__import__`/`importlib`) caught; `vault_leak_lint` wired into the gate; CI-wired | safe-app-store #107, #108 |
| **B8** Canon-promotion gate | `mem_ratify` built (pure/stdlib, fail-closed, off-by-default `WILLOW_MEM_RATIFY_ENFORCE`) + stale `CONSTITUTION.md` `n2n_packets.py` citations retired | willow #14 |
| **B8** ingest wiring | `mem_ratify` wired into willow-mcp `knowledge_ingest` behind `WILLOW_MCP_ENFORCE_MEM_RATIFY` (off); default path byte-identical | willow-mcp #191 |
| **A1** vendored `subject_consent` | cross-repo drift-guard (copy is byte-identical to canonical; guard, not repoint) | willow-mcp #190 |
| **A2** utety two chains | verified **no residue** after utety#14 — one authoritative chain + display mirror; no PR needed | — |
| **A5** per-app boilerplate → `libs/` | `willow-read`, `willow-pg` (+ source-trail), `vault-paths` (12 resolvers + shims), `pg-sqlite-shim` | safe-app-store #92–94, #101–105, #109 |
| **A6/A7** signer + ledger convergence | golden-vector guards for the HMAC encoding; `governance_ledger` v2 covers id+project | willow-gate #23, willow-mcp #188, #189 |
| **A4** nest-seed pipeline (~1.3k identical lines) | extracted to canonical `libs/nest-pipeline`; nest-seed consumes it; willow-mcp vendors it with a drift-guard | safe-app-store #110, willow-mcp #192 |
| **A10** doctrine duplication | retired the superseded Article XIV file; disambiguated "tier"/"consent gate"/"Independent Witness"; cross-linked the sudo-invariant | willow #15 |

(Prior day, per the 2026-07-25 handoff: B1, B2-submit, B4, B5, B6, B7, B10, B11,
B12, B14, B15, A3, A8, and the B3 8-app SOIL gate-bypass were already merged.)

## Whole-box scorecard (2026-07-27)

**B — hardening:** B1 ✅ · B2 ⚠️ (submit-time enforced; executor recheck deferred
on kartikeya; flag off) · B3 ✅ · B4 ✅ · B5 ✅ · B6 ✅ · B7 ✅ · B8 ✅ (built +
wired, off) · B9 ✅ · B10 ✅ · B11 ✅ (one doc-honesty residual) · B12 ✅ (flags
off) · B13 ✅ (signing/seam deferred) · B14 ✅ · B15 ✅ · **B16 ❌ low-latent**.

**A — duplication:** A1 ✅ · A2 ✅ · A3 ✅ · A4 ✅ · A5 ✅ · A6 ✅ · A7 ✅ · A8 ✅ ·
**A9 ❌ (trust-model, architectural)** · A10 ✅ · **A11 ❌ low cleanup**.

## Owner / operator actions — nothing merges these but a human

These gate *turning controls on*, not merging code.

- **Enforce flags (all shipped OFF), after seeding state:**
  - `WILLOW_MCP_ENFORCE_DB_PERIMETER` — apply `docs/schema/tasks-add-db-authorization.sql`, issue db envelopes via `willow-mcp sign-db-task`.
  - `WILLOW_GATE_ENFORCE_EARNED_RUNGS` — seed `trust_tally.json` with already-trusted agents' earned levels (else they re-climb from zero).
  - `WILLOW_MCP_ENFORCE_MEM_RATIFY` + `WILLOW_MEM_RATIFY_ENFORCE` — a denial blocks only when **both** are on. **Before enabling:** the witness/quorum/tier-column metadata is not plumbed yet, so with both on it refuses *every* direct KB write (correct fail-closed, but confirm that's intended). Build the metadata path first (mem_ratify README follow-ups 1–3).
- **mem_ratify placeholders needing sign-off:** `FRONTIER_MIN_WITNESSES` / `CANONICAL_MIN_WITNESSES = 2`, `REQUIRE_STEPWISE_PROMOTION = True`. Independent-Witness *evidence quality* and Operator-Key/ledger checks are presence-only (real verification delegated to the wiring layer).
- **kartikeya:** add a `db_authorizer=` hook + `TaskRow.db_authorization` → unblocks B2's execution-time recheck (submit-time already enforced).
- **B2 flags** and the **receipt-binding implementation** (design in willow#11) remain as in the 2026-07-25 handoff.
- **B11 doc residual:** `AGENT_SERVICES.md` presents `authority_check` as live without disclosing its default-off kill-switch — fix wherever that doc lives.
- **A10 citation calls (docs-only, left for owner):** `envelopes/syscall-table.json` cites "PROTECTED_AGENTS §7" (maps to **W-6** in the W-/I- numbering); the constitutional `nest_rules.json` projection wants a distinct name from the shipped file-classifier (deferred to willow-2.0).
- **B13:** signing+verifying `promotion.json` and a `semantic_seam` smoke-test need a key-scheme / sandbox decision.
- **`FLEET_RO_TOKEN`:** the willow-mcp `vendor-sync` CI job now checks **four** vendored copies (friction_floor, subject_consent, mem_ratify, nest-pipeline); each cross-repo diff soft-skips until this read-only PAT is set (only matters if the upstreams are private).

## Still open — builds / refactors (not live vulnerabilities)

- **A9 — trust model in 3 incompatible shapes** (willow-gate 5-rung ladder vs willow-mcp `session_binder (name, read_only)` vs `PERMISSION_GROUPS`). One identity→authority model; the others derive from it. Architectural — wants a design pass, not a blind refactor.
- **B16 — low-latent:** SSRF allowlist not wired on `source-trail/sources_db.py` `urlopen` (guard exists dormant in willow-mcp `mai/parser.py`); `willow:willow` dev DB default left as a working runtime default; unscoped utety egress env var; column-name SQL-injection latent (safe today).
- **A11 — cleanup freebies:** dead `_archived/nestor/` copies, duplicated tokenizers, forked `jeles_persona.json`, the Fernet `vault.py` copy-chain.

## Patterns / decisions carried forward

- **Vendored-copy + two-sided drift-guard is now the fleet's standard** for cross-repo shared code where a real pip dep is awkward: an in-repo body-hash pin (catches local edits) + a `vendor-sync` CI diff against canonical (catches canonical advancing, soft-skips if unreachable). Now on **four** modules (friction_floor #185, subject_consent #190, mem_ratify #191, nest-pipeline #192). The long-term "publish a real package" move remains the owner's call.
- **`libs/` extraction** is the safe-app-store home for shared app code: `willow-read`, `willow-pg`, `vault-paths`, `pg-sqlite-shim`, `nest-pipeline`, `subject-consent`, `fleet-presence`. Each is stdlib-import-safe (heavy deps lazy), unit-tested with fakes, and wired into the store-ci compile sweep / app-tests lib-install where a consumer imports it.
- **Drift-guards as source scanners** landed in the store-ci `gates` job: no raw SOIL read (B3), no f-string schema SQL (A6/B13), no inline vault-root (A5), no hardcoded `0.0.0.0` bind (B9), plus the promotion-gate tests. They fail closed on reintroduction.
- **Off-by-default enforce flags** remain the way to land a control without breaking a running install; the operator flips them after seeding state.
- **Unkeyed hash chains** (receipts, governance_ledger, custody, trust-tally) are tamper-*evident* only within the OS-ownership boundary (`.db` owned by `willow-operator`). Load-bearing precondition — the #181 receipt-binding thesis.
- **Fail-closed for person-protecting flows** (utety B7 is on-by-default, not flag-gated).

## Environment notes for the next instance

- willow-mcp / Nestor tests need Postgres + `psycopg2` + `kartikeya`; they run only in CI's matrix (willow-mcp's `conftest` autouse fixture pulls the package in, so even a stdlib-only pin test can't be run from a bare box). Crypto/SQLite/pure tests run anywhere.
- utety, jeles, and the safe-app-store `libs/` are stdlib-only — full suites run locally in <1s.
- willow-gate gate tests run with `PYTHONPATH=src`; the custody suite needs the package installed.
- safe-app-store CI: `gates` (compile sweep over `apps libs stores …` + lints + drift-guards) is the whole-store floor; per-app suites run in `app-tests` (matrix) and the dedicated workflows, which `pip install -e` the libs they import.
- **willow grove** is slated for a fresh (greenfield) build — deliberately excluded from this remediation; no existing grove code was touched or is tracked here.
