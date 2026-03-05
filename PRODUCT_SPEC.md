# Willow — Product Specification

| Field | Value |
|-------|-------|
| Owner | Sean Campbell |
| System | Aionic / Die-namic |
| Version | 0.1 |
| Status | Draft |
| Last Updated | 2026-01-11 |
| Checksum | ΔΣ=42 |

---

## One Line

Dump your heart out. It'll make sense eventually.

---

## The Problem

You have thoughts at 3am. Screenshots you'll forget. Voice notes in the car. Photos of whiteboards. Links saved with no context. Half-ideas across twelve apps.

Current solutions demand structure at the moment of capture. They require you to:
- Choose the right app
- File in the right folder
- Tag correctly
- Write coherent notes

But capture happens when you're messy. Structure happens later. Or never.

---

## The Solution

Willow is a single intake point. One place to dump everything.

**You dump.** Any format. Any time. No organization required.

**Willow holds.** Nothing lost. Everything timestamped. No judgment.

**Willow processes.** Patterns emerge. Connections surface. AI finds the structure you couldn't see in the moment.

**Willow routes.** Things go where they belong. Your notes app. Your calendar. Your project folders. Your reminders.

**Willow clears.** Processed items leave. Willow doesn't hoard. Your destinations hold what matters.

---

## The 4% Rule

**Maximum 4% cloud. 96% client.**

| Component | Location | Allocation |
|-----------|----------|------------|
| Auth (if needed) | Cloud | ~1% |
| Model inference (fallback) | Cloud | ~2% |
| Sync coordination | Cloud | ~1% |
| **Everything else** | Client | **96%** |

### What this means

**On device:**
- All raw intake storage
- Local AI processing (TensorFlow.js, on-device models)
- Pattern detection
- Routing logic
- Export/integration

**Optional cloud:**
- Cross-device sync (encrypted, user-controlled)
- Heavier model inference (BYOK only)

**We never see:**
- Your dumps
- Your patterns
- Your routes
- Your life

---

## Core Interactions

### 1. Dump

```
Any input → Willow
```

- Text (typed, pasted, voice-to-text)
- Images (screenshots, photos, saved)
- Links (URLs, with auto-preview)
- Files (PDFs, docs, whatever)
- Audio (voice notes, kept or transcribed)

No friction. No "what folder?" No "what tags?" Just dump.

### 2. Hold

Everything lands in the **Inbox**. Timestamped. Held until processed.

Inbox is:
- Chronological (default)
- Searchable (full-text + image content)
- Temporary (clears after routing)

### 3. Process

Processing happens:
- Automatically (background, when idle)
- On-demand (user triggers)
- Eventually (no rush)

Processing detects:
- **Type**: Task? Note? Event? Reference? Junk?
- **Entities**: People, places, dates, projects
- **Connections**: Links to existing items
- **Patterns**: "You've saved 47 kitchen photos this year"

### 4. Route

User defines destinations. Willow suggests routes.

| Detected | Suggested Route |
|----------|-----------------|
| Task with date | Calendar / Reminders |
| Person mentioned | Contacts / CRM |
| Project keyword | Project folder |
| Image cluster | Vision board / Album |
| Reference material | Notes / Archive |
| Junk | Delete |

User can:
- Accept suggestion (one tap)
- Override (pick different destination)
- Create rule ("always route X to Y")
- Ignore (stays in inbox)

### 5. Clear

Routed items leave inbox. Inbox tends toward empty.

Cleared ≠ Deleted. Items live in their destinations. Willow just doesn't hold them anymore.

---

## The Insight Layer

Willow sees what you're collecting. Surfaces patterns you missed.

**Anonymous (passive):**
> "147 items captured in December"

**Pseudonymous (detected):**
> "You keep saving mid-century furniture. And beach sunsets. And this one shade of yellow."

**Named (user-ratified):**
> "Dream Kitchen" board created. "2026 Travel" project linked.

Same three-layer model as Vision Board. Willow observes. You decide what matters.

---

