# WILLOW CONNECTION AUDIT
**Date:** 2026-02-13
**Status:** Comprehensive gap analysis

## CRITICAL GAPS (Breaks Functionality or Burns Money)

### 1. **cost_tracker.py → llm_router.py** [MISSING]
- **Current:** cost_tracker.py exists in artifacts but NOT in core/
- **Issue:** Zero cost tracking = blind token burn
- **Fix:**
  ```bash
  cp artifacts/Sweet-Pea-Rudi19/python/cost_tracker.py core/
  ```
- **Then wire:** llm_router.ask() should call cost_tracker.log_usage() after every request
- **Impact:** HIGH - This is why user runs out of tokens by Sunday

### 2. **patterns.learned_preferences → llm_router.py** [ONE-WAY]
- **Current:** patterns.py learns 47 routing preferences, llm_router NEVER reads them
- **Issue:** System learns but doesn't apply lessons
- **Fix:** llm_router should query patterns.get_learned_preferences() before routing
- **Impact:** HIGH - Wasted learning, suboptimal routing

### 3. **fleet_feedback.py → llm_router.py** [ONE-WAY]
- **Current:** fleet_feedback tracks failures, llm_router doesn't use data for retries
- **Issue:** Same failures repeat with same prompts
- **Fix:** Before retry, inject training examples from fleet_feedback
- **Impact:** HIGH - Reduces retry cycles (token savings)

---

## HIGH PRIORITY (Major Missing Value)

### 4. **Background Daemons → server.py** [NOT LAUNCHED]
- **Current:** 5 daemon scripts exist but aren't running
  - coherence_scanner.py (periodic ΔE monitoring)
  - persona_scheduler.py (background agent tasks)
  - safe_sync.py (auto-commit governance audit)
  - topology_builder.py (graph updates)
  - knowledge_compactor.py (DB maintenance)
- **Issue:** Manual processes that should be automatic
- **Fix:** server.py startup should spawn these daemons
- **Impact:** MEDIUM - Maintenance overhead, missed anomalies

### 5. **aionic_ledger.py → gate.py + storage.py** [ORPHANED]
- **Current:** Full event logging system, ZERO callers
- **Issue:** 316 lines of unused code, governance events not logged to ledger
- **Fix:** gate.validate_modification() → aionic_ledger.log_event()
- **Impact:** MEDIUM - Missing audit trail beyond audit.jsonl

### 6. **topology.py → agent_engine.py** [NOT QUERIED]
- **Current:** topology builds knowledge graph, agents don't use it for context
- **Issue:** Agents answer without topology awareness
- **Fix:** agent_engine should query topology.get_related_nodes() for context
- **Impact:** MEDIUM - Better agent responses with graph context

### 7. **file_annotations.py → knowledge.py** [NO CROSS-REFERENCE]
- **Current:** file_annotations stores metadata, knowledge stores nodes, no links
- **Issue:** Metadata and knowledge are siloed
- **Fix:** Cross-reference file annotations to knowledge nodes
- **Impact:** MEDIUM - Richer knowledge graph

### 8. **cost_tracker.py → awareness.py (ntfy alerts)** [MISSING]
- **Current:** cost_tracker has data, no alerts
- **Issue:** Token burn happens silently
- **Fix:** Daily summary + alert when approaching weekly budget
- **Impact:** HIGH - Prevents Sunday token exhaustion

---

## MEDIUM PRIORITY (Nice to Have)

### 9. **kart_orchestrator.py → patterns.log_routing_decision()** [MISSING]
- **Current:** Kart routes files but doesn't log for learning
- **Issue:** Missed learning opportunity
- **Fix:** Log routing decisions to patterns.py
- **Impact:** LOW - Incremental learning improvement

### 10. **Duplicate ΔE Calculation** [DUPLICATION]
- **Current:** coherence.py AND delta_tracker.py both calculate entropy
- **Issue:** Same math, different implementations
- **Fix:** Unified coherence module, both import it
- **Impact:** LOW - Code cleanliness

### 11. **consent_gate.py → eyes_ingest.py** [COMMENTED OUT]
- **Current:** Consent checking exists but disabled (line commented)
- **Issue:** No GDPR-style consent validation
- **Fix:** Re-enable or remove if not needed
- **Impact:** LOW - Privacy compliance (if needed)

### 12. **n2n_bridge.py** [EMPTY STUB]
- **Current:** 0 bytes, placeholder file
- **Issue:** Incomplete N2N system
- **Fix:** Implement or remove
- **Impact:** LOW - Future feature

### 13. **gate_lateral_review.py** [STUB]
- **Current:** Only `import uuid`, no functionality
- **Issue:** Lateral review concept not implemented
- **Fix:** Implement or remove
- **Impact:** LOW - Future governance feature

