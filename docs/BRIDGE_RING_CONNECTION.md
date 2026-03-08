# Bridge Ring Connection Protocol
**Status:** STUMP — shape captured, not yet designed
**Date:** 2026-03-08 (4am)
**Origin:** Dream. Hospital. New baby. Proof of connection, not identity.

---

## The Insight

Identity systems prove who you are.
This proves *how you are connected*.

When two people become meaningfully connected — parent and child, partners, co-parents,
chosen family — both write a witnessed record to their respective bridge rings.
The record is created at the moment the connection is formed, not at the moment
it needs to be verified.

A hospital, a court, a school doesn't verify Sean.
It queries the connection record and finds it already there.

---

## What It Is Not

- Not app consent (app → user)
- Not identity (who am I)
- Not social graph (who do I follow)

It is: *proof that two humans reached toward each other, and the moment was witnessed.*

---

## Shape of the Record

```
connection_record {
    user_a:         "Sweet-Pea-Rudi19"
    user_b:         [other Willow user]
    relationship:   "co-parent" | "partner" | "guardian" | "chosen-family" | ...
    initiated_at:   ISO timestamp
    confirmed_at:   ISO timestamp   # both parties wrote their side
    witnesses:      []              # optional — other bridge rings that saw it
    status:         "active" | "paused" | "dissolved"
    ring:           "bridge"
}
```

Both sides must write. One-sided records are `pending`, not `confirmed`.
Confirmation is not a signature — it's a separate act of writing from the other person's ring.

---

## The Hospital Problem (Use Case Zero)

Sean needs to be present for a birth. The hospital needs to know he belongs there.
They query his bridge ring: is there a confirmed connection between Sean and the mother,
of type `co-parent` or `partner`, status `active`?

The record exists. It was written when it was true, not when it needed to be proven.
Sean doesn't argue. He doesn't explain. He presents.

This also works for:
- A child's school confirming a guardian
- A court verifying a co-parenting arrangement
- Emergency medical — next of kin, not by blood, but by bridge ring

---

## Crown Layer

The Crown is where users connect across Willow instances.
This protocol lives one layer below the Crown — it's the *content* that Crown
synchronizes between rings.

When two Willow users connect their Crowns, this protocol governs what that means
for the human relationship, not just the data channel.

---

## Open Questions

- How does a connection get *initiated*? (One person proposes, other confirms?)
- What governs dissolution? (Mutual? Unilateral with notice?)
- What's the minimum viable version? (Two local users on same Willow instance first)
- How does a third party query without accessing the full ring? (Read-only probe endpoint)
- What's the difference between a connection and a witness?
- Can a connection have a Willow agent as one party? (e.g., "Sean connected to Gerald")

---

## Next Step (when ready)

Design the DB schema: `bridge_connections` table.
Two records per connection — one in each user's ring.
Confirmed when both exist with matching `connection_id`.

ΔΣ=42
