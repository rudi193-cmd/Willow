# Handoff — box-audit remediation (2026-07-25)

> **Superseded by `handoff-2026-07-27-box-audit-remediation.md`** — kept for
> history (first-day fixes). See the 2026-07-27 doc for current status.

Continuation of the 2026-07-24 fleet box scan (`design/box-scan-2026-07-24.md`).
This session drove the audit findings to merged fixes across six repos. Below is
what landed, what's deferred (and on whom), and what's still open, so the next
instance can pick up without re-deriving.

## Landed — merged to default branches

Every fix is off-by-default where it changes live behavior (fleet enforce-flag
convention) or purely additive, so nothing broke on merge.

| Finding | Fix | PR |
|---|---|---|
| **B1** (CRITICAL) session forgery | authorize off the server-side session, not the caller's dict | willow-gate#19 |
| **B6** (willow-gate) | double check-out fails closed (GateError, not KeyError) | willow-gate#19 |
| **B12** self-certified rungs | rungs gated on a gate-witnessed tally (`WILLOW_GATE_ENFORCE_EARNED_RUNGS`, off) | willow-gate#22 |
| **B2** allow_db perimeter | operator-signed db envelope, submit-time (`WILLOW_MCP_ENFORCE_DB_PERIMETER`, off) | willow-mcp#186 |
| **B12** receipt integrity | hash-chained `receipts.py` + `verify()` wired into `session_reconcile` | willow-mcp#187 |
| **B11** no-op consent panel | relabel `cloud_llm`/`lan` "reserved — not enforced" | willow-mcp#187 |
| **A8** stale friction detector | re-sync vendored `friction_floor` + cross-repo drift-guard CI | willow-mcp#185 |
| **B4/B5/B10/B14** seal/ledger | collision-safe seal, single verified-seal helper, verify-on-boot, strict/symlink | Nestor#3, #4 |
| **B6/B15/A10** jeles | verification_kind, collection-name validation + hardening, independent-source rename | jeles#1 |
| **A3** SOIL schema drift | jeles carries willow-mcp's `deviation`/`action` columns | jeles#1 |
| **B7/A1/A2** utety consent | fail-closed gate on one authoritative `subject_consent` model | utety#14 |
| **B8** dead hooks | removed retired-fylgja `.cursor/hooks.json` | willow#12 |
| box-scan map + reaction-engine | the audit artifact + design | willow#10 |
| receipt-binding (REM-4/6) | the third-proof artifact from willow-mcp#181 | willow#11 |

## Deferred — with an owner

- **B2 execution-time recheck.** Submit-time enforcement landed; the executor
  recheck (`ExecutorDbAuthorizer`, single-use-per-row) is blocked on a
  **kartikeya** change: `run_worker` takes only a `network_authorizer=` hook and
  `TaskRow` has no db field. Needs a `db_authorizer=` hook + `TaskRow.db_authorization`
  in kartikeya, then wire it in willow-mcp/worker.py + gates_actions.py.
- **Enforcement flags are OFF by default** and need an operator to turn on after
  seeding state:
  - `WILLOW_MCP_ENFORCE_DB_PERIMETER` — needs the `tasks.db_authorization` column
    (`docs/schema/tasks-add-db-authorization.sql`) applied + mapping reconfirmed,
    and operators issuing db envelopes via `willow-mcp sign-db-task`.
  - `WILLOW_GATE_ENFORCE_EARNED_RUNGS` — needs `trust_tally.json` seeded with
    already-trusted agents' earned levels, else they'd re-climb from zero.
- **`FLEET_RO_TOKEN`** — the willow-mcp `vendor-sync` CI job soft-skips until this
  read-only PAT is set (only matters if willow-gate is private).
- **Receipt-binding implementation** — the artifact (willow#11) is a design; the
  build is: extend the Nestor ledger entry with the join-key payload + the AT-M1
  receipt-integrity assertion, once `receipts.py` chaining (done, willow-mcp#187)
  is available fleet-wide.
- **B11 doc-honesty residual** — a doc presents `authority_check` as live without
  disclosing its default-off kill-switch. That doc is not in willow-mcp; find and
  fix wherever `AGENT_SERVICES.md` lives.

## Still open — NOT hardening (deliberate builds / refactors)

- **B3 — 8-app SOIL gate-bypass (safe-app-store).** The one remaining *hardening*
  finding. ~8 hosted apps read raw SOIL around the gate. Needs the app-framework
  scouted first, then the gate wired into each. Multi-app.
- **B8 `mem_ratify`** — unbuilt. A build, not a fix.
- **A-series duplication refactors:**
  - **A1** — promote `subject_consent` to a real published package (utety now
    consumes it correctly after #14; the canonical-lib promotion remains).
  - **A2** — utety's consent is consolidated (#14); the broader "two hash-chains"
    dedup (disclosure vs consent) may have residue to converge.
  - **A4** — `nest-seed` content pipeline → package (~3k byte-identical lines).
  - **A5** — safe-app-store per-app boilerplate → `libs/` (pigeon, vault-paths,
    pg-sqlite-shim); already drifting.
  - **A6/A7** — converge the divergent HMAC signers and hash-chain ledgers onto
    one canonical implementation (security-adjacent; good next target).

## Patterns / decisions worth carrying forward

- **Off-by-default enforce flags** are the fleet way to land a control without
  breaking the running install; the operator flips them after seeding state.
  Reused for B2 and B12-rungs.
- **Unkeyed hash chains** (receipts, governance_ledger, custody, the trust tally)
  are tamper-*evident* only within the OS-ownership boundary — the `.db`/files
  owned by `willow-operator`, agent uid can't write them (willow-mcp#181). That
  precondition is load-bearing; the chains do not stand alone against a same-uid
  attacker. This is the whole thesis of the #181 receipt-binding artifact.
- **Fail-closed** for anything protecting a person, especially children (utety B7
  is on-by-default, not flag-gated): a safety gate you can forget to enable is
  the B11 anti-pattern.
- **Vendored copies need a drift-guard.** willow-mcp#185 added both an in-repo
  hash pin and a cross-repo CI diff; apply the same when promoting A1/A4/A5.

## Environment notes for the next instance

- willow-mcp / Nestor tests need Postgres + `psycopg2` + the `kartikeya` package;
  they only run in CI's matrix, not a bare box. Crypto/SQLite tests run anywhere.
- utety and jeles are stdlib-only — full suites run locally in <1s.
- willow-gate gate tests run with `PYTHONPATH=src`; the custody suite needs the
  package installed.
