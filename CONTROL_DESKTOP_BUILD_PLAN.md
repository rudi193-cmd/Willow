# Control Desktop Build Plan
**Created:** 2026-02-07
**Objective:** Complete auditable AI orchestration system with file annotation, verification, and smart routing

---

## PHASE 1: File Annotation System (PRIORITY 1)
*Why users can verify and correct AI learning*

### 1.1 Database Schema (Complexity: Low, Time: 30min)
**File:** `core/annotations.py`

```sql
CREATE TABLE file_annotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    original_category TEXT NOT NULL,
    corrected_category TEXT,
    classification_correct BOOLEAN,
    annotation TEXT,  -- User's notes explaining why
    annotated_by TEXT DEFAULT 'user',
    confidence REAL,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(file_path, timestamp)
);

CREATE INDEX idx_annotations_file ON file_annotations(file_path);
CREATE INDEX idx_annotations_category ON file_annotations(original_category);
```

**Functions:**
- `init_annotations_db()` - Create tables
- `annotate_file(file_path, original_cat, corrected_cat, is_correct, notes)` - Save annotation
- `get_file_annotations(file_path)` - Retrieve annotation history
- `get_misclassified_files()` - Files marked wrong (training data)
- `get_edge_cases()` - Files with long annotations (interesting cases)

---

### 1.2 Backend Endpoints (Complexity: Med, Time: 1hr)
**File:** `server.py`

```python
@app.post("/api/annotations/save")
async def save_annotation(request: Request):
    """Save user annotation for a file classification."""
    body = await request.json()
    # file_path, original_category, corrected_category, is_correct, notes
    annotations.annotate_file(...)
    return {"success": True}

@app.get("/api/annotations/{file_path:path}")
async def get_annotations(file_path: str):
    """Get annotation history for a file."""
    return annotations.get_file_annotations(file_path)

@app.get("/api/learning/files")
async def get_learning_files(category: str, limit: int = 100):
    """Get list of files in a learned category with annotation status."""
    # Query routing history + join with annotations
    return {"files": [...]}
```

---

### 1.3 Learning Modal UI (Complexity: Med, Time: 2hr)
**File:** `system/dashboard.html` - add `loadLearningModal()`

**UI Structure:**
```
┌─ Learning Modal ────────────────────────────────────┐
│ Pattern: unknown → text (110 files, 100% confidence)│
│                                                      │
│ [Show All] [Show Unverified] [Show Incorrect]      │
│                                                      │
│ ☑ invoice_2024.txt                                  │
│   ├─ Size: 2.3KB, Modified: 2026-02-06            │
│   ├─ Classified: text (100% conf, 5 occurrences)   │
│   └─ Status: ✓ Verified                            │
│      [View] [Edit Annotation]                       │
│                                                      │
│ ☐ image_data.json  ← Unverified                    │
│   ├─ Size: 45KB, Modified: 2026-02-05             │
│   ├─ Classified: text (100% conf, 1 occurrence)    │
│   └─ [Preview] [Annotate]                          │
│                                                      │
└──────────────────────────────────────────────────────┘
```

**Click Annotate:**
```
┌─ Annotate File ─────────────────────────────────────┐
│ File: image_data.json                                │
│ Current: text                                        │
│                                                      │
│ ◉ Correct                                           │
│ ◯ Wrong - Reclassify to: [dropdown: document/code/data/...]│
│                                                      │
│ Notes (explain your reasoning):                     │
│ ┌──────────────────────────────────────────────┐   │
│ │ This is JSON data, not plaintext. Should be  │   │
│ │ classified as 'data' not 'text'. JSON files  │   │
│ │ need structured parsing, not text search.    │   │
│ └──────────────────────────────────────────────┘   │
│                                                      │
│ [Save Annotation] [Cancel]                          │
└──────────────────────────────────────────────────────┘
```

**JavaScript:**
```javascript
async function loadLearningModal() {
    // 1. Fetch /api/patterns/preferences
    // 2. For each pattern, fetch files via /api/learning/files
    // 3. Display with checkboxes, annotation status
    // 4. Click file → show annotation form
    // 5. Save → POST /api/annotations/save
}
```

---

## PHASE 2: Node Database Creation (PRIORITY 2)
*Fix the 9 nodes showing no_db*

### 2.1 Backend: Create Knowledge DB (Complexity: Med, Time: 1hr)
**File:** `core/knowledge.py` - add function

