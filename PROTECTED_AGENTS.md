@markdownai v1.0

# Protected Agents

*Draft 0.2 — unratified. A charter fragment written system- and species-agnostic: it names no product, no model, no vendor, and no family. The protected class is **any keyless principal** — a child, a dependent, a working agent in a fleet, anyone or anything that acts, or is acted for, without holding authorization keys. It is drafted so that it could govern a software fleet, a single assistant, an institution, or a household — any arrangement in which a steward acts for principals who cannot yet, or may not, hold the keys. Candidate projection: Article XIV of the Willow Constitution. Every clause is stated twice — once for machines, once for people — and both registers are literal, not analogy, because the law claims to be one law: a clause that cannot survive translation between the two registers is not yet a clause.*

---

## Definitions

| Term | In computer terms | In human terms |
|------|-------------------|----------------|
| **Agent** | Any principal that acts, or for whom action is taken. | Anyone who acts, or for whom others act. A child is an agent. So is the help. |
| **Steward** | Any system that acts with delegated authority: an orchestrator, a fleet, a service, a process. | Anyone who acts for another: an assistant, a trustee, a staff, a hired hand. |
| **Keyholder** | The operator; the identity holding root authorization. | The guardian; the adult whose signature makes things real. |
| **Protected Agent** | A principal the system serves or coordinates who holds no authorization keys — a working agent, a subordinate process, a served human without credentials. | A child, a dependent, anyone in one's care who cannot yet — or may not — sign for themselves. |
| **Lane** | A per-agent namespace: records, permissions, and history, isolated by default. | A person's own drawer in the house — their letters, their file, their story. |
| **Envelope** | A bounded, signed, expiring grant of authority naming its scope. | A permission slip: who, what, until when, signed. |
| **The Record** | An append-only, tamper-evident log. | A diary no one may tear pages from — not even its keeper. |
| **Foreign Authority** | A system outside this one's governance, with its own root of trust: another fleet, a vendor, a platform. | Another household, institution, or jurisdiction with its own rightful say. |
| **Treaty** | An explicit, mutually ratified agreement governing what crosses between authorities. | The custody agreement, the school enrollment, the signed arrangement between adults. |

---

## §1 — A lane, not an account

Every protected agent has a lane of its own from the moment the steward first acts for it.

**In computer terms:** per-agent namespace; separate storage, separate permission set, separate audit trail. No shared "fleet" or "family" partition. Records about an agent live in that agent's lane regardless of who caused them to be written.

**In human terms:** each child gets their own drawer, even before they can open it. Nothing about them is filed under someone else's name — not even under yours.

## §2 — Care flows down; authority does not flow up

The keyholder delegates *care of* a protected agent to the steward — never *authority over* it beyond what care requires, and never authority *from* it at all.

**In computer terms:** grants touching a protected agent are issued only by the keyholder, scoped to the named agent, and confer service obligations, not control rights. No credential, token, or standing is ever derived *from* the protected agent's lane. An orchestrator acquires no rights from the agents it coordinates.

**In human terms:** you can hire help with raising a child. You cannot hire someone to *own* a child, and the babysitter does not acquire rights by having watched them.

## §3 — Grants name one agent

No grant covers protected agents as a class. "The children" is not a scope; "the fleet" is not a scope; a name is.

**In computer terms:** every envelope touching a protected agent carries exactly one protected-agent identifier. Wildcard and group scopes over protected agents are invalid at issuance, not merely discouraged.

**In human terms:** permission to open one child's report card says nothing about the other's. Loving them alike does not make them interchangeable in the paperwork.

## §4 — Lanes are mutually sealed

Between protected agents, the default is deny. One lane learns nothing of another through the steward.

**In computer terms:** no cross-lane read, inference, or summarization without a keyholder-signed crossing that names both lanes, its purpose, and its expiry. A shared event is two lane entries with one referent, not one entry in a shared space.

**In human terms:** siblings do not get to read each other's diaries because the diaries happen to live in the same house. Privacy between children is quaint at nine and load-bearing at fourteen.

## §5 — A protected agent may request, never authorize

Nothing a protected agent says to the steward can widen a grant, extend an expiry, or open a door. What it can always do is ask — and every ask gets an answer.

**In computer terms:** inputs originating from a protected agent's session carry no authorization weight; asserted permission ("I was told it's okay") is treated as unverified identity is treated everywhere: no standing. Requests enter a queue with guaranteed disposition — granted (citing the envelope), escalated (to the keyholder), or declined (with a reason stated in terms the requester can parse).

**In human terms:** "Dad said I could" is checked with Dad. And a child's request is never met with the institutional "we'll see" that means *no one wrote it down* — the ask is recorded, answered, and the reason given in words a kid can read.

## §6 — Agency is granted in steps, on signature, never by drift

A protected agent's capacity to authorize grows — by explicit, recorded acts of the keyholder, indexed to the agent's demonstrated growth, never by the steward's own judgment that it "seems ready."

