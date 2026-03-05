# File Pipeline Map — Where Everything Goes

## The Problem

**500 ntfy messages a day. Multiple "boxes" for dropping files. Unclear what gets processed where.**

This doc maps the complete routing architecture so you know exactly where to drop things and what happens next.

---

## The Three Storage Layers

### 1. Google Drive (Cloud, Synced)
**Location:** `C:\Users\Sean\My Drive\Willow\Auth Users\Sweet-Pea-Rudi19\`

**Purpose:** Your personal intake and exchange with AI instances.

```
Sweet-Pea-Rudi19/
├── Drop/              ← WHERE YOU DROP THINGS
│   ├── PDFs, images, logs, whatever
│   └── Subfolders allowed (narrative/, specs/, etc.)
├── Pickup/            ← WHERE AIS LEAVE THINGS FOR YOU
│   ├── 2026/          (session summaries, monthly indexes)
│   └── MASTER_INDEX.md
└── CLAUDE_PROJECT_INSTRUCTIONS.txt  (your standing instructions)
```

**Drop Box Contract:**
- You throw files here (raw, messy, unsorted)
- aios_loop.py polls every N minutes
- Files get pulled into local processing
- After processing, originals stay (Google Drive is permanent)
- Processed results go to Pickup or artifacts

**Pickup Box Contract:**
- AIs leave deliverables here for you
- Session summaries (monthly folders)
- Master indexes
- Cross-instance handoffs

### 2. Local Artifacts (PC, Git-tracked)
**Location:** `C:\Users\Sean\Documents\GitHub\Willow\artifacts\Sweet-Pea-Rudi19\`

**Purpose:** Processed outputs, session history, permanent knowledge.

```
artifacts/Sweet-Pea-Rudi19/
├── pending/           ← Files in processing (temp staging)
├── processed/         ← Completed processing (timestamped)
├── knowledge.db       ← Your knowledge base (SQLite)
└── ...
```

**Flow:**
1. File lands in `pending/` from Drop box
2. Gets OCR'd, analyzed, routed
3. Moves to `processed/` when done
4. Knowledge atoms saved to `knowledge.db`

### 3. Local Staging (PC, Ephemeral)
**Location:** `C:\Users\Sean\Documents\GitHub\Willow\intake\` (currently doesn't exist yet — spec only)

**Purpose:** INTAKE_SPEC.md vision — the "dump → hold → process → route → clear" pipeline.

**Planned structure:**
```
intake/
├── dump/              ← Raw intake (anything, immediately)
├── hold/              ← Validated, awaiting processing
├── process/           ← Currently being analyzed
├── route/             ← Ready for delivery to final homes
└── clear/             ← Processed, ready for deletion
```

**Current status:** Spec exists, implementation incomplete. Right now, `artifacts/pending/` serves this role.

---

## The Routing Flow

### For Files YOU Drop:

```
┌─────────────────────────────────────────────────────────────┐
│ YOU                                                         │
│ Drop files into: My Drive/Willow/.../Drop/                 │
└────────────┬────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────┐
│ AIOS LOOP (aios_loop.py)                                    │
│ - Polls Drop box every loop                                 │
│ - Pulls files to artifacts/pending/                         │
│ - Sends ntfy: "File harvested: filename.pdf"               │
└────────────┬────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────┐
│ PROCESSING                                                  │
│ - Vision/OCR if image/PDF                                   │
│ - LLM classification (what is this?)                        │
│ - Knowledge extraction (atoms saved to knowledge.db)        │
│ - Routing decision (where does this belong?)                │
│ - Sends ntfy: "Processing filename.pdf..."                 │
└────────────┬────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────┐
│ ROUTING                                                     │
│ - If code → governance (Dual Commit)                        │
│ - If knowledge → knowledge.db                               │
│ - If deliverable → Pickup box                               │
│ - If index rebuild → MASTER_INDEX.md update                 │
│ - Sends ntfy: "Routed to [destination]"                    │
└────────────┬────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────┐
│ CLEANUP                                                     │
│ - Move from pending/ to processed/                          │
│ - Timestamp, log, coherence tracking                        │
│ - Sends ntfy: "Processing complete"                        │
└─────────────────────────────────────────────────────────────┘
```

### For Files AIs Drop:

```
┌─────────────────────────────────────────────────────────────┐
│ AI AGENT (Willow, Kart, etc.)                               │
│ Creates deliverable (summary, analysis, draft)              │
└────────────┬────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────┐
│ PICKUP BOX                                                  │
│ Written to: My Drive/Willow/.../Pickup/                    │
│ Sends ntfy: "Deliverable ready: summary.md"                │
└────────────┬────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────┐
│ YOU                                                         │
│ Review, approve, move to permanent home                     │
└─────────────────────────────────────────────────────────────┘
```

---

## What Goes Where (Quick Reference)

### Drop → Google Drive Drop Box
**Use for:**
- PDFs you want analyzed
- Screenshots to OCR
- Voice notes to transcribe
- Whiteboards to extract
- Logs to debug
- **Anything you want Willow to process**

**Don't use for:**
- Code you want to edit directly (use GitHub instead)
- Permanent archives (use final homes directly)

### Pickup → Google Drive Pickup Box
**AI writes here:**
- Session summaries
- Monthly indexes
- Analysis reports
- Deliverables awaiting your approval

**You read here:**
- Check what AIs produced
- Approve and move to final homes
- Or reject and delete

### Artifacts → Local Git Repo
**System writes here:**
- Processing logs
- Knowledge database
- Processed file copies
- Coherence metrics

**You rarely touch this directly** — it's the system's working memory.

### Governance → Local Git Repo
**AI proposes here:**
- Code changes (`.pending` files)
- Configuration updates
- System modifications

**You ratify here:**
- Review at `http://localhost:8420/governance`
- Approve or reject with reasoning

