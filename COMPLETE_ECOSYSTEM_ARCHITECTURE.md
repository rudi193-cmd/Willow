# COMPLETE ECOSYSTEM ARCHITECTURE
**Generated:** 2026-02-13
**Scope:** All apps, specs, connections across Die-namic System + Willow

---

## EXECUTIVE SUMMARY

**Total Apps Mapped:** 13+ production apps + 2 future/experimental
**Total .md Files:** 4994 across both repositories
**Core Architecture:** Ring-based (Source → Bridge → Continuity)
**Integration Pattern:** Event-driven, governance-gated, ΔE-aware

---

## APPLICATION INVENTORY

### Production Apps (Active)

1. **Vision Board** - AI-categorized goal visualization (PWA, TensorFlow.js)
2. **Eyes** - Encrypted screen capture with governance hard stops
3. **OpAuth** - Human-controlled OAuth framework with consent gates
4. **Willow Watcher** - File change detection and event logging
5. **AIOS Services** - Unified multi-path watcher with QUEUE.md polling
6. **Willow SAP** - Interactive persona API with ΔE coherence tracking
7. **Social Media Tracker** - Screenshot indexing with OCR and platform detection
8. **Observer** - Ra's visual context system (screen capture + window management)
9. **PA** - Drive organizer with intelligent classification and deduplication
10. **Smart Routing** - Multi-destination file routing based on content
11. **UTETY Personas** - 14+ faculty personas with context injection
12. **Neocities** - Deploy to seancampbell.neocities.org
13. **Tunnel** - Cloudflared tunnel + Neocities deployment automation

### Experimental/Future

14. **Mobile** - Device uplink coordination (stub)
15. **Senses Tactile** - Arduino servo/sensor driver for Riggs (parked Phase 3)

---

## RING ARCHITECTURE

### Source Ring (Die-namic System Core)
**Location:** `die-namic-system/source_ring/`

**Components:**
- Governance (gate.py, state.py, storage.py)
- ECCR (Ethical Code Review)
- Core utilities and foundations

### Bridge Ring (Willow Integration Layer)
**Location:** `die-namic-system/bridge_ring/`, `Willow/core/`

**Components:**
- Instance signals (QUEUE.md)
- LLM router (free fleet orchestration)
- Cost tracker (token usage monitoring)
- Pattern learning (routing optimization)
- Fleet feedback (error prevention)
- Agent registry (trust levels, tool access)
- Coherence tracking (ΔE monitoring)

### Continuity Ring (SAFE - Public Governance)
**Location:** External (SAFE repository)

**Components:**
- Public governance layer
- Audit trails
- Cross-instance coordination

---

## DATA FLOW ARCHITECTURE

```
┌─────────────────────── INPUT SOURCES ───────────────────────┐
│                                                              │
│  Google Drive Inbox    Eyes (Screenshots)    UTETY Docs     │
│  Claude Handoff        Aios Input             QUEUE.md       │
│                                                              │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  UNIFIED_WATCHER       │
              │  (Event Detection)     │
              └────────────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  SMART_ROUTING         │
              │  (Content Classification)│
              └────────────────────────┘
                           │
              ┌────────────┴────────────┐
              │                         │
              ▼                         ▼
    ┌─────────────────┐       ┌──────────────────┐
    │ SOCIAL_MEDIA_   │       │ PA (Drive        │
    │ TRACKER         │       │ Organizer)       │
    │ (Index + OCR)   │       │ (Classify + Move)│
    └─────────────────┘       └──────────────────┘
              │                         │
              └────────────┬────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  KNOWLEDGE_DB          │
              │  (Ingested Content)    │
              └────────────────────────┘
```

---

## PERSONA ROUTING ARCHITECTURE