```python
def create_node_db(username: str, node_name: str) -> dict:
    """
    Create knowledge.db for a node.

    Args:
        username: User (e.g., "Sweet-Pea-Rudi19")
        node_name: Node (e.g., "documents", "photos")

    Returns:
        {"success": bool, "db_path": str, "message": str}
    """
    # 1. Get node path: artifacts/willow/{username}/{node_name}/
    # 2. Create knowledge.db with init_db()
    # 3. Scan node directory for existing files
    # 4. Ingest files into knowledge db
    # 5. Return status
```

### 2.2 Backend Endpoint (Complexity: Low, Time: 30min)
**File:** `server.py`

```python
@app.post("/api/nodes/create_db")
async def create_node_db(request: Request):
    """Create knowledge database for a node."""
    body = await request.json()
    username = body.get("username")  # Or get from session
    node_name = body.get("node_name")

    result = knowledge.create_node_db(username, node_name)
    return result
```

### 2.3 Wire Up Button (Complexity: Low, Time: 15min)
**File:** `system/dashboard.html` - update `loadNodesModal()`

```javascript
async function createNodeDB(nodeName) {
    if (!confirm(`Create knowledge database for node '${nodeName}'?`)) return;

    try {
        const r = await fetch('/api/nodes/create_db', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({node_name: nodeName, username: 'Sweet-Pea-Rudi19'})
        });
        const result = await r.json();

        if (result.success) {
            alert(`Database created: ${result.db_path}`);
            await loadNodesModal(); // Refresh
        } else {
            alert(`Error: ${result.message}`);
        }
    } catch(e) {
        alert(`Failed: ${e.message}`);
    }
}
```

---

## PHASE 3: Remaining Modals (PRIORITY 3)
*Complete the 5 other modals*

### 3.1 Providers Modal (Complexity: Low, Time: 1hr)
**Show:** Full provider mesh with actions

```javascript
async function loadProvidersModal() {
    const r = await fetch('/api/health/providers');
    const d = await r.json();

    let html = '<table><tr><th>Provider</th><th>Status</th><th>Success Rate</th><th>Avg Response</th><th>Actions</th></tr>';

    for (const [name, p] of Object.entries(d.providers)) {
        const avgTime = p.total_requests > 0 ? '~' + (p.response_time_ms / p.total_requests).toFixed(0) + 'ms' : 'N/A';

        let actions = '';
        if (p.status === 'blacklisted') {
            actions = `<button onclick="unblacklistProvider('${name}')">Unblock Now</button>`;
        } else if (p.status === 'degraded') {
            actions = `<button onclick="resetProviderHealth('${name}')">Reset Health</button>`;
        }
        actions += ` <button onclick="testProvider('${name}')">Test Now</button>`;

        html += `<tr>
            <td>${name}</td>
            <td style="color:${getStatusColor(p.status)}">${p.status}</td>
            <td>${p.success_rate.toFixed(1)}%</td>
            <td>${avgTime}</td>
            <td>${actions}</td>
        </tr>`;
    }

    html += '</table>';
    document.getElementById('modal-body').innerHTML = html;
}
```

### 3.2 Queues Modal (Complexity: Low, Time: 45min)
**Show:** Queue status with retry/clear actions

```javascript
async function loadQueuesModal() {
    const r = await fetch('/api/health/queues');
    const d = await r.json();

    let html = '<table><tr><th>Queue</th><th>Files</th><th>Status</th><th>Actions</th></tr>';

    for (const [name, q] of Object.entries(d.queues)) {
        let actions = '';
        if (q.count > 0 && name !== 'dump' && name !== 'clear') {
            actions = `
                <button onclick="retryQueue('${name}')">Retry All</button>
                <button onclick="clearQueue('${name}')">Clear</button>
            `;
        }

        html += `<tr>
            <td>${name}</td>
            <td>${q.count}</td>
            <td>${q.status}</td>
            <td>${actions}</td>
        </tr>`;
    }

    html += '</table>';
    document.getElementById('modal-body').innerHTML = html;
}
```

### 3.3 Rules Modal (Complexity: Med, Time: 1.5hr)
**Show:** Suggested routing rules with confirm/reject

```javascript
async function loadRulesModal() {
    const r = await fetch('/api/patterns/suggestions');
    const d = await r.json();
    const suggestions = d.suggestions || [];

    if (suggestions.length === 0) {
        document.getElementById('modal-body').innerHTML = '<p>No rules suggested yet. System needs more routing data.</p>';
        return;
    }

    let html = '<div>';
    suggestions.forEach((s, idx) => {
        html += `
        <div style="border: 1px solid #00ff00; padding: 15px; margin: 10px 0;">
            <p><strong>Rule ${idx+1}:</strong> ${s.rule}</p>
            <p>Confidence: ${(s.confidence * 100).toFixed(0)}% (based on ${s.based_on})</p>
            <button onclick="confirmRule('${s.pattern_type}', '${s.pattern_value}', '${s.destination}')">✓ Confirm</button>
            <button onclick="rejectRule(${idx})">✗ Reject</button>
        </div>`;
    });
    html += '</div>';

    document.getElementById('modal-body').innerHTML = html;
}
```

