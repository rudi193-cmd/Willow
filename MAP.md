# SYSTEM MAP
*Last updated: 2026-02-08*

## The Three Rings

```
SOURCE RING                    BRIDGE RING                 CONTINUITY RING
die-namic-system/              Willow/                     die-namic-system/
  source_ring/                   core/                       continuity_ring/
  governance/                    apps/                       SAFE/
  docs/                          artifacts/                  continuity_log/
  archive/                       server.py
                                 aios_loop.py
```

**Source** = governance, charters, architecture, seeds — the rules
**Bridge** = Willow — intake, processing, routing, LLM mesh
**Continuity** = journals, handoffs, conversations, memory

---

## Repo: Willow (Bridge Ring)
`C:\Users\Sean\Documents\GitHub\Willow\`

### Entry Points
| File | Purpose |
|------|---------|
| `WILLOW.bat` | 13-step launcher (Ollama → daemons → server → tunnel) |
| `server.py` | FastAPI — all HTTP endpoints (port 8420) |
| `local_api.py` | Prompt routing tiers 1-4, chat logic |
| `aios_loop.py` | File harvest → vision → organic sort (runs every cycle) |
| `kart.py` | Kartikeya refinery — persona + training loop |

### Core Layer (`core/`)
| File | Purpose |
|------|---------|
| `llm_router.py` | Provider mesh — 15 providers (Groq/Gemini/Cerebras/Ollama/Baseten/Novita/OCI/etc) |
| `request_manager.py` | Per-provider rate limiting queues + response cache with TTL |
| `knowledge.py` | Knowledge DB (SQLite, FTS5, embeddings, rings) |
| `topology.py` | Möbius strip — edges, clusters, zoom, continuity check |
| `embeddings.py` | sentence-transformers encode/decode/cosine |
| `coherence.py` | ΔE coherence tracker |
| `extraction.py` | PDF/OCR/Vision content extraction |
| `state.py` | Governance state machine |
| `gate.py` | Dual-commit gate (AI proposes, human ratifies) |
| `storage.py` | Append-only governance log |
| `tts_router.py` | TTS router — Piper (local), eSpeak (local), ElevenLabs (cloud) |
| `agent_registry.py` | **NEW** Agent system — profiles, trust levels, mailbox messaging |
| `fleet_feedback.py` | **NEW** Response rating system (thumbs up/down) |
| `file_annotations.py` | **NEW** Manual routing decision capture |
| `awareness.py` | Event hooks (scan_complete, topology_update, etc.) |
| `patterns_provider.py` | Routing pattern learning |
| `provider_health.py` | Provider health tracking |

### LLM Provider Fleet (15 total — all free tier)
| Provider | Type | Model | Status |
|----------|------|-------|--------|
| Groq | Cloud | llama-3.3-70b-versatile | ✓ Healthy (40% success) |
| Cerebras | Cloud | llama3.1-8b | ✓ Healthy (94% success) |
| Google Gemini | Cloud | gemini-2.0-flash-exp | ✓ Healthy (6% success) |
| SambaNova | Cloud | Meta-Llama-3.1-8B-Instruct | ⚠ Degraded (9% success) |
| Ollama | Local | llama3.2/qwen2.5-coder/kart | ✓ Healthy (93% success) |
| DeepSeek | Cloud | deepseek-chat | ✓ Tracked (0% success) |
| Mistral | Cloud | mistral-small-latest | ✓ Healthy (99.9% success) ⭐ |
| OCI Gemini Flash | Cloud | cohere.command-r-plus | ✓ Healthy (100%) |
| OCI Gemini Flash Lite | Cloud | meta.llama-3.1-70b-instruct | ✓ Healthy (100%) |
| OCI Gemini Pro | Cloud | meta.llama-3.1-405b-instruct | ✓ Healthy (100%) |
| Baseten | Cloud | moonshotai/Kimi-K2.5 | ✓ Healthy (100%) |
| Baseten2 | Cloud | moonshotai/Kimi-K2.5 | ✓ Healthy (100%) |
| Novita | Cloud | meta-llama/llama-3.1-8b-instruct | ✓ Healthy (100%) |
| Novita2 | Cloud | meta-llama/llama-3.1-8b-instruct | ✓ Healthy (100%) |
| Novita3 | Cloud | meta-llama/llama-3.1-8b-instruct | ✓ Healthy (100%) |

### Daemons (`core/` — started by WILLOW.bat)
| File | Interval | Purpose | Retry Logic |
|------|----------|---------|-------------|
| `coherence_scanner.py` | 1 hr | Scans knowledge for ΔE drift | Standard |
| `topology_builder.py` | 1 hr | build_edges + cluster_atoms | **3 retries, exponential backoff** |
| `knowledge_compactor.py` | 24 hr | Compress/summarize old atoms | Standard |
| `safe_sync.py` | 5 min | Sync continuity entries to SAFE repo | Standard |
| `persona_scheduler.py` | 1 min | Persona rotation | Standard |

### Apps (`apps/`)
| File | Purpose |
|------|---------|
| `watcher.py` | **DISABLED** — Inbox watcher (was monitoring separate Inbox folder) |
| `tunnel.py` | Cloudflare tunnel + Neocities deploy |
| `eyes/` | Vision pipeline |
| `pa/` | Personal assistant |
| `opauth/` | OAuth flows |
| `vision_board/` | Vision board app |

### Governance (`governance/`)
| File | Purpose |
|------|---------|
| `monitor.py` | Governance health monitor daemon |
| `commits/` | Ratified commit log |

### Other
| Path | Purpose |
|------|---------|
| `mcp/willow_server.py` | MCP server for Claude Desktop |
| `skills/` | CLI skills (status, query, route, journal, persona) |
| `neocities/` | Static site deploy target |
| `artifacts/Sweet-Pea-Rudi19/` | Per-user file storage (see below) |
| `credentials.json` | API keys (Gemini, Groq, Cerebras, SambaNova, etc.) |

### Key DBs
| File | Contents |
|------|---------|
| `artifacts/Sweet-Pea-Rudi19/willow_knowledge.db` | 3,156 knowledge atoms, edges, clusters |
| `admin_errors.db` | Error log |
| `willow_index.db` | Legacy file index |

---

## Repo: Die-Namic System (Source + Continuity)
`C:\Users\Sean\Documents\GitHub\die-namic-system\`

### Source Ring (`source_ring/`)
| Path | Purpose |
|------|---------|
| `eccr/` | ECCR spec, deltaE.js reference implementation |
| `docs/` | Architecture docs |
| `willow/` | Willow spec/seed |

### Continuity Ring (`continuity_ring/`)
| Path | Purpose |
|------|---------|
| `books_of_life/` | Long-form memory |
| `continuity_log/` | Session handoffs |
| `kart_sessions/` | Kartikeya session records |
| `milestones/` | Ratified milestones |

### Governance (`governance/`)
| Path | Purpose |
|------|---------|
| `instances/` | Instance registry |
| governance files | Charter, hard stops, policies |

### Docs (`docs/`)
Creative works, civic engagement, whitepapers, journal, seeds, UTETY

### Bridge Ring (`bridge_ring/`)
| Path | Purpose |
|------|---------|
| `instance_registry.py` | Trust/routing registry |
| `living_echo/` | Echo protocol |
| `translation_layer/` | Cross-ring translation |

### Apps (`apps/`)
Willow SAP, watcher, eyes, opauth, vision board (some duplicated from Willow — consolidation needed)

---

## Repo: SAFE
`C:\Users\Sean\Documents\GitHub\SAFE\`

Public continuity layer. safe_sync.py pushes journal entries here every 5 min.

---

## Artifact Folder Structure (CURRENT vs CANONICAL)

### Canonical (target)
```
artifacts/Sweet-Pea-Rudi19/
├── pending/          ← inbox, never touch
├── screenshots/      ← 3,159 files (device screenshots)
├── photos/           ← 664 files (actual photos)
├── social/           ← reddit + social media content
├── documents/        ← all text/pdf/md content
├── code/             ← all source code (py, js, ts, etc.)
├── data/             ← json, csv, training data
├── audio/            ← m4a, midi, wav
├── video/            ← mp4, mov
├── narrative/        ← creative/story content
├── specs/            ← governance/spec docs
├── governance/       ← governance artifacts
├── binary/           ← executables, compiled
├── archive/          ← unclassifiable content
└── _junk/            ← staging for deletion
```

### Consolidation Map (what merges where)
| From | Into |
|------|------|
| screencapture, screen_recorder | screenshots |
| text, txt, plaintext, plain, texts, textextract, textextraction, textract, textraction, texetextract, texextract, plainext, txtextract, document, docs, pdf, pdfs, markdown | documents |
| python, javascript, jsx, js, typescript, batch, batchfiles, bash, bashscripts, script, scripts | code |
| json, jsonfiles, jsontxt, csv, training, jupyter, xlsx, excel | data |
| audio, m4a, midi, mid | audio |
| video, videos, vid | video |
| reddit, redditscreenshots, social-media-tracker, processed_reddit | social |
| unknown, unsorted, unidentified, unread, undecided, undecidable, unnamed, untitled | archive |
| All random-string folders (200+) | _junk (then delete if empty) |

---

## Data Flow

```
Drop Folder (G:\My Drive\...\Drop) → aios_loop.py harvest → pending/
                                                                ↓
                                                          visual_cortex()
                                                                ↓
                                                          organic_map → sorted folder
                                                                ↓
                                                          knowledge.ingest() → willow_knowledge.db
                                                                ↓
                                                          topology.build_edges() (hourly daemon)