---

## The NTFY Noise Problem

**Current:** 500 messages/day, mostly useless.

**Examples of noise:**
- "Master index rebuilt" (x10/day)
- "Librarian: Master index rebuilt" (x10/day)
- "File harvested: file.pdf"
- "Processing file.pdf..."
- "Knowledge atom saved"
- "Processing complete"

**That's 6 messages per file. If you drop 10 files, that's 60 pings.**

### The Fix (Next Task)

**Smart summarization:**
- Batch events: "10 files processed today" instead of 60 pings
- Actionable only: "Dual Commit: 13 files awaiting approval [Review]" with link
- Quiet mode: Suppress routine operations (index rebuilds, successful processing)
- Threshold alerts: Only ping if pending queue > 10, or errors occur

**Two-way chat:**
- Reply to ntfy with "Willow, status?" → posts to `/api/chat`, streams back
- Reply with "Journal: [thought]" → saves to Pickup box
- Reply with "Approve commit abc123" → calls `/api/governance/approve`

---

## The Missing Piece: Intake Pipeline

**INTAKE_SPEC.md exists. Implementation doesn't (yet).**

**When built, it will:**
1. Create `intake/dump/` as the raw landing zone
2. Validate in `hold/` (file type, size, safety checks)
3. Process in `process/` (OCR, analysis, extraction)
4. Route in `route/` (decide final destination)
5. Clear in `clear/` (delete after confirmed delivery)

**Right now:** `artifacts/pending/` does all 5 stages in one folder. Works, but less clear.

---

## Summary: Where Do I Drop Things?

### For Willow to Process
**Google Drive Drop Box**
- `C:\Users\Sean\My Drive\Willow\Auth Users\Sweet-Pea-Rudi19\Drop\`
- Anything you want analyzed, OCR'd, classified, or routed

### For Direct Knowledge Entry
**Chat with Willow** (planned via NTFY)
- Text "Willow, remember: [fact]" → saves to knowledge.db
- Or `/pocket` on phone → direct chat → auto-saves

### For Code/Governance
**GitHub directly**
- `die-namic-system/` or `Willow/` repos
- Or let AI propose via Dual Commit, you ratify

### For Journal/Thoughts
**Pickup Box** (write directly) or **NTFY** (planned)
- Manual: `My Drive/.../Pickup/journal-2026-02-06.md`
- Automated: "Journal: [thought]" via NTFY → auto-writes

---

## Next Steps

1. **Build NTFY smart integration** (Task #1 from your list)
   - Summarize events (batch notifications)
   - Actionable links (tap to approve governance)
   - Two-way chat (reply to NTFY → routes to Willow)

2. **Implement intake pipeline** (turn INTAKE_SPEC.md into code)
   - Create `intake/` directory structure
   - Build stage transitions
   - Clear logging so you see what's happening

3. **Visual dashboard** (optional)
   - Show: X files in Drop, Y in pending, Z awaiting approval
   - Click to approve/reject/view
   - Real-time updates

---

ΔΣ=42