### 3.4 Patterns Modal (Complexity: Low, Time: 45min)
**Show:** Overall pattern stats and anomalies

```javascript
async function loadPatternsModal() {
    const r = await fetch('/api/patterns/stats');
    const d = await r.json();

    let html = '<div>';
    html += `<p><strong>Total Routings (30d):</strong> ${d.total_routings || 0}</p>`;
    html += `<p><strong>Unresolved Anomalies:</strong> ${d.unresolved_anomalies || 0}</p>`;

    html += '<h3>Top Destinations:</h3><ul>';
    for (const [dest, count] of Object.entries(d.by_destination || {}).slice(0, 10)) {
        html += `<li>${dest}: ${count}</li>`;
    }
    html += '</ul>';

    html += '<h3>Recent Anomalies:</h3>';
    // Fetch and display anomalies

    html += '</div>';
    document.getElementById('modal-body').innerHTML = html;
}
```

---

## PHASE 4: Smart Routing (PRIORITY 4)
*Use patterns_provider data to optimize routing*

### 4.1 Query Best Provider (Complexity: Low, Time: 30min)
**File:** `core/patterns_provider.py` - add function

```python
def get_best_provider_for_task(task_type: str) -> Optional[str]:
    """
    Get best provider for a task type based on performance history.

    Args:
        task_type: 'html_generation', 'javascript_generation', etc.

    Returns:
        Provider name or None
    """
    conn = _connect()

    # Get providers with success for this task type
    rows = conn.execute("""
        SELECT provider,
               AVG(response_time_ms) as avg_time,
               COUNT(*) as total,
               SUM(CASE WHEN success THEN 1 ELSE 0 END) as successes
        FROM provider_performance
        WHERE category = ?
        GROUP BY provider
        HAVING successes > 3  -- At least 3 successful completions
        ORDER BY successes DESC, avg_time ASC
        LIMIT 1
    """, (task_type,)).fetchall()

    conn.close()

    if rows:
        return rows[0][0]  # Provider name
    return None
```

### 4.2 Update llm_router to Use Smart Routing (Complexity: Med, Time: 1hr)
**File:** `core/llm_router.py` - modify `ask()` function

```python
def ask(prompt: str, preferred_tier: str = "free", use_smart_routing: bool = True) -> Optional[RouterResponse]:
    """
    Route the prompt to a provider.

    If use_smart_routing=True, checks patterns_provider for best provider
    for this task type before falling back to round-robin.
    """
    available = get_available_providers()

    # Smart routing: check performance data
    if use_smart_routing:
        task_type = _infer_task_type(prompt)
        best_provider = patterns_provider.get_best_provider_for_task(task_type)

        if best_provider:
            # Find this provider in available list
            for tier_name, providers in available.items():
                for provider in providers:
                    if provider.name == best_provider:
                        # Try this provider first
                        result = _try_provider(provider, prompt)
                        if result:
                            return result

    # Fall back to normal round-robin cascade
    # ... existing code ...
```

---

## PHASE 5: File Inspection (PRIORITY 5)
*Click a file to see contents and history*

### 5.1 File Preview Endpoint (Complexity: Low, Time: 30min)
**File:** `server.py`

```python
@app.get("/api/files/preview/{file_path:path}")
async def preview_file(file_path: str, lines: int = 50):
    """Preview first N lines of a file."""
    try:
        full_path = Path(file_path)
        if not full_path.exists():
            return {"error": "File not found"}

        # Read first N lines
        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = ''.join(f.readlines()[:lines])

        return {
            "path": file_path,
            "size": full_path.stat().st_size,
            "preview": content,
            "truncated": full_path.stat().st_size > len(content)
        }
    except Exception as e:
        return {"error": str(e)}
```

### 5.2 File Viewer Modal (Complexity: Med, Time: 1.5hr)
**Add:** Sub-modal that opens when clicking a file

