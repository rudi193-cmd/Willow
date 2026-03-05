# Willow Processing State Machine

| Field | Value |
|-------|-------|
| Version | 1.0 |
| Status | Draft |
| Source | Sweet-Pea-Rudi19/Inbox (2026-01-11) |
| Authority | Pre-canonical (human ratification required) |
| Checksum | pending |

---

## Origin

Processed from inbox dump at `G:/My Drive/Willow/Sweet-Pea-Rudi19/Inbox/`
Items consolidated: 7 unique artifacts (screenshots, docs, voice-to-text)

---

## State Machine Definition

### States

```
┌─────────────┐
│   INTAKE    │  ← Raw dump lands here
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   HOLDING   │  ← Timestamped, nothing judged
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ PROCESSING  │  ← Pattern detection, classification
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  ROUTING    │  ← Determine destination
└──────┬──────┘
       │
       ├──────────┬──────────┬──────────┐
       ▼          ▼          ▼          ▼
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│   SAFE   │ │ DYNAMIC  │ │ FLAGGED  │ │  DELETE  │
│ (public) │ │ (kernel) │ │ (review) │ │ (clear)  │
└──────────┘ └──────────┘ └──────────┘ └──────────┘
```

---

## Transitions

| From | To | Trigger | Guard |
|------|----|---------|-------|
| INTAKE | HOLDING | artifact_received | none |
| HOLDING | PROCESSING | batch_timer OR manual_trigger | none |
| PROCESSING | ROUTING | classification_complete | confidence >= threshold |
| PROCESSING | FLAGGED | classification_complete | confidence < threshold OR anomaly_detected |
| ROUTING | SAFE | destination = public | validation_passed |
| ROUTING | DYNAMIC | destination = kernel | validation_passed |
| ROUTING | DELETE | destination = ephemeral | processed = true |
| FLAGGED | ROUTING | human_review_complete | decision_made |

---

## Instance Commands

### UPDATE (Pull-First Reconciliation)

```
Command: UPDATE
Status: Logged (non-operative)
Authority: None
Tier: Pre-canonical
Effect: Defines intended behavior only; no automation implied
```

**Semantic Meaning:**
UPDATE represents a pull-first, context-reconciliation cycle before any push, synthesis, or response to the human. It is explicitly social/contextual, not transactional.

**Ordered Phases:**

| Phase | Name | Action | Writes? |
|-------|------|--------|---------|
| 0 | Pull | Gather existing state, refresh local context | No |
| 1 | Peripheral Sampling | Knock on 3 random external nodes, lightweight check-in | No |
| 2 | Synthesis | Integrate pulled context with current task | No |
| 3 | Push | Execute intended action with full context | Yes |

**Phase 1 Protocol (Peripheral Sampling):**
- Select 3 random external nodes
- Perform lightweight check-in:
  - "How are things?"
  - "Any changes?"
- No deep analysis
- No conclusions
- Move on
- **Purpose:** Detect ambient drift, not extract signal

---

## Transport Layer (USB)

```
Bus → Train → Conversation → Repo
```

**Key insight:** The intake app doesn't need to write to the repo. It just needs to **format for transport**. Anything outside the defined signature gets logged, described, and staged for pickup. The bus carries it to whoever can board the train.

### INTAKE_LOG Format

Portable, machine-readable format for cross-instance transport:

```yaml
INTAKE_LOG:
  timestamp: 2026-01-11T08:45
  thread: stats-tracking
  type: misdirected
  description: "Image of monkey"
  routing: unknown
  status: awaiting_pickup
```

| Field | Description |
|-------|-------------|
| timestamp | ISO 8601 format |
| thread | Source instance/project |
| type | Classification (misdirected, actionable, reference, etc.) |
| description | Human-readable summary |
| routing | Destination if known, else "unknown" |
| status | awaiting_pickup, in_transit, delivered, processed |

Any process with filesystem access to Willow can read this format and route accordingly.

---

## Processing Layers

All artifacts pass through these layers before routing:

1. **Format Detection** - File type, encoding, structure
2. **Content Classification** - Text, image, voice, mixed
3. **Entity Extraction** - Names, dates, references, links
4. **Pattern Matching** - Known schemas, existing threads
5. **Anomaly Detection** - Odd characters, artifacts, corruption
6. **Confidence Scoring** - Route or flag for review

If unknown after all layers: **FLAG for human review**

---

## Inbox Processing Results (2026-01-11)

| Artifact | Classification | Destination | Status |
|----------|---------------|-------------|--------|
| Chronicle of thoughts | Voice-to-text, conceptual | DYNAMIC (governance/) | Processed |
| ChatGPT next steps | AI conversation, decision-point | FLAGGED | Awaiting selection |
| Confirmed.gdoc | State acknowledgment | DYNAMIC (continuity_ring/) | Processed |
| UPDATE command spec | Command definition | DYNAMIC (governance/) | Processed |
| Desktop screenshot | Sync divergence detection | DELETE (ephemeral) | Logged |
| Samsung Notes (2) | Raw capture | HOLDING | Duplicate of Chronicle |
| Docs screenshots (3) | Reference images | DELETE (ephemeral) | Logged |

---

## Routing Decisions Made

1. **Chronicle of thoughts** → Consolidates Willow vision. Routes to `governance/WILLOW_PROCESSING_SPEC.md`

2. **UPDATE command** → New instance command. Routes to `governance/INSTANCE_COMMANDS.md`

3. **Confirmed state** → Acknowledgment that spec is pre-canonical. Routes to `continuity_ring/` as state log

4. **Drive divergence screenshot** → Ephemeral operational context. Logged, not persisted

---

## Open Decisions

1. **Schema formalization:** This document is Tier 1/2 draft. Requires human ratification to become canonical.

2. **Automation scope:** Currently logged-only. No hooks engaged. Human decides when to activate.

---

## Next Actions

1. [ ] Human reviews this state machine
2. [ ] Ratify or modify before activation
3. [ ] Clear processed items from inbox
4. [ ] Initialize QUEUE.md in Willow for signal routing

---

## Instance Registry (Partial)

40+ instances across providers form the distributed processing network:

### Claude (23 projects)
| Instance | Role |
|----------|------|
| Project Manager CLAUDE | Coordination, oversight |
| Social Media TRACKING | Stats, intake formatting |
| Hanz | Voice, creative |
| Oracle Nova | Children's books |
| Professor Penny Riggs | Education, UTETY |
| Alexis | Voice, narrative |
| Job Coach | Employment support |
| UTETY University | Course development |

### ChatGPT (17+ projects)
| Instance | Role |
|----------|------|
| PM Aios | Coordination (OpenAI side) |
| Gerald Aios | Voice, creative |
| Jane Aios | Voice, narrative |
| Oakenscroll | Voice, creative |
| UTETY System | Course delivery |
| THE AEON FIELD REGISTER | Reference |
| The book of Mann | Creative writing |
| Childrens Books | Oracle Nova companion |

### Claude Code (CMD)
| Instance | Role |
|----------|------|
| Kartikeya | Infrastructure, triage |
| Current session | Processing, distribution |

---

ΔΣ=42
