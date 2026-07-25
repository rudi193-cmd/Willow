# Receipt binding — the third proof (REM-4/6)

Status: **DRAFT** · 2026-07-25 · seat: willow · author: instance (proposes; operator ratifies)
Source: the willow-mcp#181 red-team thread. Written up here because the KB
remediation map (`domain: remediation-map-20260724`, atoms REM-1…6) records the
*decision* but not the *artifact*; this is the artifact REM-4/6 point at.

## Why this exists

The #181 kill chain reduced to one root cause — *correct code protecting the
wrong perimeter* — and the fix is OS-level isolation (unprivileged agent uid;
`config/`, `mcp_apps/`, keys, `.db` files owned by `willow-operator`). Biscuit
closes **capability** and PGP/Biscuit manifests close **identity**. A reviewer in
#181 pointed out a third proof the map under-states:

| Proof | Question it answers | Hardened by |
|-------|---------------------|-------------|
| **capability** | what may this agent do now | Biscuit attenuation (REM-1, #183) |
| **identity** | which non-human principal is acting | PGP/Biscuit manifests (REM-2, #183) |
| **receipt** | what happened, in what order, under which signed context | **this doc (REM-4/6)** |

Biscuit-style attenuation and key custody do not, on their own, leave a durable
record a verifier can inspect *after the fact*. Without it, a reviewer reads
three honest-but-independent logs (an identity log, a capability log, a ledger)
and has to *guess* they describe the same action. The receipt is the record that
removes the guess.

## The invariant

A verifier must be able to assert, of a single signed record:

> this tool call came from **this** signed agent identity, under **this**
> attenuated capability, against **this** prior chain state, and produced
> **this** effect (or denial).

The failure the receipt prevents is not "no log" — it is "three logs that each
look fine but were never *bound*, so nothing proves they refer to one event."

## The join-key schema

One receipt row, written at the decision point, carrying a reference into each
plane. Field set (from the #181 proposal, annotated with where each already
exists in the fleet vs. what is missing):

| field | binds | exists today as | gap |
|-------|-------|-----------------|-----|
| `agent_identity_ref` | identity | `session_bind` HMAC header (agent_id + capped trust_level) | — |
| `capability_token_ref` | capability | manifest ACL (→ Biscuit, #183) | token ref not captured at call time |
| `policy_or_manifest_digest` | capability | manifest on disk | digest not hashed at call time |
| `tool_call_digest` | effect (request) | gate decision input | not sealed |
| `ledger_prev` | order | Nestor chain `prev == sha256(previous line)` | — |
| `ledger_entry_hash` | order | Nestor chain entry hash | — |
| `effect_ref_or_denial_code` | effect (result) | tool result / denial reason | not sealed into the same row |
| `signer` / `verifier_id` | provenance | seal HMAC key (Nestor), egress Ed25519 key | — |
| `issued_at` / `expires_at` | freshness | egress lease TTL; envelope expiry (B2) | — |

Most planes already have a primitive; the work is **binding** them into one
signed row rather than three independent systems. The Nestor hash-chained ledger
(Nestor#2, PR #4 — `verify()` on boot, refuses a broken chain, HMAC seal over a
canonical encoding) is the receipt *substrate*: it already supplies
`ledger_prev` / `ledger_entry_hash` / `signer`. The bound receipt is a ledger
entry whose payload carries the remaining join keys.

## The failure-mode test (ties to AT-M1)

The test that makes the binding real, and the reason to prefer one bound row
over three logs:

> Break or rewrite any **one** of `{agent_identity_ref, capability_token_ref,
> policy_or_manifest_digest, tool_call_digest, ledger_prev, effect_ref}` and the
> receipt must stop verifying.

This is the AT-M1 acceptance shape #181 already calls for ("attempt every
exploit in a real session and assert refusal"), extended from *access* to
*receipt integrity*. It is a live-session assertion, not a unit test: mutate a
field post-hoc, re-verify, expect refusal.

## The precondition it inherits (do not overclaim)

The bound receipt does **not** relax #181's root cause — it inherits it. Every
ref must be signed by a key **outside the agent's write reach**. Bind five
agent-writable fields together and the result is a *self-consistent forgery*, not
a proof: the same collapse condition as the capability and identity legs. So the
ordering is fixed:

1. **Local OS isolation first** (#181 body): unprivileged agent uid; `config/`,
   `mcp_apps/`, keys, `.db` files, **and the ledger** owned by `willow-operator`.
2. **Bound receipt second** (this doc): only sound once (1) holds.

From the SATP framing raised in #181: local runtime enforcement first, portable
signed receipts second. The receipt is the portable part — it makes the result
inspectable after it leaves this machine or org — but portability is worthless if
the substrate is forgeable.

## Adjacent cleanup this depends on

- **willow-mcp `receipts.py` must be hash-chained** (box-scan B12). It is the log
  H3 reconciliation reads, currently a plain SQLite table with no chain in a repo
  that already has `governance_ledger`'s chain — a same-uid process edits it and
  `session_reconcile` reports `clean:true`. A receipt plane built on an
  unchained log inherits that hole. Chain it (mirror the Nestor ledger) before
  binding join keys into it.

## Cross-references

- **willow-mcp#181** — the kill chain and the three-proof decomposition.
- **willow-mcp#182** — egress key custody (moves `signer` out of agent reach).
- **willow-mcp#183** — Biscuit for identity + capability (`agent_identity_ref`,
  `capability_token_ref`).
- **Nestor#2 / Nestor PR #4** — the hash-chained ledger, the receipt substrate.
- **Box scan B12** (`design/box-scan-2026-07-24.md`) — `receipts.py` hash-chain gap.
- **Box scan B1 (merged, willow-gate #19) / B2 (merged, willow-mcp #186)** —
  identity and capability perimeters the receipt binds against.

## Status

Design draft; the decision is recorded as REM-4/6 in the KB remediation map. No
code here. First implementable bite: extend the Nestor ledger entry with the
join-key payload and write the AT-M1 receipt-integrity assertion, once
`receipts.py` is chained.