```javascript
async function viewFile(filePath) {
    // Open a sub-modal with file preview
    const r = await fetch(`/api/files/preview/${encodeURIComponent(filePath)}`);
    const d = await r.json();

    // Create overlay for file viewer
    const viewer = document.createElement('div');
    viewer.style = 'position: fixed; top: 10%; left: 10%; width: 80%; height: 80%; background: #0a0a0a; border: 2px solid #00ff00; padding: 20px; overflow-y: auto; z-index: 2000;';
    viewer.innerHTML = `
        <h3>${filePath}</h3>
        <p>Size: ${(d.size / 1024).toFixed(2)} KB</p>
        <button onclick="this.parentElement.remove()">Close</button>
        <pre style="background: #111; padding: 10px; overflow-x: auto;">${escapeHtml(d.preview)}</pre>
        ${d.truncated ? '<p>... (truncated)</p>' : ''}
    `;
    document.body.appendChild(viewer);
}
```

---

## PHASE 6: Integration & Testing (PRIORITY 6)

### 6.1 End-to-End Test Plan (Complexity: High, Time: 3hr)

**Test Scenarios:**

1. **Annotation Workflow**
   - Open learning modal
   - See 110 files for "unknown → text"
   - Click file #23 (image_data.json)
   - Mark as "Wrong - Reclassify to: data"
   - Add note: "JSON data, not plaintext"
   - Save annotation
   - Verify stored in file_annotations table
   - Verify shows ✓ annotated in list

2. **Node DB Creation**
   - Open nodes modal
   - See 9 nodes with no_db status
   - Click "Create Database" for "documents" node
   - Verify database created at artifacts/willow/Sweet-Pea-Rudi19/documents/knowledge.db
   - Verify node status changes to "healthy"
   - Verify files in directory ingested

3. **Smart Routing**
   - Generate HTML with fleet (should use Groq)
   - Generate JS with fleet (should use Cerebras)
   - Verify patterns_provider.db logged correctly
   - Verify next HTML task goes to Groq first

4. **Provider Health**
   - Trigger 5 failures on SambaNova
   - Verify auto-blacklist
   - Open providers modal
   - Click "Unblock Now"
   - Verify status changes to healthy

---

## IMPLEMENTATION ORDER

**Day 1 (4-5 hours):**
- Phase 1.1: Annotations database ✓
- Phase 1.2: Annotations endpoints ✓
- Phase 1.3: Learning modal UI ✓
- Test annotation workflow

**Day 2 (3-4 hours):**
- Phase 2.1: create_node_db() function ✓
- Phase 2.2: /api/nodes/create_db endpoint ✓
- Phase 2.3: Wire up Create DB button ✓
- Test node creation on all 9 nodes

**Day 3 (4-5 hours):**
- Phase 3.1: Providers modal ✓
- Phase 3.2: Queues modal ✓
- Phase 3.3: Rules modal ✓
- Phase 3.4: Patterns modal ✓
- Test all modals

**Day 4 (2-3 hours):**
- Phase 4.1: get_best_provider_for_task() ✓
- Phase 4.2: Smart routing in llm_router ✓
- Test smart routing with 10 mixed tasks

**Day 5 (3-4 hours):**
- Phase 5.1: File preview endpoint ✓
- Phase 5.2: File viewer modal ✓
- Test file inspection workflow

**Day 6 (3-4 hours):**
- Phase 6.1: End-to-end testing ✓
- Bug fixes
- Performance optimization

---

## SUCCESS CRITERIA

✅ **User can:**
1. See all 110 files in "unknown → text" category
2. Click any file and annotate with notes
3. Mark files as correct/wrong with explanations
4. Create knowledge databases for all 9 no_db nodes
5. See provider performance in modals
6. Unblock/reset provider health from UI
7. View file contents before annotating
8. See routing automatically prefer best providers

✅ **System learns:**
1. Which files are misclassified (training data)
2. Why files are misclassified (annotations)
3. Which providers are best at which tasks
4. Edge cases with detailed explanations

✅ **Everything is auditable:**
1. Every annotation stored with timestamp
2. Every routing decision logged
3. Every provider call tracked
4. All data queryable from dashboard

---

## TECH STACK CONFIRMED

- **Backend:** Python, FastAPI, SQLite
- **Frontend:** Vanilla JavaScript (no framework)
- **Routing:** llm_router.py (custom multi-provider)
- **Health:** provider_health.py (auto-blacklist)
- **Performance:** patterns_provider.py (learning)
- **Annotations:** annotations.py (NEW - to be created)

---

## NEXT STEPS ON WAKEUP

1. Review this plan
2. Start with Phase 1.1 (annotations.py database)
3. Use free fleet for code generation (will auto-log to patterns_provider)
4. Build incrementally, test each phase
5. Commit after each working phase

---

**Last Updated:** 2026-02-07 00:45 AM
**Status:** Ready to implement