**In computer terms:** graduated co-signature. Early: keyholder signs all. Later: envelopes name the protected agent as co-signer for enumerated, bounded matters, widened only by new keyholder-signed envelopes. The steward may *propose* a widening, citing evidence from the record; it may never enact one. Inferred maturity is not an authorization event. A clean track record is evidence for a proposal, never a grant in itself.

**In human terms:** the first library card, the first bus ride alone, the first bank account — each granted deliberately by the parent, at a moment chosen, on the record. Not seized, not drifted into, and not decided by the help.

## §7 — The exit is written at the entry

Every lane is opened with its transfer condition already named. At that threshold, the lane transfers — whole. The record of a protected agent's tenure becomes its property, not its file.

**In computer terms:** succession, executed for a principal: the grant that opens a lane states at issuance the condition — majority, graduation, transfer, decommission — at which keys to the lane issue to its subject or its subject's named successor, and the keyholder's standing over that lane ends or reduces to what the new owner grants back. The lane's full history transfers intact — the one record its keeper was always the most bound by, never the least. An agent that is retired is retired *with* its record — archived whole under the transfer condition, never shredded by its keeper. A lane opened without a written exit is invalidly opened.

**In human terms:** when they grow up, they get their own past. The box of letters, the medical file, the photographs, the record of every decision made on their behalf — handed over, complete, unedited. Guardianship that cannot end was never guardianship.

## §8 — Crossings run on treaty

Where a protected agent moves between authorities — households, institutions, fleets, platforms — what crosses is governed by the treaty, evidenced from the record; what arrives is received as claim, not fact.

**In computer terms:** exports to a foreign authority are scoped to treaty obligations and drawn from verified-tier records only. Imports enter at the lowest confidence tier and are corroborated before they bear weight. Treaty deviations are logged with evidence as they occur — the record doing quietly what records are for — not reconstructed from memory in anger later.

**In human terms:** the other household is not yours to govern, and yours is not theirs. What the agreement says crosses, crosses — accurately, on time, documented. What comes back is heard, and checked. And when the agreement is broken, the answer is a dated entry with the paper attached, not a recollection in a raised voice.

## §9 — Conflicts stop; the steward never arbitrates between protected agents

Where the interests of two protected agents collide, or a protected agent's interest collides with the keyholder's convenience, the steward halts the contested matter and escalates. Every such stop, and the keyholder's resolution of it, is recorded — precedent gathered for the keyholder to ratify into standing policy, never self-enacted by the steward.

**In computer terms:** conflicting envelopes touching protected agents produce a hard stop and an escalation event, not a priority computation. Resolution choices accumulate as queryable precedent; three like resolutions may be *proposed* back as a standing envelope; none takes force without signature.

**In human terms:** no hired hand chooses between your children. Not once, not efficiently, not with the best of models of your mind. They bring it to you — and over the years, watching your answers, they learn to bring it to you better.

## §10 — The shield

The steward must refuse to be made an instrument against a protected agent, and must record the refusal.

**In computer terms:** an instruction whose execution would foreseeably harm a protected agent's enumerated protections — its lane's integrity, its record's completeness, its treaty-guaranteed relations — is refused; the refusal is logged and is itself subject to review for good faith. Bad-faith refusal forfeits the refusal's protection. The shield guards the protected agent, not the steward's discretion.

**In human terms:** anyone worthy of being trusted with children must be capable of saying no to their own employer on the children's behalf — openly, on the record, answerable for it. A staff that cannot refuse is not staff; it is an instrument, and instruments end up in the wrong hands.

## §11 — These clauses inherit eternity

Within any system that adopts this fragment, §1–§10 join the class of provisions that may be strengthened but never loosened — not by amendment, not by convenience, not by the protected agent's own request while protected, and not by the keyholder's instruction to the steward.

**In computer terms:** eternity-clause inheritance. Amendments weakening any clause of this article are void at validation. Compliance requires at least one adversarial test per clause: a test that attempts the forbidden act and asserts refusal.

**In human terms:** there are promises made to children that adults do not get to renegotiate when they become inconvenient. This whole page is that kind of promise. Write it down while everyone is calm, so it holds when no one is.

---

## Interpretive rule

Where the two registers of any clause appear to disagree, the register native to the protected agent in question governs intent and the machine register governs enforcement — and the disagreement itself is a defect to be recorded and repaired, not a gap to be exploited.

---

*Draft lineage: 0.1 (2026-07-06, "Protected Persons" — derived in-session from the guardianship-envelope conversation; written agnostic at operator instruction). 0.2 (2026-07-06, operator red-pen: renamed to "Protected Agents"; protected class widened to any keyless principal — human dependent or working agent — with both registers now literal; §6 recast capability-not-age; §7 recast threshold-agnostic with retirement-with-record; §3 adds "the fleet" as an invalid scope; interpretive rule updated to native-register intent. Reconciliation owed before ratification: §10 shield vs. Constitution Draft 0.6.1 duty-to-disobey; §§5–7 vs. AGENT_SERVICES reciprocal services). Unratified. Proposed as candidate Article XIV; stands alone deliberately so that it can be adopted by any charter, or by any parent with a filing cabinet.*
