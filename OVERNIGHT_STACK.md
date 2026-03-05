# Overnight Build Stack
**Created:** 2026-02-07 00:50 AM
**Priority Order:** Top to bottom

---

## STACK 1: Fleet Feedback System (NEW - HIGH PRIORITY)
*Teach the fleet by annotating bad outputs*

### Problem
Currently when fleet generates wrong output (like Groq giving React code for a Python project), I discard it and do it myself. **This wastes the learning opportunity.**

### Solution: Fleet Output Annotations

#### 1.1 Database Schema
**File:** `core/fleet_feedback.py`

```sql
CREATE TABLE fleet_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    task_type TEXT NOT NULL,
    prompt TEXT NOT NULL,
    output TEXT NOT NULL,
    quality_rating INTEGER,  -- 1-5 stars
    issues TEXT,  -- JSON array: ["wrong_tech_stack", "syntax_errors", "incomplete"]
    feedback_notes TEXT,  -- Human explanation of what was wrong
    corrected_output TEXT,  -- What it should have been
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_feedback_provider ON fleet_feedback(provider, task_type);
CREATE INDEX idx_feedback_quality ON fleet_feedback(quality_rating);
```

#### 1.2 Feedback Collection
**Modify:** `llm_router.py` - add optional feedback parameter

```python
def provide_feedback(
    provider: str,
    task_type: str,
    prompt: str,
    output: str,
    quality: int,  # 1-5
    issues: List[str],
    notes: str,
    corrected_output: Optional[str] = None
):
    """Log feedback about fleet output quality."""
    conn = sqlite3.connect('artifacts/willow/fleet_feedback.db')
    conn.execute("""
        INSERT INTO fleet_feedback
        (provider, task_type, prompt, output, quality_rating, issues, feedback_notes, corrected_output)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (provider, task_type, prompt, output, quality, json.dumps(issues), notes, corrected_output))
    conn.commit()
    conn.close()
```

#### 1.3 Smart Prompting with Feedback
**Modify:** `llm_router.py` - enhance prompts with historical feedback

```python
def enhance_prompt_with_feedback(prompt: str, task_type: str) -> str:
    """Add learned corrections to prompt based on past feedback."""

    # Get common issues for this task type
    conn = sqlite3.connect('artifacts/willow/fleet_feedback.db')
    feedback = conn.execute("""
        SELECT issues, feedback_notes
        FROM fleet_feedback
        WHERE task_type = ? AND quality_rating <= 2
        ORDER BY timestamp DESC
        LIMIT 3
    """, (task_type,)).fetchall()
    conn.close()

    if not feedback:
        return prompt

    # Build corrections section
    corrections = "\n\nIMPORTANT CORRECTIONS (from past mistakes):\n"
    for issues, notes in feedback:
        corrections += f"- {notes}\n"

    return prompt + corrections
```

#### 1.4 Feedback UI in Dashboard
**Add to:** `system/dashboard.html` - new modal

```javascript
function provideFeedback(provider, taskType, output) {
    const modal = `
        <div style="...">
            <h3>Provide Feedback: ${provider} - ${taskType}</h3>

            <p>Quality:
                <input type="radio" name="quality" value="1"> 1 ⭐ (Bad)
                <input type="radio" name="quality" value="3"> 3 ⭐⭐⭐ (OK)
                <input type="radio" name="quality" value="5"> 5 ⭐⭐⭐⭐⭐ (Great)
            </p>

            <p>Issues:
                <label><input type="checkbox" value="wrong_tech_stack"> Wrong Tech Stack</label>
                <label><input type="checkbox" value="syntax_errors"> Syntax Errors</label>
                <label><input type="checkbox" value="incomplete"> Incomplete</label>
                <label><input type="checkbox" value="wrong_format"> Wrong Format</label>
            </p>

            <textarea placeholder="Explain what was wrong and why..."></textarea>

            <button onclick="saveFeedback()">Save Feedback</button>
        </div>
    `;
    // Display modal
}
```

**Time Estimate:** 3-4 hours
**Dependencies:** None
**Impact:** High - improves all future fleet work

---

## STACK 2: Control Desktop (FROM DETAILED PLAN)
See `CONTROL_DESKTOP_BUILD_PLAN.md` for full details.