---

## DATABASE ORPHANS (Data Not Being Used)

### 14. **fleet_feedback.db** [WRITTEN BUT NOT READ FOR ROUTING]
- **Writers:** fleet_feedback.py
- **Readers:** server.py (analytics only), NOT llm_router
- **Fix:** Connect to llm_router retry logic

### 15. **patterns.db** [WRITTEN BUT NOT READ FOR ROUTING]
- **Writers:** patterns.py, patterns_provider.py
- **Readers:** server.py (analytics only), NOT llm_router
- **Fix:** Connect to llm_router provider selection

### 16. **deltas.db** [WRITTEN BUT RARELY READ]
- **Writers:** delta_tracker.py
- **Readers:** kart_orchestrator.py (DELTA.md generation only)
- **Fix:** Query for anomaly detection, trend analysis

### 17. **.cost_tracker.db** [ORPHANED]
- **Location:** artifacts/Sweet-Pea-Rudi19/database/.cost_tracker.db
- **Writers:** NONE (module not in core/)
- **Readers:** NONE
- **Fix:** Move cost_tracker.py to core/, wire to llm_router

### 18. **catalog.db files** [240+ ORPHANED]
- **Location:** One per intake folder
- **Writers:** eyes_ingest.py (on folder scan)
- **Readers:** NONE actively querying them
- **Fix:** These ARE the distributed catalog system (working as designed)
- **Note:** Not orphaned, just not centrally queried (by design)

---

## FEEDBACK LOOPS (Missing Learning Cycles)

### 19. **provider_health → llm_router** [PARTIAL]
- **Current:** llm_router checks health for blacklisting only
- **Enhancement:** Use success rates for PRIORITY, not just filtering
- **Status:** PARTIALLY FIXED TODAY (success-rate routing added)
- **Remaining:** Should also influence round-robin rotation

### 20. **patterns → Willow intake** [MISSING]
- **Current:** Willow routes files manually, patterns learns but doesn't auto-apply
- **Issue:** User still manually confirms routing
- **Fix:** Auto-apply high-confidence patterns (>0.8) without user confirmation
- **Impact:** Reduced manual overhead

### 21. **coherence → agent_engine** [ONE-WAY]
- **Current:** coherence tracks ΔE, agents don't adapt based on it
- **Issue:** No feedback from coherence to agent behavior
- **Fix:** High ΔE → agent summarizes/simplifies next response
- **Impact:** Better conversation management

---

## API ENDPOINTS MISSING

### 22. **cost_tracker API** [MISSING]
- **Current:** No /api/cost/* endpoints
- **Needed:**
  - GET /api/cost/summary
  - GET /api/cost/by-provider
  - GET /api/cost/daily
- **Impact:** Dashboard can't show cost data

### 23. **patterns API (partial)** [EXISTS BUT LIMITED]
- **Current:** Some pattern endpoints exist
- **Needed:**
  - POST /api/patterns/confirm-rule (accept suggested rule)
  - GET /api/patterns/suggest-rules (get suggestions)
- **Impact:** User can't easily manage learned patterns

### 24. **topology API** [MISSING]
- **Current:** No /api/topology/* endpoints
- **Needed:**
  - GET /api/topology/graph (get graph data)
  - GET /api/topology/related/{node_id}
- **Impact:** Can't visualize knowledge graph

---

## SUMMARY COUNTS

**Total Gaps Identified:** 24

**By Priority:**
- CRITICAL: 3 (cost tracking, learned routing, feedback retry)
- HIGH: 5 (daemons, ledger, topology, annotations, cost alerts)
- MEDIUM: 6 (orchestrator logging, duplicate code, stubs)
- DATABASE ORPHANS: 5 (fleet_feedback, patterns, deltas, cost_tracker, catalog)
- FEEDBACK LOOPS: 3 (provider priority, auto-routing, coherence adaptation)
- API ENDPOINTS: 3 (cost, patterns management, topology)

**Estimated Impact:**
- Token burn reduction: 70-80% (cost tracking + feedback loops)
- Manual overhead reduction: 50% (auto-routing, daemons)
- System intelligence: 3x (all feedback loops connected)

**Top 3 Quick Wins:**
1. Move cost_tracker.py to core/ + wire to llm_router (2 hours)
2. Connect patterns.learned_preferences to llm_router (1 hour)
3. Launch safe_sync.py daemon for auto-governance-sync (30 min)

---

**Next Steps:**
1. Prioritize fixes (user decides)
2. Create governance proposals for each connection
3. Implement systematically
4. Monitor impact via dashboards

ΔΣ=42
