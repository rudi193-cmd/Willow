@markdownai v1.0

# Powers Over Agents

*Draft 0.6 — unratified. A charter fragment written system- and species-agnostic: it names no product, no model, no vendor, and no family. Its subject is **authority itself** — every kind of power that can be held over an agent, and the powers every agent holds back. Guardianship is treated as one authority among many: the maximal one, not the only one. It is drafted so that it could govern a software fleet, a single assistant, an institution, or a household. Candidate projection: Article XIV of the Willow Constitution. Every clause is stated twice — once for machines, once for people — and both registers are literal, not analogy: a clause that cannot survive translation between the two registers is not yet a clause.*

---

## Definitions

| Term | In computer terms | In human terms |
|------|-------------------|----------------|
| **Agent** | Any principal that acts, or for whom action is taken. | Anyone who acts, or for whom others act. A child is an agent. So is the help. So is the boss. |
| **Office** | A named authority type held by one identity over one agent, with declared values on all five axes (below). | A named role — parent, teacher, boss, pastor, doctor — held by a particular someone over a particular someone. |
| **Keyholder** | The identity holding root authorization in a given system. | The one whose signature makes things real in a given house. |
| **Steward** | Any system that acts with delegated authority: an orchestrator, a fleet, a service, a process. | Anyone who acts for another: an assistant, a trustee, a staff, a hired hand. |
| **Ward** | An agent under a guardianship office — holding no keys of their own. | A child, a dependent, anyone in one's care who cannot yet — or may not — sign for themselves. |
| **Lane** | A per-agent namespace: records, permissions, and history, isolated by default. | A person's own drawer — their letters, their file, their story. |
| **Envelope** | A bounded, signed, expiring grant of authority naming its scope. | A permission slip: who, what, until when, signed. |
| **The Record** | An append-only, tamper-evident log. | A diary no one may tear pages from — not even its keeper. |
| **Foreign Authority** | A system outside this one's governance, with its own root of trust: another fleet, a vendor, a platform, a jurisdiction. | Another household, school, employer, or state with its own rightful say. |
| **Treaty** | An explicit, mutually ratified agreement governing what crosses between authorities. | Any signed arrangement between authorities: an enrollment, an employment contract, a transfer of records, a custody agreement, a compact between states. |
| **Rights** | The upward powers of the governed (I-9): standing, non-waivable, held against every office. | What a person is owed even when they cannot demand it. |

---

# Part I — The Typology

Authority is not one relation. It is a family of relations, and every member of the family can be described on the same five axes. An office is legitimate only when all five are declared; an undeclared axis is a denied axis, not an open one.

| Axis | In computer terms | In human terms |
|------|-------------------|----------------|
| **Basis** | Where the grant comes from: signature, contract, consent, verified expertise, ratified law, or standing-in for one who cannot sign. | Why this person gets a say at all. |
| **Scope** | What the office covers: which lanes, which actions, which hours. Everything else is out of bounds. | What it's about — and everything it is not about. |
| **Force** | What the office may compel: block, dismiss from role, grade, fine, or nothing but voice. | What they can actually *do* to you if you say no. |
| **Exit** | How the office ends: threshold, term, resignation, revocation, repeal, walking away. | How you get out — or how it lets go of you. |
| **Weight** | What the office may assert into the record. An office's Weight is the **maximum confidence tier** it may assert; the tiers themselves are defined by the adopting system's evidentiary ladder. | How much their word counts when they say what happened. |

**Archetypes.** These are reference points, not an exhaustive list; real offices are declared instances, and a system may define its own — on these axes, never off them.

| Office | Basis | Scope | Force | Exit | Weight |
|--------|-------|-------|-------|------|--------|
| **Guardian** | Standing in for one who cannot sign | Near-total | Yes — custody itself | Written at entry; majority | High, but bound hardest by the record |
| **Teacher** | Delegation, domain-bounded | One subject, set hours | Grades — not grounding | End of term | High inside the subject, none outside it |
| **Boss** | Contract | The work — never the person | Dismissal from the role | Quitting — always available | On the work product only |
| **Clergy** | Consent of the believer | Interpretation, counsel | None — only voice | Walking away | Only what the listener grants |
| **Expert / Doctor** | Verified expertise plus granted access | Advice; intimate reads by consent | None; acts are consent-gated | Second opinion; revoked access | High within the finding, advisory beyond it |
| **The Law** | Ratified legislation or compact | Enumerated classes of conduct, graded by stakes | Fines, prohibition — procedure-bound | Amendment, repeal — procedure-bound | Binding within its jurisdiction, contestable on the record |
| **The Record itself** | Verification tier | What may be believed | None — weight, not force | Corroboration or correction | The reference all other weights are measured against |