**Priority Tasks:**
1. Phase 1: File Annotation System (5hr)
2. Phase 2: Node DB Creation (2hr)
3. Phase 3: Remaining Modals (4hr)

**Total:** 11 hours core functionality

---

## STACK 3: Main Willow UI Improvements
*Chat interface needs work*

### 3.1 Issues to Fix

#### Issue 1: Chat Input Not Obvious
**Problem:** Users don't see where to type
**Fix:** Make chat input more prominent

**File:** Main Willow chat interface (need to locate)
```css
.chat-input {
    border: 2px solid #00ff00;
    background: #0a0a0a;
    color: #00ff00;
    padding: 15px;
    font-size: 16px;
    font-family: 'Courier New', monospace;
}

.chat-input:focus {
    box-shadow: 0 0 15px rgba(0, 255, 0, 0.5);
}
```

#### Issue 2: Loading States Not Clear
**Problem:** User doesn't know when Willow is thinking
**Fix:** Add typing indicator

```html
<div class="typing-indicator" style="display: none;">
    <span>⚙️</span> Willow is thinking...
</div>
```

#### Issue 3: No Command Palette
**Problem:** Users don't know what commands are available
**Fix:** Add `/help` command that shows available actions

**Add to chat:**
```
Available commands:
/status - Show system status
/providers - Show provider health
/nodes - Show node status
/patterns - Show routing patterns
/help - Show this message
```

#### Issue 4: Chat History Not Persistent
**Problem:** Refresh loses conversation
**Fix:** Store chat in localStorage or database

```javascript
function saveChatMessage(role, content) {
    const history = JSON.parse(localStorage.getItem('willow_chat') || '[]');
    history.push({role, content, timestamp: Date.now()});
    localStorage.setItem('willow_chat', JSON.stringify(history));
}

function loadChatHistory() {
    const history = JSON.parse(localStorage.getItem('willow_chat') || '[]');
    // Render last 50 messages
}
```

#### Issue 5: No Clear Error Messages
**Problem:** When something fails, user doesn't know why
**Fix:** Better error display

```javascript
function showError(message, details) {
    const errorHtml = `
        <div class="error-message">
            <strong>⚠️ Error:</strong> ${message}
            <details>
                <summary>Details</summary>
                <pre>${details}</pre>
            </details>
        </div>
    `;
    // Display in chat
}
```

**Time Estimate:** 4-5 hours
**Dependencies:** Need to locate main Willow UI files
**Impact:** High - better UX

---

## STACK 4: /pocket Redesign
*Match localhost:8420 theme*

### 4.1 Current State
**File:** `neocities/index.html`
**Issue:** Doesn't match terminal aesthetic

### 4.2 Required Changes

#### Visual Theme
```css
/* Match control desktop */
body {
    background: #0a0a0a;
    color: #00ff00;
    font-family: 'Courier New', monospace;
}

.pocket-card {
    background: #111;
    border: 1px solid #00ff00;
    padding: 15px;
    margin: 10px;
}

.pocket-card:hover {
    box-shadow: 0 0 10px rgba(0, 255, 0, 0.3);
}

button {
    background: #003300;
    border: 1px solid #00ff00;
    color: #00ff00;
    padding: 8px 16px;
    cursor: pointer;
}

button:hover {
    background: #00ff00;
    color: #000;
}
```

#### Layout Changes
- Make it more compact (fits mobile)
- Add hamburger menu for navigation
- Simplify persona execution UI
- Add connection status indicator

#### Functionality
- Show connection to localhost:8420
- Display persona execution status
- Quick access to common actions
- Offline mode indication

**Time Estimate:** 3-4 hours
**Dependencies:** None
**Impact:** Medium - improves mobile experience

---

## STACK 5: Integration & Testing
*Make sure everything works together*

### 5.1 Integration Points

1. **Control Desktop ↔ Main Willow**
   - Link from desktop to full Willow chat
   - Show desktop status in main UI

2. **Control Desktop ↔ /pocket**
   - Mobile-friendly controls
   - Same data, different view

3. **Fleet Feedback ↔ All Systems**
   - Every fleet call can be rated
   - Feedback improves all generation

