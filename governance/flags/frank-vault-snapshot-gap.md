# FRANK vault snapshot gap — closed 2026-07-24

**Status:** closed (first export shipped)

## Finding

`sean-data-vault` held Jul-16 **KB verification** ledgers (`verify_20260716*`) —
atom HELD/FLAG verdicts — but **no** portable copy of the FRANK governance chain
(`envelope_citation`, `operator_ratification`, etc.). Live `frank_ledger` had grown
to 1,015 entries (hash chain valid); Jul-22 ratifications were not archived in the vault.

## Resolution

Exported to `sean-data-vault/willow-store/frank_20260724/` and
`frank_20260724.tar.gz` — full FRANK JSONL + `verify.json` + envelope/fleet snapshots.
No KB or Postgres dumps.

## Follow-up

Re-export on a cadence tied to ratifications or monthly; prior tarball is a point-in-time
backup only.