## Privacy Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     YOUR DEVICE (96%)                       │
│                                                             │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│   │   Intake    │  │  Processing │  │   Routing   │        │
│   │   (dump)    │→ │  (AI local) │→ │ (your apps) │        │
│   └─────────────┘  └─────────────┘  └─────────────┘        │
│                                                             │
│   ┌─────────────────────────────────────────────┐          │
│   │              Local Storage                   │          │
│   │  IndexedDB / SQLite / Filesystem            │          │
│   └─────────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ Optional, encrypted, user-controlled
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     CLOUD (4% max)                          │
│                                                             │
│   ┌─────────────┐  ┌─────────────┐                         │
│   │  Auth       │  │  Sync       │                         │
│   │  (stateless)│  │  (E2E enc)  │                         │
│   └─────────────┘  └─────────────┘                         │
└─────────────────────────────────────────────────────────────┘
```

**Your data never touches our servers unencrypted. Period.**

---

## Integrations

Willow routes to your existing tools. Doesn't replace them.

| Category | Examples |
|----------|----------|
| Tasks | Apple Reminders, Todoist, Things, Notion |
| Calendar | Google Calendar, Apple Calendar, Outlook |
| Notes | Apple Notes, Obsidian, Notion, Roam |
| Files | Local folders, iCloud, Google Drive, Dropbox |
| Custom | API webhooks, Shortcuts, Zapier |

Willow is the intake. Your tools are the destinations.

---

## Pricing

| Tier | Price | Features |
|------|-------|----------|
| **Free** | $0 | Local processing, 1 device, basic routing |
| **Pro** | $X/year (one-time?) | Multi-device sync, advanced AI, custom integrations |
| **BYOK** | $0 | Bring your own API keys for heavier models |

No subscriptions for core features. No metered usage. You own your data and your access.

---

## Platform Strategy

```
Phase 1: iOS app (primary capture device is phone)
Phase 2: macOS companion (desktop processing power)
Phase 3: Web app (PWA, access anywhere)
Phase 4: Android (if demand)
```

Phone is the capture device. People dump from their pocket.

---

## Technical Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| Mobile | Swift/SwiftUI (iOS) | Native performance, system integrations |
| AI | Core ML + on-device models | Privacy, speed, offline |
| Storage | SQLite + file system | Reliable, portable, no vendor lock |
| Sync | CloudKit (optional) | Apple ecosystem, E2E encryption |
| Desktop | Swift (macOS) | Shared codebase |
| Web | PWA, TensorFlow.js | Fallback, cross-platform |

---

## MVP Scope

### Phase 1A — Capture
- [ ] Single intake point (text, image, link)
- [ ] Inbox view (chronological)
- [ ] Local storage
- [ ] Basic search

### Phase 1B — Process
- [ ] On-device classification (note/task/event/reference)
- [ ] Entity extraction (dates, people, places)
- [ ] Pattern detection (image clusters, keyword frequency)

### Phase 1C — Route
- [ ] Destination configuration
- [ ] Suggested routing (accept/override)
- [ ] Apple Reminders integration
- [ ] Apple Notes integration
- [ ] Files/folders integration

### Phase 1D — Clear
- [ ] Inbox clearing after route
- [ ] Archive for unrouted items
- [ ] "Junk" detection and auto-clear

---

## What Willow Is Not

- **Not a notes app.** It routes to your notes app.
- **Not a task manager.** It routes to your task manager.
- **Not a second brain.** It's the intake before the brain.
- **Not a replacement.** It's the front door to everything else.

---

## The Philosophy

Structure is a tax on capture. The moment you have to think "where does this go?" — you've lost momentum.

Willow removes the tax. Dump now. Structure later. Or never.

Trust the system to make sense of the mess. Eventually.

---

## Open Questions

1. **Voice-first?** Should primary input be voice with text as fallback?
2. **Share sheet integration?** iOS share sheet as primary capture mechanism?
3. **Widget?** Home screen widget for instant dump?
4. **Watch app?** Wrist capture for truly frictionless input?
5. **Collaboration?** Multi-user dumps? Shared inboxes? (Probably not — personal assistant, not team tool)

---

ΔΣ=42
