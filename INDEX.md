# Willow - System Index

Auto-generated navigation for Willow codebase.

**Last Updated:** (auto-generated)

Delta-Sigma=42

---

## Core Modules

### agent_engine
**File:** `core\agent_engine.py`
**Purpose:** Agent Engine - Conversational AI with Tool Access

### agent_registry
**File:** `core\agent_registry.py`
**Purpose:** Agent Registry — Willow

### aionic_ledger
**File:** `core\aionic_ledger.py`
**Purpose:** No description

### awareness
**File:** `core\awareness.py`
**Purpose:** Willow Awareness Layer — When to Speak

### checksum_chain
**File:** `core\checksum_chain.py`
**Purpose:** Checksum Chain - ΔΣ=42 Validation

### coherence
**File:** `core\coherence.py`
**Purpose:** ΔE Coherence Tracker — Python Implementation

### coherence_scanner
**File:** `core\coherence_scanner.py`
**Purpose:** No description

### consent_gate
**File:** `core\consent_gate.py`
**Purpose:** Consent Gate — checks opauth consent before signal sources activate.

### context_check
**File:** `core\context_check.py`
**Purpose:** Context Check - Query RAG before architectural decisions

### conversation_rag
**File:** `core\conversation_rag.py`
**Purpose:** Conversation RAG - Index and query Claude Code session logs

### cost_tracker
**File:** `core\cost_tracker.py`
**Purpose:** COST_TRACKER.PY - Track LLM API usage and costs

### decision_checklist
**File:** `core\decision_checklist.py`
**Purpose:** Decision Checklist - Pre-architectural-change workflow

### delta_tracker
**File:** `core\delta_tracker.py`
**Purpose:** Delta Tracker - Entropy Change Tracking for AIONIC_CONTINUITY

### embeddings
**File:** `core\embeddings.py`
**Purpose:** Local Embeddings — sentence-transformers wrapper for Willow.

### extraction
**File:** `core\extraction.py`
**Purpose:** Content Extraction — Extract text/data from files for intelligent routing.

### eyes_ingest
**File:** `core\eyes_ingest.py`
**Purpose:** Eyes -> Knowledge Pipeline

### file_annotations
**File:** `core\file_annotations.py`
**Purpose:** File Annotation System

### filename_sanitizer
**File:** `core\filename_sanitizer.py`
**Purpose:** Filename Sanitization for AIOS

### fleet_feedback
**File:** `core\fleet_feedback.py`
**Purpose:** Fleet Feedback System

### gate
**File:** `core\gate.py`
**Purpose:** GATEKEEPER v2.3.0

### gate_lateral_review
**File:** `core\gate_lateral_review.py`
**Purpose:** No description

### health
**File:** `core\health.py`
**Purpose:** HEALTH MONITORING — Willow's Self-Awareness

### kart_orchestrator
**File:** `core\kart_orchestrator.py`
**Purpose:** Kart Orchestrator - Multi-Step Task Execution

### kart_tasks
**File:** `core\kart_tasks.py`
**Purpose:** Kart Task Management System

### knowledge
**File:** `core\knowledge.py`
**Purpose:** Knowledge Accumulation Layer — Willow's Structured Memory

### knowledge_compactor
**File:** `core\knowledge_compactor.py`
**Purpose:** No description

### litellm_adapter
**File:** `core\litellm_adapter.py`
**Purpose:** LiteLLM Adapter - Universal fallback for 100+ LLM providers

### llm_router
**File:** `core\llm_router.py`
**Purpose:** LLM ROUTER v2.0 (JSON LOADER)

### n2n_bridge
**File:** `core\n2n_bridge.py`
**Purpose:** No description

### n2n_db
**File:** `core\n2n_db.py`
**Purpose:** N2N Database - Packet Inbox/Outbox Storage

### n2n_packets
**File:** `core\n2n_packets.py`
**Purpose:** N2N Packets - Node-to-Node Minimal Transport

### patterns
**File:** `core\patterns.py`
**Purpose:** PATTERN RECOGNITION — Willow's Learning System

### patterns_provider
**File:** `core\patterns_provider.py`
**Purpose:** Provider Performance Tracking

### persona_scheduler
**File:** `core\persona_scheduler.py`
**Purpose:** No description

### provider_health
**File:** `core\provider_health.py`
**Purpose:** Provider Health Tracking - Non-Linear Resilience

### recursion_tracker
**File:** `core\recursion_tracker.py`
**Purpose:** No description

### request_manager
**File:** `core\request_manager.py`
**Purpose:** Request Manager — Rate limiting queue + response cache for LLM calls.

### restore_personas
**File:** `core\restore_personas.py`
**Purpose:** No description

### safe_sync
**File:** `core\safe_sync.py`
**Purpose:** No description

### seed_packet
**File:** `core\seed_packet.py`
**Purpose:** Willow Seed Packet Module

### state
**File:** `core\state.py`
**Purpose:** STATE v2.2.1

### storage
**File:** `core\storage.py`
**Purpose:** STORAGE v1.3 (MERGED — Windows + Pending/Human Actions)

### time_resume_capsule
**File:** `core\time_resume_capsule.py`
**Purpose:** No description

### tool_engine
**File:** `core\tool_engine.py`
**Purpose:** Tool Execution Engine for Kart Orchestrator

### topology
**File:** `core\topology.py`
**Purpose:** Möbius Strip Topology Layer

### topology_builder
**File:** `core\topology_builder.py`
**Purpose:** Topology Builder Daemon

### tts_router
**File:** `core\tts_router.py`
**Purpose:** TTS Router — Text-to-speech with local and cloud providers.

### workflow_state
**File:** `core\workflow_state.py`
**Purpose:** No description

## Tools

- **code_rag**: Code RAG - Index Python/MD files for semantic search
- **db_cleanup**: Database Cleanup Tool - Willow
- **db_verify_unique**: Database Uniqueness Verification - Willow
- **generate_index**: Generate Index - Auto-create INDEX.md from directory structure
- **generate_tool**: GENERATE_TOOL.PY - Meta-tool to scaffold new utilities via free LLMs
- **index_all_sessions**: Index All Claude Code Sessions
- **normalize**: Text normalization utilities for cross-platform consistency.
- **populate_index**: Populate Index - Extract metadata into willow_index.db
- **reprocess_all**: Reprocess All - Run complete Willow reindexing
- **validate_release**: Release validation utilities.

## Governance

- [PRODUCT_SPEC.md](PRODUCT_SPEC.md) - Product vision
- [INTAKE_SPEC.md](INTAKE_SPEC.md) - Intake contract
- [ARCHITECTURE_INDEX.md](ARCHITECTURE_INDEX.md) - System architecture

## Databases

**willow_index.db**
- Files indexed: 499
- Functions: 3668
- Classes: 326

---

**Navigation:**
- [Core](core/) - Core system modules
- [Tools](tools/) - Utility scripts
- [Data](data/) - Databases and state

Delta-Sigma=42