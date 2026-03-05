# Governance Commit Approved

**Commit ID:** UUHXH
**Action:** Apply this commit

---

# Governance Proposal: WSL Path Resolution for Pigeon + Pigeon Daemon

**Proposer:** Ganesha
**Date:** 2026-03-04T17:30:00Z
**Type:** Bug Fix
**Trust Level:** ENGINEER (3)
**Commit ID:** UUHXH

## Summary
All hardcoded Windows-style paths in `core/pigeon.py` and `core/pigeon_daemon.py` fail silently when the server runs in WSL/Linux. `NEST_PATH.exists()` returns False, so the auto-trigger never fires and `scan_and_process` looks at the wrong directory. Fix: detect platform at runtime and use `/mnt/c/...` paths on Linux.

## Proposed Changes

**File:** `core/pigeon.py`
Replace the hardcoded Windows path constants with a platform-aware resolver:

```diff
-DB_PATH = r"C:\\Users\\Sean\\Documents\\GitHub\\Willow\\artifacts\\Sweet-Pea-Rudi19\\willow_knowledge.db"
-
-NEST_PATHS = {
-    "Sweet-Pea-Rudi19": r"C:\\Users\\Sean\\Willow\\Nest",
-}
-NEST_BASE = r"C:\\Users\\Sean\\Willow\\Nest"
-FILED_BASE = {
-    "Sweet-Pea-Rudi19": r"C:\\Users\\Sean\\Willow\\Filed",
-}
+import sys as _sys
+_WIN = _sys.platform == "win32"
+_BASE = r"C:\Users\Sean" if _WIN else "/mnt/c/Users/Sean"
+_WILLOW_REPO = (r"C:\Users\Sean\Documents\GitHub\Willow" if _WIN
+                else "/mnt/c/Users/Sean/Documents/GitHub/Willow")
+
+DB_PATH = _WILLOW_REPO + ("/artifacts/Sweet-Pea-Rudi19/willow_knowledge.db"
+                          if not _WIN else r"\artifacts\Sweet-Pea-Rudi19\willow_knowledge.db")
+
+NEST_PATHS = {
+    "Sweet-Pea-Rudi19": _BASE + ("/Willow/Nest" if not _WIN else r"\Willow\Nest"),
+}
+NEST_BASE = _BASE + ("/Willow/Nest" if not _WIN else r"\Willow\Nest")
+FILED_BASE = {
+    "Sweet-Pea-Rudi19": _BASE + ("/Willow/Filed" if not _WIN else r"\Willow\Filed"),
+}
```

Also fix the `get_nest_path` fallback and `route_file` fallback to use `_BASE`.

Also fix the `classify_file` sys.path.insert to use `_WILLOW_REPO`.

**File:** `core/pigeon_daemon.py`
Same platform-aware fix for TRIGGER and NEST_PATH:

```diff
-TRIGGER = Path(r"C:\Users\Sean\Documents\GitHub\Willow\artifacts\Sweet-Pea-Rudi19\.pigeon_trigger")
-NEST_PATH = Path(r"C:\Users\Sean\Willow\Nest")
+import sys as _sys
+_WIN = _sys.platform == "win32"
+_BASE = r"C:\Users\Sean" if _WIN else "/mnt/c/Users/Sean"
+_REPO = (r"C:\Users\Sean\Documents\GitHub\Willow" if _WIN
+         else "/mnt/c/Users/Sean/Documents/GitHub/Willow")
+TRIGGER = Path(_REPO + (r"\artifacts\Sweet-Pea-Rudi19\.pigeon_trigger" if _WIN
+                        else "/artifacts/Sweet-Pea-Rudi19/.pigeon_trigger"))
+NEST_PATH = Path(_BASE + (r"\Willow\Nest" if _WIN else "/Willow/Nest"))
```

## Rationale
Server migrated from Windows to WSL/Linux. All Pigeon paths assumed Windows. On Linux, `Path(r"C:\...")` silently returns a non-existent path, so scan_and_process scans nothing and files sit in Nest forever. One runtime platform check fixes all of it.

## Risk Assessment
- **Risk Level:** LOW
- **Reversible:** YES
- **Dependencies:** None — purely path string changes, no logic changes
- **Testing:** Drop file in Nest, confirm it moves to Filed/{category}/ within 30s

---

**Awaiting Human Ratification**

ΔΣ=42