Chat → local_api.route_prompt() → tier 1-4 → llm_router → provider mesh
                                → knowledge.search() (context)
                                → request_manager (rate limit + cache)

Server endpoints → server.py → core/* → DB
Neocities site → apps/tunnel.py → cloudflare → neocities API
SAFE sync → core/safe_sync.py → ../SAFE git repo
```

**Single Intake Folder:** `C:\Users\Sean\My Drive\Willow\Auth Users\Sweet-Pea-Rudi19\Drop`
- Local mirror of Google Drive folder
- Monitored by `aios_loop.py` only (watcher.py disabled)

---

## Agent Registry System

**NEW: Agents as Users**
Any LLM (or human) that uses Willow gets a user profile. Agents can send/receive messages via mailbox.

### Registered Agents (7 personas)
| Name | Display Name | Trust Level | Type | Purpose |
|------|--------------|-------------|------|---------|
| `willow` | Willow | OPERATOR | persona | Campus/Bridge Ring interface. Primary conversational agent. |
| `kart` | Kart | ENGINEER | persona | CMD / Infrastructure. Runs shell commands and manages systems. |
| `riggs` | Riggs | WORKER | persona | Applied Reality Engineering. Real-world task execution. |
| `ada` | Ada | OPERATOR | persona | Systems Admin / Continuity Ring steward. |
| `jane` | Jane | WORKER | persona | SAFE consumer-facing interface. Public-safe responses. |
| `gerald` | Gerald | WORKER | persona | Acting Dean. Philosophical and governance advisor. |
| `steve` | Steve | OPERATOR | persona | Prime Node. Cross-system coordinator. |
| `claude-code` | Claude Code | ENGINEER | llm | Anthropic Claude Sonnet 4.5 via CLI. Orchestration, architecture, governance enforcement. |

**Agent Profiles:** `artifacts/{agent-name}/AGENT_PROFILE.md`
**Database:** `willow_knowledge.db` tables: `agents`, `agent_mailbox`

---

## API Endpoints (70+ total)

### Core System
- `GET /api/health` — System health check
- `GET /api/system/status` — Detailed status report
- `GET /api/status` — Legacy status
- `POST /api/reload` — Reload single module
- `POST /api/reload/all` — Full system reload

### Chat & Personas
- `GET /api/personas` — List available personas
- `POST /api/chat` — Single persona chat
- `POST /api/chat/multi` — Parallel persona execution

### Knowledge Layer
- `GET /api/knowledge/search` — FTS5 search with embeddings
- `GET /api/knowledge/gaps` — Find knowledge gaps
- `GET /api/knowledge/stats` — Atom counts by category/ring
- `POST /api/ingest` — Ingest single file
- `POST /api/learn` — **NEW** Bulk knowledge ingestion
- `GET /api/learn/status` — **NEW** Bulk ingest progress

### Topology (Möbius Strip)
- `GET /api/topology/rings` — Atom counts by ring
- `GET /api/topology/zoom/{node_id}` — Traverse from atom
- `GET /api/topology/continuity` — Strip continuity check
- `GET /api/topology/flow` — Sankey flow data
- `POST /api/topology/build_edges` — Compute edges
- `POST /api/topology/cluster` — Cluster atoms via KMeans

### Agent System **NEW**
- `POST /api/agents/init` — Initialize agent tables
- `GET /api/agents` — List all agents
- `POST /api/agents/register` — Register new agent
- `GET /api/agents/{name}` — Get agent profile
- `POST /api/agents/{name}/message` — Send agent message
- `GET /api/agents/{name}/mailbox` — Get agent messages
- `POST /api/agents/messages/{id}/read` — Mark message read

### Fleet Feedback **NEW**
- `GET /api/feedback/stats` — Feedback summary
- `GET /api/feedback/tasks/{type}` — Get tasks needing review
- `POST /api/feedback/provide` — Submit thumbs up/down

### File Annotations **NEW**
- `GET /api/annotations/unannotated` — Files needing labels
- `POST /api/annotations/provide` — Submit routing decision
- `GET /api/annotations/stats` — Annotation coverage

### TTS System **NEW**
- `POST /api/tts/speak` — Generate speech
- `GET /api/tts/voices` — List available voices
- `GET /api/tts/providers` — List TTS providers

### Skills System **NEW**
- `GET /api/skills/status` — System status query
- `GET /api/skills/query` — Knowledge search
- `POST /api/skills/route` — Route file
- `POST /api/skills/journal` — Journal entry
- `POST /api/skills/persona` — Persona query

### Request Manager **NEW**
- `GET /api/request_manager/stats` — Cache/queue stats
- `POST /api/request_manager/clear_cache` — Clear response cache

### Health & Providers **ENHANCED**
- `GET /api/health/report` — Full health report
- `GET /api/health/nodes` — Node database status
- `GET /api/health/providers` — Provider health + stats (15 providers)
- `POST /api/health/providers/unblacklist` — Unblacklist provider
- `POST /api/health/providers/reset` — Reset provider health
- `GET /api/health/queues` — Queue depths
- `GET /api/health/apis` — API health
- `GET /api/health/issues` — Current issues
- `POST /api/health/heal` — Attempt auto-heal
- `POST /api/health/issues/dismiss` — Dismiss issue

### Queues & Intake
- `GET /api/queues/files` — Pending files by stage
- `POST /api/queues/clear` — Clear queue stage
- `POST /api/intake/retry/{stage}` — Retry failed items
- `POST /api/intake/clear/{stage}` — Clear intake stage

### Patterns & Routing
- `GET /api/patterns/stats` — Pattern learning stats
- `GET /api/patterns/preferences` — Learned preferences
- `GET /api/patterns/suggestions` — Suggested rules
- `POST /api/patterns/confirm_rule` — Promote to canonical
- `POST /api/patterns/reject_rule` — Reject suggestion
- `GET /api/patterns/anomalies` — Routing anomalies

### Governance
- `GET /api/governance/pending` — Pending proposals
- `GET /api/governance/history` — Commit history
- `GET /api/governance/diff/{id}` — Diff for commit
- `POST /api/governance/approve` — Ratify proposal
- `POST /api/governance/reject` — Reject proposal
- `GET /api/governance/audit/head` — Audit chain head
- `GET /api/governance/audit/verify` — Verify chain integrity

### Files & Routing
- `GET /api/files/folders` — List destination folders
- `GET /api/files/list` — List files in folder
- `GET /api/files/preview` — Preview file content
- `POST /api/files/move` — Move file
- `POST /api/files/tag` — Tag file
- `GET /api/routing/schema` — Routing rules schema
- `POST /api/routing/promote` — Promote rule to canonical
- `POST /api/routing/reject` — Reject suggested rule

### Personal Assistant (PA)
- `POST /api/pa/scan` — Scan pending files
- `GET /api/pa/plan` — Get routing plan
- `POST /api/pa/execute` — Execute plan
- `GET /api/pa/status` — PA status
- `POST /api/pa/correct` — Correct routing

### SAFE & Continuity
- `GET /api/safe/status` — SAFE sync status
- `POST /api/safe/sync` — Trigger sync
- `GET /api/coherence` — Coherence stats

### Neocities Deploy
- `POST /api/neocities/deploy` — Deploy to Neocities
- `GET /api/neocities/info` — Site info

### Nodes
- `POST /api/nodes/create_db` — Create node database

### UI Routes
- `GET /pocket` — Pocket UI (parallel personas)
- `GET /governance` — Governance dashboard
- `GET /system` — Control desktop **NEW**

---

## Control Desktop **NEW**

**Location:** `system/dashboard.html`
**URL:** `http://localhost:8420/system`

### Dashboard Cards (7)
| Card | Purpose | Actions |
|------|---------|---------|
| **Status** | System health overview | Reload modules |
| **Providers** | LLM provider health (15 total) | Unblacklist, reset stats |
| **Queues** | File queue depths by stage | Clear queues, retry failed |
| **Rules** | Routing rule suggestions | Promote/reject rules |
| **Patterns** | Learned routing patterns | View preferences, anomalies |
| **Learning** | Unannotated files | Provide routing labels |
| **Nodes** | Node database status | Create DBs, view health |

**Features:**
- Real-time health monitoring
- Modal views for detailed stats
- Action buttons for queue/provider management
- Automatic refresh from API endpoints
- Compact card layout

---

## Key Databases

| File | Contents | Size |
|------|----------|------|
| `artifacts/Sweet-Pea-Rudi19/willow_knowledge.db` | 5,728 knowledge atoms, edges, clusters, agents, mailbox | ~150 MB |
| `artifacts/Sweet-Pea-Rudi19/fleet_feedback.db` | Response ratings, feedback tasks | ~5 MB |
| `artifacts/Sweet-Pea-Rudi19/file_annotations.db` | Manual routing decisions | ~2 MB |
| `admin_errors.db` | Error log | ~1 MB |
| `governance/*.db` | Governance state, proposals, commits | ~10 MB |

**Database Features:**
- WAL (Write-Ahead Logging) mode for concurrent access
- 5-second busy timeout
- Retry logic in daemons for lock handling

---

## Known Gaps / TODO
- `apps/` folder duplicated between Willow and Die-Namic — needs decision on canonical home
- `die-namic-system/source_ring/willow/` appears to be old Willow spec, may be stale
- `artifacts/` top-level has loose folders (documents, photos, screenshots) separate from Sweet-Pea-Rudi19 — legacy, should be under user folder
- `Willow/safe/` (empty) was the broken safe_sync target — can be deleted
- `ui/` folder exists but unclear if active