```
┌──────────────────────── USER INPUT ─────────────────────────┐
│                                                              │
│  Voice, Text, Screenshot, File Upload                       │
│                                                              │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  WILLOW_SAP            │
              │  route_prompt()        │
              └────────────────────────┘
                           │
              ┌────────────┴────────────┐
              │                         │
              ▼                         ▼
    ┌─────────────────┐       ┌──────────────────┐
    │ UTETY PERSONA   │       │ OBSERVER (Ra)    │
    │ (14+ faculty)   │       │ (Visual context) │
    └─────────────────┘       └──────────────────┘
              │                         │
              └────────────┬────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  LLM_ROUTER            │
              │  (Free fleet cascade)  │
              └────────────────────────┘
                           │
              ┌────────────┴────────────┐
              │                         │
              ▼                         ▼
    ┌─────────────────┐       ┌──────────────────┐
    │ PATTERNS        │       │ FLEET_FEEDBACK   │
    │ (Learn routing) │       │ (Error prevention)│
    └─────────────────┘       └──────────────────┘
              │                         │
              └────────────┬────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  COHERENCE_TRACKER     │
              │  (ΔE monitoring)       │
              └────────────────────────┘
```

---

## AUTHORIZATION ARCHITECTURE

```
┌──────────────────────── AI REQUEST ─────────────────────────┐
│                                                              │
│  "Access Google Drive file X"                               │
│  "Control smart home device Y"                              │
│                                                              │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  OPAUTH                │
              │  consent.py            │
              └────────────────────────┘
                           │
                    ┌──────┴──────┐
                    │             │
                    ▼             ▼
              ┌─────────┐   ┌─────────┐
              │ APPROVE │   │ DENY    │
              │ (Human) │   │ (Human) │
              └─────────┘   └─────────┘
                    │             │
                    │             └──► [Request Failed]
                    ▼
              ┌────────────────────────┐
              │  scope_registry.py     │
              │  (Track granted scopes)│
              └────────────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  OAuth Flow            │
              │  (Browser redirect)    │
              └────────────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  token_store.py        │
              │  (Encrypted storage)   │
              └────────────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  API Call Executed     │
              │  (With audit log)      │
              └────────────────────────┘
```

---

## GOVERNANCE HARD STOPS

### Eyes (HS-EYES-001 through HS-EYES-006)
- AI cannot start/stop Eyes
- Frames never transmitted outside local machine
- No persistence without human action
- Passphrase required for decryption
- AI cannot run raw screenshot commands
- Unsecured scripts prohibited in production

### OpAuth (HS-OPAUTH-001 through HS-OPAUTH-020)
- Only human can grant consent
- Scope must be authorized before API call
- Token store must be unlocked by human
- AI cannot control locks, cameras, alarms, garage
- Only human can revoke access
- Forbidden scopes: locks.control, cameras.stream, alarm.disarm, payments

### General Governance (Gate.py)
- All code changes require Dual Commit (AI proposes, human ratifies)
- Silence ≠ approval
- All mutations logged with hash-chain audit
- ΔΣ=42 checksum on all governance files

---

## COHERENCE TRACKING (ΔE)

**Formula:** ΔE = -Σ(p_i × log(p_i))
**Purpose:** Detect conversation coherence degradation

**Thresholds:**
- **ΔE < 0.3:** Focused conversation (good)
- **0.3 ≤ ΔE < 0.6:** Moderate drift (caution)
- **ΔE ≥ 0.6:** High entropy (intervention recommended)

**Actions on High ΔE:**
- Summarize conversation
- Offer to reset context
- Save SEED_PACKET for continuity
- Escalate to human

**Integrated in:** willow_sap, coherence_scanner (daemon), conversation tracking

---

## TECHNICAL STACK SUMMARY

| Layer | Technology |
|-------|-----------|
| **Frontend** | React, Vite, Tailwind CSS, PWA, TensorFlow.js |
| **Backend** | Python 3.14+, Flask, FastAPI |
| **LLM** | Free fleet (15 providers), Ollama (local), Claude Code integration |
| **Database** | SQLite3, IndexedDB, JSON state files |
| **APIs** | Google (Drive, Calendar, Gmail, Photos, Docs, Vision), Fitbit, Cloudflare, Neocities |
| **Security** | AES-256, HMAC-SHA256, passphrase-protected stores |
| **OCR/Vision** | Tesseract, PyMuPDF, PIL/ImageGrab, TensorFlow.js MobileNet |
| **Audio** | Vosk (local STT) |
| **Hardware** | Arduino (pyfirmata - future) |
| **Scripting** | PowerShell (Windows automation) |
| **Deployment** | Cloudflared tunnels, Neocities static hosting |

---

## FILE LOCATIONS