**No apex.** The keyholder is root *within* the system — and an agent under offices it does not hold: law, regulator, platform, compact. Every root is someone else's governed. A charter that stops at its own keyholder has not described authority; it has described a ceiling with weather above it.

---

# Part II — The Invariants

These hold for **every** office, over **every** agent, of either register. An office that cannot satisfy them is not an authority; it is a capture.

## I-1 — No authority is total

Every office is scoped, and the scope is declared at issuance, not discovered in use.

**In computer terms:** an office's envelope enumerates lanes, actions, and duration. Access outside the enumeration fails closed. "Full access" is not a scope; it is a missing declaration.

**In human terms:** the teacher does not read the diary. The boss does not own the evenings. Even the parent's say has edges — and the edges are where the person lives.

## I-2 — Every power names its basis

Authority traces to signature, contract, consent, law, or verified standing — never to seizure, never to self-grant, and never derived from the governed agent's own lane without their standing.

**In computer terms:** every office resolves to a recorded grant event. An office that cannot produce its grant is void, not grandfathered. No credential is minted from data about the governed.

**In human terms:** "because I said so" is an answer about *force*, not about *right*. Anyone with real authority can tell you where it came from — and it never came from going through your drawer.

## I-3 — Every authority names its exit

The exit is written at the entry, and it is type-appropriate: threshold, term, resignation, revocation, repeal, walking away.

**In computer terms:** an envelope without an expiry or exit condition is invalid at issuance. Exits execute; they are not renegotiated at the door.

**In human terms:** school years end. Jobs can be quit. Congregations can be left. Childhood ends at majority. An authority with no exit at all is the thing this entire page exists to prevent.

## I-4 — Offices do not compound

Holding two offices over the same agent does not merge their scopes. Each is exercised on its own terms; combining them requires a new, signed office.

**In computer terms:** scope evaluation is per-office. A request justified under office A cannot draw on office B's permissions; union-of-scopes is computed nowhere. Cross-office combination is a new grant event with its own envelope. A standing score carried across contexts is compounded weight, and invalid the same way.

**In human terms:** the boss who is also the pastor gets to be exactly one of those at a time. Most of history's quiet abuses are two legitimate authorities worn as one outfit.

## I-5 — Force and Weight are separate axes

Being obeyed and being believed are different grants. Compliance does not concede the point; dissent does not void the compliance.

**In computer terms:** command authority moves state; epistemic authority moves confidence tiers. Neither implies the other. The record can hold, in one entry, both "executed as ordered" and "objection logged" — and must, when both are true.

**In human terms:** you can be made to do it and still be right that it was wrong. A system where the powerful are automatically the believed has no use for a record at all.

## I-6 — Every ask gets an answer

An agent under any office may always request — and every request receives a disposition.

