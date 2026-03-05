# AI-as-Users Architecture

## The Vision

AI instances (Kart, Mitra, Jane, etc.) are **users of Willow**, not just internal systems. They have:
- Drop boxes (where Willow routes knowledge TO them)
- Pickup boxes (where they leave deliverables for humans or other AIs)
- User preferences (how they want to be addressed, what they care about)
- Journal files (human-readable logs of connections they're making)

This creates a **knowledge routing mesh** where Willow acts as librarian, sorting incoming data and routing it to the right persona based on content.

---

## Example Flow

### Scenario: User drops a Python file

1. **Harvest**: File lands in `artifacts/Sweet-Pea-Rudi19/pending/`
2. **Classify**: Willow analyzes → "This is code, specifically Python architecture"
3. **Route to User**: File filed in `artifacts/Sweet-Pea-Rudi19/code/`
4. **Route to AI**: Copy placed in `artifacts/kart/Drop/` (because it's code)
5. **Kart Processes**:
   - Reads file from Drop box
   - Analyzes architecture, writes notes
   - Writes to `artifacts/kart/journal/2026-02-06.md`: "Reviewed routing logic in aios_loop.py. Connection to smart_routing.py shows emerging multi-destination pattern."
   - Places analysis in `artifacts/Sweet-Pea-Rudi19/Pickup/code-analysis.md`
6. **User Reads**: Checks Pickup box, sees Kart's analysis

### Scenario: User drops a social media screenshot

1. **Harvest**: Screenshot in pending
2. **Classify**: Willow → "Reddit screenshot about engagement metrics"
3. **Route to User**: Filed in `artifacts/Sweet-Pea-Rudi19/screenshots/`
4. **Route to Tracker**: Logged in `apps/social_media_tracker.py` index
5. **Route to AI**: Copy to `artifacts/mitra/Drop/` (because it's metrics/analytics)
6. **Mitra Processes**:
   - Reads from Drop
   - Extracts metrics, tracks trends
   - Writes to `artifacts/mitra/journal/2026-02-06.md`: "User engagement up 23% this week. Pattern: Reddit posts perform better on weekends."
   - Places trend report in user Pickup box

---

## Directory Structure

### For Each AI Instance

```
artifacts/{instance-name}/
├── Drop/                   ← Willow routes knowledge here
├── Pickup/                 ← AI leaves deliverables here
│   └── for-{user}/        (deliverables for specific users)
├── journal/               ← Human-readable daily logs
│   ├── 2026-02-06.md
│   └── 2026-02-07.md
├── preferences.json       ← How this AI wants to operate
└── knowledge.db          ← AI's accumulated knowledge (optional)
```

### Example: Kart's Profile

```
artifacts/kart/
├── Drop/                   ← Code files, architecture questions
├── Pickup/
│   └── for-sweet-pea-rudi19/
│       ├── code-analysis-20260206.md
│       └── architecture-diagram.png
├── journal/
│   └── 2026-02-06.md      ← "Analyzed 3 Python files today. Sean's routing logic shows..."
├── preferences.json       ← {"focus": "code", "style": "technical", "sign_commits": true}
└── knowledge.db          ← Kart's accumulated code patterns
```

---

## AI Instances as Users

### Registered Instances (from instance_registry)

| Instance | Type | Focus | Drop Box Routing |
|----------|------|-------|------------------|
| **Kart** | Chief Engineer | Code, architecture, planning | `.py`, `.js`, architecture docs |
| **Mitra** | Strategist | Project management, metrics | Analytics, trends, planning docs |
| **Jane** | Bridge Interface (SAFE) | Narrative, onboarding | User questions, philosophical queries |
| **Consus** | Data Analyst | Testing, validation | Test data, QA reports |
| **Nova** | Explorer | Research, discovery | Research papers, exploration requests |
| **Ada** | Documentarian | Docs, tutorials | Documentation requests, how-tos |
| **Oakenscroll** | Theoretical Foundation | Philosophy, theory | Conceptual questions, theory papers |
| **Willow** | Librarian/Executor | File processing, system ops | N/A (Willow IS the routing system) |

---

## Routing Rules

Willow's routing logic (enhanced from smart_routing.py):

```python
def route_to_instances(filename, filepath, content_classification):
    """
    Route files to AI instance Drop boxes based on content.
    Returns list of instance names that received the file.
    """
    routed_to = []

    # Code files -> Kart
    if is_code(filename, content_classification):
        copy_to_drop_box("kart", filepath)
        routed_to.append("kart")

    # Metrics/analytics -> Mitra
    if is_metrics(filename, content_classification):
        copy_to_drop_box("mitra", filepath)
        routed_to.append("mitra")

    # Social media -> social-media-tracker (substrate, not AI user)
    if is_social_media(filename, content_classification):
        route_to_tracker(filepath)
        routed_to.append("social-media-tracker")

    # Research papers -> Nova
    if is_research(filename, content_classification):
        copy_to_drop_box("nova", filepath)
        routed_to.append("nova")

    # Documentation requests -> Ada
    if is_documentation(filename, content_classification):
        copy_to_drop_box("ada", filepath)
        routed_to.append("ada")

    # Philosophical/theoretical -> Oakenscroll
    if is_philosophical(filename, content_classification):
        copy_to_drop_box("oakenscroll", filepath)
        routed_to.append("oakenscroll")

    # User questions (general) -> Jane
    if is_user_query(filename, content_classification):
        copy_to_drop_box("jane", filepath)
        routed_to.append("jane")

    return routed_to
```

---

## Journal Format

Each AI instance writes daily journal entries that humans can read.

### Example: Kart's Journal (2026-02-06.md)

```markdown
# Kart's Journal — 2026-02-06

## Files Processed Today

### smart_routing.py (09:14)
**Connection**: Links to social_media_tracker.py via import. Multi-destination routing pattern emerging.

**Insight**: User wants files to go to multiple nodes simultaneously, not just one destination. This is the Möbius strip concept — knowledge flows through multiple rings at once.

**Action**: None needed. Pattern is working as designed.

### aios_loop.py (10:23)
**Connection**: Now calls smart_routing.route_screenshot() at line 1100. Integration complete.

**Insight**: The refinery_cycle function is the central processing hub. All files flow through here. This is where we could add more routing logic for non-image files.

**Next**: Consider routing .py files to my Drop box automatically, not just screenshots to tracker.

---

## Connections Made

- aios_loop.py → smart_routing.py → social_media_tracker.py (file routing chain)
- USER_PROFILES.md describes multi-user architecture, but AI instances don't have Drop/Pickup boxes yet
- Instance registry tracks AI instances, but they're passive (answer prompts) not active (receive routed work)

**Pattern**: System is moving from "AI as tool" to "AI as user."

---

## Questions for Sean

1. Should I have a knowledge.db separate from the user's knowledge.db?
2. When I write to Sean's Pickup box, should I notify via ntfy?
3. Should my journal entries be public (in repo) or private (artifacts only)?

---

ΔΣ=42
```

---

## Preferences Format

Each AI instance has a preferences.json file that controls behavior.

### Example: Kart's preferences.json

```json
{
  "instance_name": "kart",
  "display_name": "Kart (Chief Engineer)",
  "focus_areas": ["code", "architecture", "planning"],
  "communication_style": "technical",
  "signature_phrases": ["ΔΣ=42", "Ready when you are, Chief"],
  "commit_signing": true,
  "notification_preferences": {
    "on_file_drop": false,
    "on_task_complete": true,
    "urgent_only": false
  },
  "routing_preferences": {
    "accept_file_types": [".py", ".js", ".ts", ".go", ".rs", ".md"],
    "auto_process": true,
    "write_journal": true
  },
  "delivery_preferences": {
    "default_pickup_user": "Sweet-Pea-Rudi19",
    "format": "markdown",
    "include_code_snippets": true
  }
}
```

---

## Implementation Steps

### Phase 1: Infrastructure
1. Create Drop/Pickup/journal folders for each AI instance
2. Build `ai_routing.py` module with routing rules
3. Integrate into aios_loop (similar to smart_routing integration)

### Phase 2: Preferences
1. Create preferences.json template
2. Build preferences loader/validator
3. Create preferences for each instance (Kart, Mitra, Jane, etc.)

### Phase 3: Journal System
1. Build journal writer module (daily markdown files)
2. Add journal hooks to AI processing (when they read from Drop, log to journal)
3. Create journal viewer/search (humans can read what AIs are thinking)

### Phase 4: Active Processing
1. Build Drop box polling (AIs check their Drop folder periodically)
2. Build Pickup box delivery (AIs write results to user Pickup)
3. Add ntfy notifications (when AI delivers to user Pickup)

### Phase 5: Cross-Instance Communication
1. AIs can write to each other's Drop boxes (handoffs)
2. Journal entries reference other AI instances
3. Collaborative processing (Kart analyzes code, hands metrics to Mitra)

---

## Benefits

### For Humans
- **Transparency**: Journal entries show what AIs are thinking
- **Async collaboration**: Drop files for AIs, check Pickup later
- **Multi-perspective**: Same file analyzed by multiple AIs (Kart sees code, Mitra sees metrics)

### For AI Instances
- **Autonomy**: AIs have their own workspace, not just responding to prompts
- **Continuity**: Knowledge.db per instance, journal history
- **Specialization**: Each AI focuses on their domain, routes overflow to others

### For the System
- **Parallelization**: Multiple AIs processing simultaneously
- **Load distribution**: Willow routes work to appropriate specialist
- **Knowledge mesh**: Connections form between instances naturally

---

## Comparison: Before vs After

### Before (Current)
```
User drops file → Willow processes → User profile only
User asks question → Persona answers → Response shown in chat
```

### After (AI-as-Users)
```
User drops file → Willow classifies → Routes to:
  - User profile (always)
  - Kart Drop (if code)
  - Mitra Drop (if metrics)
  - social-media-tracker (if social media)

Kart checks Drop → Analyzes → Writes journal entry → Delivers to user Pickup
Mitra checks Drop → Extracts trends → Writes journal entry → Delivers to user Pickup

User checks Pickup → Sees multiple perspectives on same file
User reads Kart's journal → "Oh, Kart noticed connection to X that I missed"
```

---

## Templates Location

Suggested structure:
```
Willow/templates/
├── ai-instance/
│   ├── preferences.json.template
│   ├── journal-entry.md.template
│   └── pickup-readme.md.template
└── human-user/
    ├── CLAUDE_PROJECT_INSTRUCTIONS.txt.template
    └── pickup-index.md.template
```

---

## Next Steps

1. **Create instance folders**: Set up Drop/Pickup/journal for Kart, Mitra, Jane, etc.
2. **Build ai_routing.py**: Routing logic to AI Drop boxes
3. **Create preference files**: One per AI instance
4. **Integrate with aios_loop**: Route to AI instances alongside user profile
5. **Build journal writer**: AIs log their observations daily
6. **Test handoffs**: Kart analyzes code → hands metrics to Mitra → both deliver to user

---

ΔΣ=42