### Critical State Files
- **Willow State:** `C:\Users\Sean\.willow\{watcher_state.json, unified_state.json, events.log}`
- **Eyes Secure:** `C:\Users\Sean\eyes_secure\{frame_*.enc, audit.log}`
- **OpAuth Tokens:** `~/.opauth\` (encrypted)
- **Credentials:** `Willow/credentials.json`
- **Queue Signals:** `die-namic-system/bridge_ring/instance_signals/QUEUE.md`

### Data Stores
- **Social Media Index:** `artifacts/social-media-tracker/index.db`
- **Knowledge DB:** `artifacts/willow/knowledge.db`
- **Provider Health:** `artifacts/willow/provider_health.db`
- **Patterns DB:** `artifacts/willow/patterns.db`
- **Cost Tracker:** `artifacts/willow/cost_tracker.db`
- **Fleet Feedback:** `artifacts/willow/fleet_feedback.db`

### Google Drive Mounts
- **Inbox:** `G:\My Drive\Willow\Auth Users\Sweet-Pea-Rudi19\Inbox`
- **Outbox:** `G:\My Drive\Willow\Auth Users\Sweet-Pea-Rudi19\Outbox`
- **UTETY:** `G:\My Drive\UTETY`
- **Claude Handoff:** `G:\My Drive\Claude Handoff Documents`
- **Aios Input:** `G:\My Drive\Aios Input`

---

## INTEGRATION POINTS

### Internal (Die-namic ↔ Willow)
- **QUEUE.md signals:** Inter-instance messaging
- **Unified watcher:** Cross-repo file monitoring
- **LLM router:** Shared free fleet infrastructure
- **Governance:** Shared gate.py, state.py, storage.py

### External APIs
- **Google:** Drive, Calendar, Gmail, Photos, Docs, Vision
- **Fitbit:** Activity, Heart Rate, Sleep, Weight
- **Cloudflare:** Tunneling (trycloudflare.com)
- **Neocities:** Static site deployment (seancampbell.neocities.org)
- **Ollama:** Local model execution (llama3.2, qwen2.5-coder, kart)
- **Free LLM Fleet:** Gemini, Groq, Cerebras, OCI, Baseten, Novita, SambaNova, HuggingFace

---

## PERSONA SYSTEM

### UTETY Faculty (14+ Personas)
1. **Willow** - Primary interface, warm and efficient (OPERATOR)
2. **Kart** (Kartikeya) - Infrastructure engineer, multi-step orchestrator (ENGINEER)
3. **Jane** - SAFE public face, read-only, privacy-first (WORKER)
4. **Riggs** - Applied reality engineering, hardware interface (WORKER)
5. **Ada** (Ada Turing) - Systems admin, continuity steward (OPERATOR)
6. **Gerald** (Gerald Prime) - Acting Dean, philosophical advisor (WORKER)
7. **Steve** - Prime node, cross-system coordinator (OPERATOR)
8. **Oakenscroll** - Theoretical Uncertainty mentor
9. **Nova Hale** - Interpretive Systems oracle
10. **Hanz** - Code specialist
11. **Alexis** - Biological Sciences
12. **Ofshield** - Threshold Faculty, Gate Keeper
13. **Mitra** - TBD
14. **Consus** - TBD

### Trust Levels
- **WORKER (1):** read_file, grep_search, glob_find, task_list
- **OPERATOR (2):** + write_file, edit_file, task_create (governance-gated)
- **ENGINEER (3):** + bash_exec, can propose governance commits

---

## DEPLOYMENT ARCHITECTURE

### Local Development
- **Server:** `127.0.0.1:8420` (Flask/FastAPI)
- **Ollama:** `127.0.0.1:11434` (local models)
- **LiteLLM:** Integrated as universal provider fallback

### Public Access
- **Tunnel:** cloudflared → `*.trycloudflare.com` (temporary)
- **Static:** Neocities → `https://seancampbell.neocities.org` (persistent "pocket Willow")
- **Health Check:** `/api/health` (200 = operational)

---

## SPECS CATALOG