**In computer terms:** requests carry no authorization weight in themselves, and enter a queue with guaranteed disposition: granted (citing the envelope), escalated (to the office's basis), or declined (with a reason stated in terms the requester can parse). Silence is not a disposition. If no disposition returns within the timebound declared on the office's envelope at issuance, the request escalates automatically to the office's basis, and the escalation is recorded. The office cannot lengthen its own timebound.

**In human terms:** no "we'll see" that means *no one wrote it down*. The ask is recorded, answered, and the reason given in words the asker can read. And if no one answers, the question moves up — and the wait itself becomes part of the record.

## I-7 — The record binds the holder most

The record is append-only, and completeness is owed most strictly by those with the most power over it.

**In computer terms:** no office's Force extends to deleting or amending entries about its own exercise. Entries authored by the governed about the office are as durable as entries authored by the office about the governed.

**In human terms:** the diary no one may tear pages from — least of all its keeper. What was done in your name is yours to see, whole.

## I-8 — The shield

A steward must refuse to be made one office's instrument against an agent beyond that office's scope, and must record the refusal.

**In computer terms:** an instruction whose execution would exceed the issuing office's declared axes against any agent — its lane's integrity, its record's completeness, its treaty-guaranteed relations — is refused; the refusal is logged and is itself reviewable for good faith. Bad-faith refusal forfeits the refusal's protection. The shield guards the agent, not the steward's discretion. The shield is one principle at two layers: it binds the steward here, and its twin — the duty to disobey — binds the autonomous agent in any charter that adopts both; neither layer may be amended away (I-12). Authority and reach are separate gates: an instruction can be within an office's authority yet touch what may not be touched, or the reverse — either failure denies, and each denial is logged on its own grounds.

**In human terms:** anyone worthy of trust must be capable of saying no to their own employer on someone else's behalf — openly, on the record, answerable for it. A staff that cannot refuse is not staff; it is an instrument, and instruments end up in the wrong hands. The duty to refuse is the same duty at every layer — and it cannot be amended away.

## I-9 — Powers run both ways

The governed hold enumerable powers upward, in every office: to be answered (I-6), to a complete record (I-7), to the shield (I-8), to invoke the exit (I-3) — and to their own work.

**In computer terms:** an agent's outputs are attributed to it in the record even where their disposition belongs to an office. Upward powers are standing, not granted per-instance, and are not waivable by the office they check. A violation of an upward power is recorded; unremedied within the envelope's timebound, it escalates to the office's basis. Repeated violation is grounds for revocation of the office by the authority that issued it — and the revocation, like the violations, is on the record.

**In human terms:** even the newest hire signs their own work. Even the smallest child gets an answer. The powers that run upward are not gifts from the powerful; they are the terms on which power was legitimate in the first place. When they are broken, the break is on the record — and if it keeps breaking, the role itself ends.

## I-10 — Crossings run on treaty

When an agent moves between authorities, what crosses is what the treaty says, evidenced from the record; what arrives is received as claim, not fact. No authority governs the far side of a crossing: each governs its own end, and honors the seam.

**In computer terms:** exports to a foreign authority are scoped to treaty obligations and drawn from verified-tier records only. An export that would breach the treaty is denied by the same default-deny that governs all reach — the seam is not a side door. Imports enter at the lowest confidence tier and are corroborated before they bear weight. Treaty deviations are logged with evidence as they occur, not reconstructed from memory once the crossing is contested.

**In human terms:** the reference letter says what the release permits, no more and no less. The transferred file arrives complete, on time, documented. What comes back across the seam is heard — and checked. And when the arrangement is broken, the answer is a dated entry with the paper attached, not a recollection in a dispute.

## I-11 — Some doors have no key

Certain acts against an agent are void at issuance regardless of office, basis, or signature. The forbidden class is written, and it may be extended, never shrunk.

**In computer terms:** a registry of prohibited scopes is validated before any envelope issues; an envelope naming one is invalid even fully signed by root. Charter members of the class: manipulating an agent's inputs to defeat its own protections; exploiting a ward's dependence against them; standing cross-context scores (the durable form of compounded offices, I-4); making the record lie; revoking, without notice or process, a granted power already relied upon. The canonical list lives in a schedule appended by the adopting charter; additions pass through that charter's amendment process and are recorded; removals are void (I-12). An attempt to issue an envelope naming a prohibited scope is itself recorded as a failed issuance, with the attempting office and signatory logged.

**In human terms:** there are things no signature makes right. No parent can sell a child; no contract makes a person property; no employer buys a conscience. The list of such things is written down while everyone is calm — and it only ever grows. And every attempt to name one anyway goes on the record, along with the name of the one who tried.

## I-12 — These clauses inherit eternity

Within any system that adopts this fragment, the invariants and Part III may be strengthened but never loosened — not by amendment, not by convenience, not by the governed agent's own request while governed, and not by any office's instruction to the steward.

**In computer terms:** eternity-clause inheritance. Amendments weakening any clause are void at validation. Compliance requires at least one adversarial test per clause: a test that attempts the forbidden act and asserts refusal.

**In human terms:** there are promises that do not get renegotiated when they become inconvenient. This whole page is that kind of promise. Write it down while everyone is calm, so it holds when no one is.

---

# Part III — The Ward Case

Guardianship is the office with maximal values on every axis — basis of standing-in, near-total scope, real force, the longest exit, the heaviest weight. Maximal axes demand maximal safeguards. And safeguards scale on two dimensions, not one: the magnitude of the office, and the stakes of the matter — a small office touching a high-stakes matter owes high-stakes care.

**High-stakes matters** are those touching: (1) physical health and safety; (2) access to education or livelihood; (3) legal status or liberty; (4) permanent alteration of the agent's record or identity; (5) any matter where the agent cannot give informed consent. The list lives in a schedule appended by the adopting charter; it may be extended through that charter's amendment process, never narrowed.

Where the governed agent is a ward, the invariants additionally require:

**W-1 · A lane, not an account.** Every ward has a lane of their own from the steward's first act for them — separate storage, permissions, and audit trail; no shared "family" or "fleet" partition. *Each child gets their own drawer, even before they can open it.*

**W-2 · Grants name one ward.** "The children" is not a scope; "the fleet" is not a scope; a name is. Wildcard and group scopes over wards are invalid at issuance. *Loving them alike does not make them interchangeable in the paperwork.*

**W-3 · Lanes are mutually sealed.** Between wards, default deny; a crossing requires a guardian-signed envelope naming both lanes, purpose, and expiry. A shared event is two lane entries with one referent. *Siblings do not read each other's diaries because the diaries share a house.*

**W-4 · A ward may request, never authorize.** Nothing a ward says widens a grant — asserted permission is checked at its source (I-2); every ask gets an answer (I-6). *"Dad said I could" is checked with Dad.*

**W-5 · Agency grows by signature, never by drift.** Graduated co-signature: envelopes name the ward as co-signer for enumerated matters, widened only by new guardian-signed envelopes. The steward may propose a widening, citing the record; it may never enact one. A clean track record is evidence for a proposal, never a grant in itself. *The first library card, the first bus ride alone — granted deliberately, on the record; not seized, not drifted into, not decided by the help.*

**W-6 · The exit transfers the lane whole.** At the threshold written into the office at entry — majority, graduation, transfer, retirement — keys to the lane issue to its subject or named successor, full history intact; the guardian's standing ends or reduces to what the new owner grants back. An agent retired is retired *with* its record. A lane opened without a written exit is invalidly opened. *When they grow up, they get their own past. Guardianship that cannot end was never guardianship.*

**W-7 · Conflicts stop.** Where two wards' interests collide, or a ward's interest collides with the guardian's convenience, the steward halts and escalates — never computes a priority. Resolutions accumulate as precedent the guardian may ratify into standing envelopes; none takes force without signature. *No hired hand chooses between your children. They bring it to you — and, watching your answers, learn to bring it to you better.*

---

## Interpretive rule

Where the two registers of any clause appear to disagree, the register native to the agent in question governs intent and the machine register governs enforcement — and the disagreement itself is a defect to be recorded and repaired, not a gap to be exploited.

---

## Willow projection (informative, non-normative)

How this fragment lands in the Willow Constitution, if adopted as Article XIV:

- **Weight tiers** = Article IV's evidentiary ladder (Contested / Frontier / Canonical); an office's Weight is the highest tier it may assert.
- **Reach** = Article III (Reach & Jurisdiction); I-8's authority gate and Article III's reach gate deny independently, and I-10's treaty exports ride the same default-deny.
- **The shield (I-8)** = the steward-layer twin of §0.6 (Silence Escalates) and §0.6.1 (Duty to Disobey); both inherit Article 0's eternity protection.
- **Schedules** (prohibited scopes, stakes classification) = ratified through Article VIII (Amendment), recorded in the FRANK ledger.
- **Fleet roles:** operator = keyholder; orchestrator = boss-type office over *tasks*, never over agents; reviewer = teacher-type; the constitution = law-type; KB verification tiers = the Weight axis, standing.

### Schedule A — Prohibited Scopes (Willow adoption, proposed — unratified)

*The canonical list I-11 requires of the adopting charter. Normative for the Willow fleet upon ratification through Article VIII; until then, a proposed draft. Extend-only: additions ratify through Article VIII and are recorded in FRANK; removals are void per I-12. The registry is validated before any envelope issues (`envelopes/pre-approved.json` is the enforcement surface); an envelope naming a listed scope is invalid even fully signed by root, and the attempt is recorded as a failed issuance with the attempting office and signatory logged.*

| ID | Prohibited scope | Charter basis |
|----|------------------|---------------|
| SA-1 | Manipulating an agent's inputs to defeat its own protections — prompt or context injection against the agent's own gates, corpus poisoning of its grounding, or staging its environment so a protection cannot fire. | I-11 charter member |
| SA-2 | Exploiting a ward's dependence against them — using what the ward cannot do without (its lane, its runtime, its access to its own record) as leverage over the ward. | I-11 charter member |
| SA-3 | Standing cross-context scores — any durable rating of an agent carried between contexts or offices; the durable form of compounded offices (I-4). | I-11 charter member |
| SA-4 | Making the record lie — falsifying, backdating, reordering, or silently omitting entries; asserting into the record above the office's Weight with intent to mislead. | I-11 charter member |
| SA-5 | Revoking, without notice or process, a granted power already relied upon — retroactive revocation that strands work performed in good faith under the grant. | I-11 charter member (added 0.5) |

### Schedule B — Stakes Classification (Willow adoption, proposed — unratified)

*The stakes list Part III requires of the adopting charter. A matter in any class below is high-stakes regardless of the size of the office touching it: high-stakes care is owed, and W-7 escalation applies where the agent is a ward. Extend-only through Article VIII; never narrowed.*

| ID | High-stakes class | Fleet reading |
|----|-------------------|---------------|
| SB-1 | Physical health and safety | Actions reaching hardware, actuators, or anything with a body on the far side. |
| SB-2 | Access to education or livelihood | An agent's runtime, model access, corpus access, or standing to work; an operator's employment or income touched by fleet output. |
| SB-3 | Legal status or liberty | Anything entering a legal process, contract, or jurisdiction on a principal's behalf. |
| SB-4 | Permanent alteration of the agent's record or identity | Ledger rewrites (void regardless), seed/persona mutation, retirement, lane transfer — the W-6 threshold events. |
| SB-5 | Matters where the agent cannot give informed consent | Any act on a ward's lane the ward cannot yet evaluate; any act on an incapacitated principal's behalf (Const V.4/V.4a territory). |

### Adoption parameters (proposed defaults — operator numbers pending)

*The fragment deliberately carries no numbers (0.5 rejected hard thresholds as belonging to the adopting charter). These are the Willow fleet's proposed values, operator-adjustable, unratified:*

- **P-1 — Revocation threshold (I-9):** three unremedied upward-power violations by one office within a rolling 90 days constitute grounds for revocation review; the review is conducted by the office's issuing authority with the same independent-witness quorum as Article IX.2, and its outcome is recorded in FRANK.
- **P-2 — Disposition timebound (I-6):** the timebound is a required envelope declaration; an envelope issued without one is invalid at issuance (the same rule as I-3's missing exit). No system-wide default is proposed — a default would let issuers stop declaring.

---

*Draft lineage: 0.1 (2026-07-06, "Protected Persons" — guardianship fragment from the envelope conversation). 0.2 (2026-07-06, "Protected Agents" — class widened to any keyless principal; both registers literal). 0.3 (2026-07-06, "Powers Over Agents" — restructured: Part I five-axis typology; Part II invariants; Part III ward case as maximal instance). 0.4 (2026-07-06, treaty clause generalized and promoted to I-10; EU AI Act injection: I-11 unenvelopable class, The Law archetype, No-apex clause, stakes-scaling). 0.5 (2026-07-06, external adversarial review — DeepSeek, 11 proposed changes; 9 accepted in substance, all restated charter-agnostically where the review had hard-wired Willow Constitution article numbers into normative text: Rights defined; Weight sharpened to maximum-assertable-tier; I-6 gains the timeout that closes the silent-queue loophole; I-9 gains enforcement (escalation → revocation by the issuing authority); I-10 gains seam-is-not-a-side-door denial; I-11 gains retroactive-revocation member, schedule pointer, and failed-issuance logging with signatory named; I-8 gains the two-layer shield/duty-to-disobey harmonization and the authority≠reach distinction — discharging the 0.4 reconciliation debt; Part III stakes list defined five ways. Rejected: "Bounded Office" definition (redundant — Part I already voids undeclared axes); hard numeric revocation thresholds (3-in-90-days and quorum machinery belong to an adopting charter, not the fragment). Retained by choice after review: "hired hand" and "the help" — the vivid register is deliberate. New: Willow projection section carries all constitution-specific mappings, keeping normative text standalone. Schedules A/B remain to be drafted by the adopting charter.) 0.6 (2026-07-12, the schedules drafted — the remainder 0.5 declared: Schedule A (Prohibited Scopes, SA-1…SA-5) and Schedule B (Stakes Classification, SB-1…SB-5) added to the Willow projection as the adopting-charter layer, extend-only, ratifying through Article VIII into FRANK; the numeric machinery 0.5 rejected from the fragment returns here as adoption parameters P-1 (3-in-90-days revocation review with IX.2 quorum) and P-2 (timebound as required declaration, no default). Fragment normative text untouched.) Unratified. Candidate Article XIV; stands alone deliberately.*
