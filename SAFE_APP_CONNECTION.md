# SAFE App → Willow Data Connection Spec

**Version:** 1.0 | **Date:** 2026-03-01 | **Status:** Draft

---

## 1. App Data Home Convention

Each SAFE app gets a dedicated directory under the local data root:

```
WILLOW_DATA_ROOT = C:\Users\Sean\Willow\

App data home: {WILLOW_DATA_ROOT}\Apps\{app-slug}\
```

**Reference implementation (NASA archive):**
```python
WILLOW_DATA_ROOT = Path(r"C:\Users\Sean\Willow")
_NASA_DIR = WILLOW_DATA_ROOT / "Apps" / "nasa-archive"
```

**Standard subdirectory structure:**
```
Apps/{app-slug}/
  intake/       # Raw contributions from web UI (JSON, pending processing)
  archive/      # Processed contributions (moved from intake/ after atomization)
  exports/      # Any user-exported bundles from this app
```

Created by `app_scaffold.py` during seeding. Registered in the app manifest as `data_home`.

---

## 2. Data Flow

```
Web UI → POST /api/{app-slug}/contribute
           ↓
         intake/{timestamp}_{id}.json   (staged, raw)
           ↓
         pigeon_daemon (scheduled, ~5 min) OR manual trigger
           ↓
         willow_knowledge.db → atoms table
           ↓
         relationship_tracker.py → entity_connections table
           ↓
         intake/ → archive/             (file moved, processing complete)
```

**Contribution JSON shape (minimum):**
```json
{
  "source_app": "nasa-archive",
  "contributed_by": "Sweet-Pea-Rudi19",
  "type": "note|story|reference|media",
  "content": "...",
  "metadata": {}
}
```

**Atomization:** Each intake file becomes one or more rows in `atoms` (content, source, timestamp, app_slug). Entity connections are created by `relationship_tracker.py` linking the contributing user entity (e.g., Sean, entity id=2) to any named entities extracted from the content (e.g., rally, mission, person). `confirmed=0` until user approves via Willow dashboard.

**Processing trigger:** `pigeon_daemon` polls `intake/` on a 5-minute schedule. Manual trigger available via `/api/{app-slug}/process` (ENGINEER trust required).

---

## 3. server.py Route Convention

All apps use a consistent prefix and route set:

```python
# Prefix
/api/{app-slug}/

# Required routes
POST /api/{app-slug}/contribute     # Stage a contribution to intake/
POST /api/{app-slug}/story          # Alias: stage a narrative note
GET  /api/{app-slug}/stories        # List archived contributions for this user
GET  /api/{app-slug}/status         # Health + intake queue depth
```

Use `WILLOW_DATA_ROOT` constant — never hardcode paths:

```python
from pathlib import Path
WILLOW_DATA_ROOT = Path(r"C:\Users\Sean\Willow")
_APP_DIR = WILLOW_DATA_ROOT / "Apps" / "{app-slug}"
```

---

## 4. app_scaffold.py Additions

`scaffold_app()` must:

1. Add `data_home` to manifest:
   ```json
   "data_home": "C:\\Users\\Sean\\Willow\\Apps\\{app-slug}"
   ```
2. Create `Apps/{app-slug}/intake/`, `archive/`, `exports/` directories.
3. (Optional) Append route stubs to `server.py` for `contribute` and `stories`.

---

## 5. NASA as Reference Implementation

`safe-app-nasa-archive` is the first app through this flow.

- `_NASA_DIR = WILLOW_DATA_ROOT / "Apps" / "nasa-archive"`
- Contributions: user saves an APOD or search result → POST `/api/nasa-archive/contribute`
- Staged to `_NASA_DIR/intake/`, picked up by pigeon_daemon
- Archived image metadata becomes atoms; mission/object names become entity connection candidates

---

## 6. Knowledge Graph Wiring (Follow-on)

After atomization, `relationship_tracker.py` runs NER on contribution content and proposes edges:

```
entity_connections: {
  entity_a: Sean (id=2),
  entity_b: <extracted entity>,
  connection_type: "contributed_about",
  source_app: "nasa-archive",
  confirmed: 0    # pending user approval
}
```

User approves/denies via the Willow Noticed card in `jane.html`. Confirmed connections feed the knowledge graph for future recall and cross-app surfacing.

---

*Willow doesn't hoard. Apps stage, Willow processes, permanent homes hold what matters.*