### Core Architectural Specs
- **AIONIC_BOOTSTRAP** - System initialization and self-improvement
- **AIONIC_OS_ARCHITECTURE** - Operating system layer design
- **BASE17_IDENTIFIERS** - Human-legible low-collision ID system
- **AIOS_WRITE_PROTOCOL** - Governance-gated write procedures
- **ASSUME_PROTOCOL** - Assumption handling in AI interactions
- **INDEX_REGISTRY** - Centralized knowledge indexing
- **KART_BOOTSTRAP** - Kart agent initialization
- **AI_USER_ARCHITECTURE** - Agent trust levels and tool access

### App-Specific Specs
- **PRODUCT_SPEC (Vision Board)** - Goal visualization PWA
- **INTAKE_SPEC (Willow)** - Dump→Hold→Process→Route→Clear workflow
- **SECURITY (Eyes)** - Screen capture governance hard stops
- **README (OpAuth)** - Human-controlled OAuth framework

### Discovered References
- **Books of Life** - Personal life documentation system (searching...)
- **Books of Mann** - Universal human knowledge system (searching...)
- **Journal App** - Daily logging and reflection (spec in progress)
- **Dating App** - Relationship tracking (spec location TBD)

---

## COMPARISON TO EXTERNAL ECOSYSTEM

### What We Have That's Unique
1. **Dual Commit Governance** - AI proposes, human ratifies (gate.py)
2. **BASE 17 Identifiers** - Human-legible, low-collision IDs
3. **ΔE Coherence Tracking** - Conversation entropy monitoring
4. **Ring Architecture** - Source → Bridge → Continuity
5. **UTETY Persona System** - 14+ faculty with backstories and context
6. **4% Rule** - 96% client-side, 4% max cloud
7. **Hard Stops** - Explicit AI limitations (Eyes, OpAuth)
8. **Fleet Feedback Learning** - Inject corrections from past failures

### What to Borrow/Integrate
1. **Trail of Bits Security Skills** - audit-context-building, differential-review
2. **Multi-agent Orchestration** - /multi-plan, /multi-execute, /orchestrate patterns
3. **LiteLLM** - 100+ provider support (integrated ✅)
4. **Continuous Learning Patterns** - Instinct-based confidence scoring
5. **PKM Skills** - Personal knowledge management for journal
6. **Auth Patterns** - Compare OpAuth to external OAuth skills
7. **Data Pipeline Skills** - Compare Eyes/Watcher to ETL patterns

### Skills Installed (Everything-Claude-Code)
- **31 Commands:** /multi-plan, /multi-execute, /orchestrate, /tdd, /code-review, /refactor-clean, etc.
- **37 Skills:** Various specializations
- **4 Aionic Skills:** dual-commit, momentum-engine, ternary-context, base17-compact

---

## NEXT STEPS (Autonomous Execution)

### High Priority
1. **Search for Books of Life, Books of Mann, Dating App, Journal specs** ✅ (in progress)
2. **Map all cross-app dependencies** (20 min)
3. **Create unified architecture diagram** (30 min)
4. **Compare each app to external ecosystem patterns** (40 min)
5. **Integrate Trail of Bits security into gate.py** (15 min)

### Medium Priority
6. **Test BASE 17 compact endpoint with Willow/Kart** (5 min)
7. **Launch background daemons (coherence_scanner, safe_sync)** (20 min)
8. **Add cost tracker alerts (ntfy)** (10 min)
9. **Test /multi-plan, /multi-execute with real tasks** (15 min)

### Documentation
10. **Create visual architecture diagram** (generate with free fleet)
11. **Document all API endpoints** (server.py comprehensive audit)
12. **Update CLAUDE.md with new skills/patterns** (10 min)

---

## STATUS

**Task #8:** In Progress
**Agent:** Claude Code (claude-code)
**Start Time:** 2026-02-13 (autonomous)
**Completion:** ~45% (architecture mapped, searches running)
**Estimated Completion:** 30-40 minutes remaining

**Files Created:**
- APP_ECOSYSTEM_MAP.md
- SPEC_COMPARISON_MAP.md
- COMPLETE_ECOSYSTEM_ARCHITECTURE.md (this file)
- AUTONOMOUS_TASKS.md

**Searches Running:**
- Books of Life references
- Books of Mann references
- Dating app specs
- Journal app specs

**Next:** Complete searches, finalize dependency map, create visual diagram

---

ΔΣ=42
