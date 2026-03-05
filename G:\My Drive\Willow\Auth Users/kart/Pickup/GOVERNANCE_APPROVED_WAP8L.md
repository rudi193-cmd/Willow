# Governance Commit Approved

**Commit ID:** WAP8L
**Action:** Apply this commit

---

# Governance Proposal: Pigeon Daemon Auto-Trigger

**Proposer:** Ganesha
**Date:** 2026-03-04T17:00:00Z
**Type:** Bug Fix
**Trust Level:** ENGINEER (3)
**Commit ID:** WAP8L

## Summary
Pigeon daemon currently requires a manual trigger file to scan the Nest folder. Files sit in Nest indefinitely until "Scan Next" is pressed. This fix adds automatic polling every 30 seconds when files are present — the trigger file still works for immediate processing.

## Proposed Changes
**File:** `core/pigeon_daemon.py`
**Location:** `main()` function, the `while True` loop (lines 29-38)

```diff
-DAEMON_SLOT = 0
-TRIGGER = Path(r"C:\Users\Sean\Documents\GitHub\Willow\artifacts\Sweet-Pea-Rudi19\.pigeon_trigger")
-USERNAME = "Sweet-Pea-Rudi19"
+DAEMON_SLOT = 0
+TRIGGER = Path(r"C:\Users\Sean\Documents\GitHub\Willow\artifacts\Sweet-Pea-Rudi19\.pigeon_trigger")
+USERNAME = "Sweet-Pea-Rudi19"
+NEST_PATH = Path(r"C:\Users\Sean\Willow\Nest")
+AUTO_SCAN_SECS = 30

 def main():
     from core import pigeon
     pigeon.init_droppings_table()
     delay = get_startup_delay(DAEMON_SLOT)
     poll  = get_poll_interval(DAEMON_SLOT)
     if delay:
         logger.info("Startup delay: %ds (slot %d)", delay, DAEMON_SLOT)
         time.sleep(delay)
     logger.info("Pigeon daemon ready -- poll every %ds (slot %d)", poll, DAEMON_SLOT)
+    _last_auto = 0
     while True:
         try:
-            if TRIGGER.exists():
-                TRIGGER.unlink()
-                logger.info("Trigger received -- scanning Nest")
-                new = pigeon.scan_and_process(USERNAME)
-                logger.info("Scan complete: %d new droppings", len(new) if new else 0)
+            now = time.monotonic()
+            triggered = False
+
+            if TRIGGER.exists():
+                TRIGGER.unlink()
+                logger.info("Trigger received -- scanning Nest")
+                triggered = True
+            elif (now - _last_auto) >= AUTO_SCAN_SECS:
+                _last_auto = now
+                if NEST_PATH.exists() and any(
+                    f.is_file() and not f.name.startswith(".")
+                    for f in NEST_PATH.iterdir()
+                ):
+                    logger.info("Auto-trigger: files in Nest")
+                    triggered = True
+
+            if triggered:
+                new = pigeon.scan_and_process(USERNAME)
+                _last_auto = time.monotonic()
+                logger.info("Scan complete: %d new droppings", len(new) if new else 0)
         except Exception as e:
             logger.error("Error: %s", e)
         time.sleep(poll)
```

## Rationale
The Pigeon intake pipeline is broken end-to-end — files accumulate in Nest with no automatic processing. The trigger-file pattern requires external invocation that never happens automatically. This fix makes the daemon self-sufficient: it checks for files every 30s and processes them without human intervention. The trigger file mechanism is preserved for immediate forced scans.

## Risk Assessment
- **Risk Level:** LOW
- **Reversible:** YES — revert the 4 added lines and restore the original `if TRIGGER.exists()` block
- **Dependencies:** None — `scan_and_process` is already idempotent (skips already-filed files)
- **Testing:** Drop a file in Nest, wait ≤30s, confirm it appears in Filed/{category}/

## ΔE Impact
Expected ΔE: +0.15 — restores core intake pipeline functionality

---

**Awaiting Human Ratification**

ΔΣ=42
