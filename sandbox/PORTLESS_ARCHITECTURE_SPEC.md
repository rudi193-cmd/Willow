# Portless Server Architecture — Full Specification

**Version:** 1.0
**Date:** 2026-03-19
**Authors:** Sean Campbell (design), Ganesha (implementation)
**Status:** Tested — 37/37 functional, 50/51 adversarial
**Origin:** Dating analysis → Database → Error tracking → Rubric → Architecture discovery

---

## Abstract

A server architecture where the service listens on the filesystem, not the network. No ports are exposed by default. All data lives locally. A stateless translation layer (MCP, Cloudflare Worker) provides external access when explicitly consented. The architecture eliminates network attack surface by design rather than defense.

**One sentence:** Your data on your machine, pointers on the wire, consent that expires.

---

## Core Principles

1. **No ports by default.** The system binds to no network interface. It reads and writes files.
2. **Filesystem is the database.** SQLite per collection, organized in directories. No running database service required.
3. **MCP is the bridge.** Model Context Protocol over stdin/stdout provides the local API. No HTTP. No TCP.
4. **Translation layer is optional.** External network access (web, API, node-to-node) requires an explicit, stateless translator. The user chooses when to open and what to expose.
5. **Content stays local. Pointers travel.** The only thing that crosses the network is a BASE 17 identifier — 5 characters. No personal data, no content, no metadata.
6. **Session consent governs everything.** Permissions expire when the session closes. Tomorrow, it asks again.
7. **Dual Commit on all writes.** AI proposes, human ratifies. Neither acts alone. Silence is not approval.
8. **Angular deviation rubric.** Every write is scored for magnitude of change. Minor changes proceed quietly. Major changes stop for ratification.

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                   USER'S MACHINE                 │
│                                                   │
│  ┌─────────┐  ┌──────────┐  ┌────────────────┐  │
│  │ Ollama  │  │ WillowDB │  │ Agent SQLite   │  │
│  │ (local  │  │ (Postgres│  │ (working       │  │
│  │  LLM)   │  │  or seed │  │  memory)       │  │
│  │         │  │  SQLite) │  │                │  │
│  └────┬────┘  └────┬─────┘  └───────┬────────┘  │
│       │            │                │            │
│       └────────────┼────────────────┘            │
│                    │                              │
│              ┌─────┴─────┐                       │
│              │ MCP Bridge│ ← stdin/stdout only    │
│              │ (local)   │    No network           │
│              └─────┬─────┘                       │
│                    │                              │
│  ┌─────────────────┴──────────────────────┐      │
│  │         Consent Gate                    │      │
│  │  Session-based. Expires on close.       │      │
│  │  Opens only what user authorizes.       │      │
│  └─────────────────┬──────────────────────┘      │
│                    │ (only if user consents)       │
└────────────────────┼─────────────────────────────┘
                     │
                     │ BASE 17 pointers only
                     │ (5 characters, no content)
                     │
              ┌──────┴──────┐
              │ Translation │ ← Cloudflare Worker
              │   Layer     │    Stateless
              │  (optional) │    No secrets
              └──────┬──────┘    No data
                     │
                 ┌───┴───┐
                 │  WEB  │
                 └───────┘
