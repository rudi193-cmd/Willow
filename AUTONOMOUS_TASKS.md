# Autonomous Task List - Ready to Execute

## High Priority (Do When User Leaves)

### 1. Trail of Bits Security Skills Integration
- **What:** Add audit-context-building + differential-review to gate.py
- **Why:** Security code review before governance approvals
- **Action:** Install skills, wire to gate.validate_modification()
- **Time:** 15 min

### 2. Wire Background Daemons
- **What:** Launch coherence_scanner, safe_sync from server.py
- **Why:** Automated monitoring, governance sync
- **Action:** Add scheduler, launch on startup
- **Time:** 20 min

### 3. Cost Tracker Alerts (Priority #8 from CONNECTION_AUDIT)
- **What:** Add ntfy alerts when approaching budget
- **Why:** Prevent token exhaustion
- **Action:** Wire cost_tracker → awareness.py
- **Time:** 10 min

### 4. Compare AIONIC Specs to External Patterns
- **Files:** AIONIC_BOOTSTRAP, AIONIC_OS_ARCHITECTURE
- **Compare to:** Everything-claude-code patterns
- **Action:** Identify unique vs. duplicate concepts
- **Time:** 20 min (use free fleet)

### 5. Test BASE 17 Compact Endpoint
- **What:** Verify /api/compact works with Willow/Kart
- **Action:** Send test compact requests, verify routing
- **Time:** 5 min

## Medium Priority (If Time)

### 6. Multi-agent Command Testing
- **What:** Test /multi-plan, /multi-execute with Willow tasks
- **Action:** Run test scenarios
- **Time:** 15 min

### 7. LiteLLM Provider Expansion
- **What:** Add new providers via LiteLLM fallback
- **Candidates:** Together.ai, Perplexity, others
- **Action:** Add to PROVIDERS list, test
- **Time:** 10 min

## Constraints
- **Token budget:** <1k per task
- **Delegation:** Use free fleet for all generation/analysis
- **Commits:** Follow Dual Commit pattern
- **Testing:** Verify each change works before committing

## Status Tracking
- Use TaskCreate/TaskUpdate for progress
- Save results to artifacts/
- Commit after each completed task