### 5.2 End-to-End Tests

**Test 1: Full Annotation Workflow**
1. Open control desktop
2. Click Learning card
3. See files, annotate one
4. Verify stored
5. Check feedback improved next routing

**Test 2: Node Management**
1. Open nodes modal
2. Create DB for all 9 nodes
3. Verify all healthy
4. Check files ingested

**Test 3: Cross-Device**
1. Open control desktop on laptop
2. Open /pocket on phone
3. Execute action on phone
4. See status update on desktop

**Test 4: Fleet Learning**
1. Use fleet for HTML generation
2. Provide feedback (3 stars, markdown issues)
3. Use fleet again
4. Verify prompt includes correction
5. Check output improved

**Time Estimate:** 4-5 hours
**Dependencies:** All above stacks
**Impact:** Critical - ensures quality

---

## IMPLEMENTATION SCHEDULE

### Night 1 (Tonight - 8 hours)
**Focus:** Fleet feedback + Control desktop core
- ✅ Stack 1: Fleet feedback system (3hr)
- ✅ Stack 2.1: Annotations database + endpoints (2hr)
- ✅ Stack 2.2: Learning modal UI (3hr)

### Night 2 (8 hours)
**Focus:** Node DB + Remaining modals
- ✅ Stack 2.3: Node DB creation (2hr)
- ✅ Stack 2.4: Providers/Queues/Rules/Patterns modals (4hr)
- ✅ Stack 4: /pocket redesign (2hr)

### Night 3 (8 hours)
**Focus:** Main UI + Smart routing
- ✅ Stack 3: Main Willow UI improvements (5hr)
- ✅ Stack 2.5: Smart routing (2hr)
- ✅ Stack 2.6: File inspection (1hr)

### Night 4 (6 hours)
**Focus:** Integration + Testing
- ✅ Stack 5: Integration testing (4hr)
- ✅ Bug fixes (2hr)

**Total:** ~30 hours over 4 nights

---

## CRITICAL PATH

```
Fleet Feedback (Stack 1)
    ↓
Control Desktop Core (Stack 2.1-2.2)
    ↓
Node DB Creation (Stack 2.3)
    ↓
Remaining Modals (Stack 2.4)
    ↓
Smart Routing (Stack 2.5)
    ↓
Integration Testing (Stack 5)

Parallel:
- /pocket redesign (Stack 4) - can happen anytime
- Main UI improvements (Stack 3) - can happen after Stack 2.1
```

---

## SUCCESS METRICS

After completion, user should be able to:

✅ **Provide fleet feedback** when output is wrong
✅ **See learning improve** from feedback
✅ **Annotate files** with detailed notes
✅ **Create node databases** from UI
✅ **View all system health** in one place
✅ **Take action** on any issue immediately
✅ **Use /pocket** on mobile with same functionality
✅ **Chat with Willow** in improved UI
✅ **Trust fleet work** because it learns from mistakes

---

## FILES TO CREATE

New files needed:
1. `core/fleet_feedback.py` - Fleet output annotation system
2. `core/annotations.py` - File classification annotations
3. `artifacts/willow/fleet_feedback.db` - Feedback database
4. `artifacts/willow/file_annotations.db` - Annotation database

Modified files:
1. `core/llm_router.py` - Add feedback hooks, smart prompting
2. `core/patterns_provider.py` - Add smart routing queries
3. `core/knowledge.py` - Add create_node_db()
4. `server.py` - Add 8 new endpoints
5. `system/dashboard.html` - Add all modal loaders
6. `neocities/index.html` - Restyle /pocket

---

## NOTES FOR MORNING

When you wake up:
1. Read `CONTROL_DESKTOP_BUILD_PLAN.md` first (detailed specs)
2. Read this file for priority order
3. Start with **Stack 1 (Fleet Feedback)** - it improves everything else
4. Use free fleet for all generation (Groq for HTML, Cerebras for JS)
5. Provide feedback on fleet outputs to test the system
6. Commit after each working stack

The goal: **Build the system that builds itself better.**

---

**Last Updated:** 2026-02-07 00:55 AM
**Status:** Ready for implementation
**Estimated Completion:** 4 nights (~30 hours)