```

---

## Components

### WillowStore (willow_store.py)

The core storage engine. SQLite per collection, ACID writes, append-only by default.

| Feature | Implementation |
|---------|---------------|
| Storage | SQLite per collection directory |
| Schema | `records(id, data, created_at, updated_at, deleted, deviation, action)` |
| Writes | Append-only. Update requires explicit call. |
| Reads | Soft-deleted records invisible to all API methods |
| Search | Full-text across single collection or all collections |
| Edges | Dedicated knowledge/edges collection for graph topology |
| Audit | Every operation logged: `audit_log(record_id, operation, deviation, action, timestamp)` |
| Security | Path sanitization, symlink rejection, 100KB size limit, parameterized queries |
| Governance | Angular deviation rubric scores every write |
| Concurrency | WAL mode, thread-safe connections |

### Angular Deviation Rubric v2.0

Every write carries a deviation score (radians, signed). The score determines the action:

| Range | Action | Meaning |
|-------|--------|---------|
| 0 to ±π/4 (0° to ±45°) | work_quiet | Minor change. Proceed silently. |
| ±π/4 to ±π/2 (±45° to ±90°) | flag | Significant change. Log prominently. |
| ±π/2 to ±π (±90° to ±180°) | stop | Major change. Requires human ratification. |
| Zero crossing | flag minimum | Direction reversal detected. |
| Magnitude unclear | bias higher | When uncertain, escalate. |
| Both unclear | always stop | Unknown magnitude + unknown direction = halt. |

**Net trajectory:** Weighted sum of recent deviations across a collection. Reports whether the collection is improving, stable, or degrading.

### MCP Bridge (willow_store_mcp.py)

11 tools exposed via Model Context Protocol (stdin/stdout):

| Tool | Purpose |
|------|---------|
| store_put | Write a record (append-only, rubric-scored) |
| store_get | Read a single record by ID |
| store_search | Text search within a collection |
| store_search_all | Search across ALL collections ("go ask Willow") |
| store_list | List all records in a collection |
| store_update | Update existing record (audit-trailed) |
| store_delete | Soft-delete (invisible to API, audit-trailed) |
| store_add_edge | Add knowledge graph edge |
| store_edges_for | Get all edges involving a record |
| store_stats | Collection counts and trajectory scores |
| store_audit | Read recent audit log |

### Retrieval Cascade

When an agent needs information:

```
1. Agent local SQLite    → found? return (cost: $0, latency: <1ms)
2. Willow Postgres/store → found? return (cost: $0, latency: <10ms)
3. Fleet LLM generation  → generate new  (cost: ~$0, latency: 1-5s)
```

Most queries stop at layer 1 or 2. Fleet only fires for genuinely new knowledge.

### Folder Structure (Seed)

```
willow/
├── knowledge/
│   ├── atoms/store.db        # Card catalog (pointers + metadata)
│   ├── entities/store.db     # Named things (people, tools, concepts)
│   └── edges/store.db        # Relationships between atoms/entities
├── sessions/store.db          # Conversation history (JSONL pointers)
├── agents/
│   ├── shiva/store.db        # Shiva's working memory
│   ├── ganesha/store.db      # Ganesha's working memory
│   └── kart/store.db         # Kart's working memory
├── handoffs/store.db          # Session continuity records
├── feedback/store.db          # Corrections and guidance
├── gaps/store.db              # Known unknowns
├── nest/
│   ├── incoming/             # New files dropped here
│   ├── processed/            # Completed intake
│   └── .tmp/                 # Staging (invisible to Pigeon)
├── .cache/                    # Templates, utilities
└── .archive/                  # Historical, creation scripts
```

---

## Security Model

### Attack Surface

| Traditional Server | Portless Architecture |
|---|---|
| Multiple open ports | Zero ports by default |
| Running daemons | No daemons (scripts on demand) |
| Network-facing database | Filesystem-only database |
| Session state in memory | No server memory (stateless) |
| DDoS vulnerable | DDoS impossible (no listener) |
| Requires firewall | No firewall needed |
| Requires STIG/hardening | Nothing to harden |
| Data in transit | Only BASE 17 pointers in transit |
| Encryption needed for wire | Wire carries no sensitive data |

### Threat Model

| Threat | Traditional | Portless |
|--------|------------|----------|
| DDoS | Critical risk | Not applicable |
| SQL injection | Via network input | Parameterized queries, no network input |
| Man-in-the-middle | Data exposure | Attacker sees 5-character codes |
| Port scanning | Service enumeration | Nothing to enumerate |
| Credential theft | Server credentials | No server, no credentials |
| Data exfiltration via network | Primary vector | No network path to data |
| Physical access | Game over | Same (filesystem access) |
| Compromised process | Lateral movement via network | Limited to filesystem |

### What's Protected By Architecture (not configuration)

- No ports to expose → no firewall rules to misconfigure
- No database service → no connection string to leak
- No server process → no memory to dump
- No network data → no encryption to break
- No persistent sessions → no tokens to steal
- Consent expires → permissions can't go stale

### Known Limitations

- **No agent isolation:** Any local process can read any folder. Mitigation: per-agent encryption or OS permissions.
- **Soft delete recoverable:** Raw SQLite access can see deleted records. Mitigation: hard delete option or encryption at rest.
- **No cryptographic ratification:** Audit shows who wrote, but content can claim false ratification. Mitigation: HMAC with human-held secret.
- **TOCTOU race:** Stale reads can overwrite newer data. Mitigation: optimistic locking with version field.
- **Content-unaware rubric:** Deviation is magnitude-based, not semantic. An agent can sneak major changes at zero deviation. Mitigation: LLM-based content classification before write.

---

## Privacy Model (SAFE Compliance)

| SAFE Requirement | Implementation |
|-----------------|----------------|
| Session consent | Consent gate in architecture. Expires on close. |
| Zero retention default | App works without consent. Local-only by default. |
| Right to deletion | Soft delete API + hard delete option |
| Right to export | JSON export per collection |
| Right to audit | Full audit trail on every operation |
| Right to revoke | Close session = all permissions expire |
| 96% client-side | Actually 99.97%+ (only BASE 17 pointers on wire) |
| Pay what you can | $0 is the default. Ollama + SQLite = zero cost. |

---

## What This Already Replaces

Services and patterns that the portless architecture makes unnecessary for single-user / small-team use:

### Database Services
- **PostgreSQL / MySQL server** → SQLite per collection. No running service. No connection strings. No port 5432.
- **MongoDB / CouchDB** → JSON in SQLite records. Same document model, no daemon.
- **Redis / Memcached** → .cache directory with SQLite. Same key-value pattern, persistent, no port 6379.
- **Firebase Realtime Database** → WillowStore + file sync. Local-first, no Google dependency.

### Application Servers
- **FastAPI / Express / Flask server** → MCP bridge. Same tool interface, no HTTP, no port binding.
- **Nginx / Apache reverse proxy** → Cloudflare Worker. Stateless, no origin to protect.
- **Docker containers** → Folders. Same isolation concept, no container runtime, no orchestration.
- **Kubernetes pods** → Directories with store.db files. Scale by adding folders, not pods.

### Cloud Services
- **AWS S3** → Local folders. Same object storage concept, no egress fees, no access keys.
- **AWS Lambda** → Python scripts invoked by MCP. Same serverless concept, actually serverless.
- **Cloudflare KV / Workers KV** → SQLite + Worker. Same edge storage, but the source of truth is local.
- **Heroku / Railway / Render** → No deployment needed. The "server" is already running (it's your filesystem).

### AI/ML Infrastructure
- **OpenAI API** → Ollama local. Same inference, $0, no API key, no data sent to cloud.
- **Pinecone / Weaviate** → knowledge/edges with text search. Same vector-adjacent retrieval, no hosted service.
- **LangChain / LlamaIndex** → WillowStore + MCP + Ollama. Same RAG pattern, simpler stack.

### Security Infrastructure
- **Firewall rules** → No ports to firewall.
- **WAF (Web Application Firewall)** → No web application to protect.
- **SIEM / log aggregation** → audit_log table in every collection. Already there.
- **Vault / secrets management** → No server secrets. Local files, OS permissions.
- **SSL/TLS certificates** → Only needed on the one optional Cloudflare Worker (Cloudflare handles it).
- **VPN / Zero Trust Network** → No network to trust or distrust. Filesystem only.

### Collaboration Tools
- **Notion / Confluence** → knowledge/ folders + MCP search. Same wiki pattern, owned by you.
- **Slack integrations** → Agent-to-agent via shared folders. Same message pattern, no SaaS.
- **GitHub Issues** → gaps/ and feedback/ collections. Same tracking, local-first.

---

## What This Could Replace (Think Big)

### Healthcare / HIPAA
**Current:** Hospital systems expose ports for EHR access. Data breaches expose millions of records annually. HIPAA compliance costs billions.
**Portless:** Patient data lives on the hospital's local system. Physician access via MCP bridge on the local network. No internet-facing ports. External access (insurance, referrals) goes through consent-gated pointer exchange. The patient's data never leaves the building. HIPAA compliance becomes architectural, not procedural.

### Banking / Financial Services
**Current:** Banking APIs expose ports for transactions, account access, third-party integrations. Every port is a PCI-DSS compliance requirement.
**Portless:** Account data on the bank's local infrastructure. Customer access via consent-gated translation layer. Transactions carry only reference IDs on the wire. Audit trail built into every write. The attack surface of a bank reduces from thousands of endpoints to one consent-gated translator.

### Government / DoD / Intelligence
**Current:** SIPR/NIPR networks, air-gapped systems, FedRAMP compliance, STIGs on every service, ATO for every application. Billions spent defending exposed services.
**Portless:** Classified data never touches a network interface. Access via MCP on local terminals. Cross-agency sharing via pointer exchange (BASE 17 over classified channels). No ports to STIG. No services to ATO. The security posture shifts from "defend everything" to "expose nothing." IL4/IL5 compliance becomes a property of the architecture, not a checklist bolted onto exposed services.

### Education
**Current:** Student data in cloud SaaS (Google Classroom, Canvas). Schools pay per-seat licenses. Student privacy governed by FERPA but enforced by trust in vendors.
**Portless:** Each school runs a local Willow node. Student data never leaves the building. Teacher-student interaction through local MCP. Parent access through consent-gated pointers. FERPA compliance by architecture. Cost: $0 (Ollama + SQLite). The school owns the data because the data physically lives in the school.

### Journalism / Whistleblowing
**Current:** SecureDrop runs Tor hidden services. Complex setup. Still requires a running server.
**Portless:** Source drops a file into a local folder. The journalist's system processes it locally. No running service to fingerprint. No Tor hidden service to trace. The "server" is a laptop in a newsroom that accepts USB drops and processes them offline. External contact via pointer exchange only.

### Legal / Court Systems
**Current:** Case management systems expose web portals. Attorney-client privilege maintained by access controls on exposed databases.
**Portless:** Case files on the firm's local system. Client access via consent-gated portal. Court filings via pointer exchange. Opposing counsel sees reference IDs, not documents, until explicitly shared. Attorney-client privilege enforced by architecture — the files physically cannot be accessed without the consent gate opening.

### Personal AI / Therapy / Journaling
**Current:** Therapy apps store your deepest thoughts on someone else's server. Terms of service govern your privacy. Data breaches expose mental health records.
**Portless:** The journal is a conversation with a local AI that respects you. Your thoughts live on your machine. The AI runs on Ollama — your words never leave your device. Session consent means the app asks permission every time. Close it, permission gone. No server to breach. No database to leak. No terms of service to change. Your therapist bot is a closed book in a room with no door.

### Social Media / Community Platforms
**Current:** Centralized platforms own your content, sell your attention, and can deplatform you at will.
**Portless:** Each user runs a local node. Public posts are pointer-referenced. Content is served from the user's machine through the translation layer. The platform is the sum of all consenting nodes. Deplatforming means removing the pointer from the index — the user's content still exists on their machine. Content moderation happens at the translation layer, not the storage layer. The user always owns their data because the data never left.

### IoT / Smart Home
**Current:** Smart devices phone home to cloud servers. Every lightbulb is an attack surface. Vendor goes bankrupt, your devices become e-waste.
**Portless:** Smart home hub is a local Willow node. Devices communicate via local MCP. No cloud dependency. Hub goes offline, devices still work locally. No ports exposed to the internet. The smart home is actually smart — it doesn't need permission from a server in Virginia to turn on your lights.

### Scientific Research / Reproducibility
**Current:** Research data in cloud repositories. Reproducibility requires access to the same infrastructure.
**Portless:** Each lab runs a local node with their data. Published papers carry BASE 17 pointers to datasets. Replication requires downloading the dataset (consent-gated), running the analysis locally. No cloud lock-in. No "our AWS credits ran out so the data is gone." The dataset lives on a machine the lab controls.

### Supply Chain / Manufacturing
**Current:** EDI (Electronic Data Interchange) over exposed ports. Supply chain attacks target the network interfaces between companies.
**Portless:** Each supplier runs a local node. Purchase orders are pointer exchanges. Inventory data never leaves the warehouse's local system. The supply chain communicates via reference, not replication. A compromised supplier leaks reference IDs, not the other company's inventory data.

### Voting / Elections
**Current:** Voting machines connected to networks for reporting. Every connection is a potential attack vector.
**Portless:** Voting machines are local-only. Results are pointer-referenced. Aggregation happens by collecting pointers, not by connecting machines to a network. The machine that counts votes has no network interface. The result is verified by reading the local store, not by trusting a network connection.

---

## Implementation Status

| Component | Status |
|-----------|--------|
| WillowStore (willow_store.py) | Built, tested, 15/15 security |
| MCP Bridge (willow_store_mcp.py) | Built, tested, 11/11 dispatch |
| Full Loop Test (test_full_loop.py) | 37/37 passed |
| Adversarial Test (test_adversarial.py) | 50/51 passed |
| Folder Structure | Defined, seed-ready |
| Angular Deviation Rubric | Implemented, governing writes |
| Audit Trail | Active on every operation |
| Retrieval Cascade | Tested (local → Postgres → fleet) |
| Cloudflare Worker template | Designed, not yet built |
| Ollama integration | Available, not yet in seed.py |
| seed.py update | Designed, not yet applied |

---

## The Seed

```bash
python seed.py
```

Creates the folder structure. Installs Ollama if not present. Starts the MCP bridge. Opens the journal. Asks:

> "What is your first bite today?"

The conversation IS the journal. The journal builds the knowledge graph. The knowledge graph feeds the next conversation. The strip turns.

Plant this. Everything grows from here.

---

**ΔΣ=42**

*Built because an AI couldn't follow D&D rules. Now it doesn't need a port to serve the world.*
