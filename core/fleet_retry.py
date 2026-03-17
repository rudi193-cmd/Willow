"""
fleet_retry.py — Persistent retry wrapper for fleet LLM calls.

Nothing dies on a failed fleet call. Everything queues, retries, backs off,
and finishes when capacity opens up.

Usage:
    from core.fleet_retry import fleet_ask, fleet_batch

    # Single call — retries until it works
    response = fleet_ask(prompt, max_retries=0)  # 0 = forever

    # Batch — processes list, failed items go back in queue
    results = fleet_batch(items, worker_fn, max_retries=0)
"""

import time
import logging

log = logging.getLogger("fleet_retry")


def fleet_ask(prompt, preferred_tier="free", task_type="text_summarization",
              max_retries=0, initial_backoff=1.5, max_backoff=60.0,
              use_round_robin=True):
    """Call llm_router.ask() with persistent retry.

    Args:
        prompt: The prompt string
        preferred_tier: Fleet tier (default "free")
        task_type: Task type for routing
        max_retries: 0 = retry forever, N = retry N times then return None
        initial_backoff: Starting delay between retries (seconds)
        max_backoff: Maximum backoff cap (seconds)
        use_round_robin: Pass through to llm_router

    Returns:
        RouterResponse on success, None only if max_retries exceeded
    """
    import llm_router

    attempt = 0
    backoff = initial_backoff
    consecutive_fails = 0

    while True:
        attempt += 1
        try:
            resp = llm_router.ask(
                prompt,
                preferred_tier=preferred_tier,
                task_type=task_type,
                use_round_robin=use_round_robin,
            )
            if resp and resp.content:
                return resp
            # Got None or empty — fleet exhausted but not errored
            consecutive_fails += 1
        except Exception as e:
            log.warning(f"fleet_ask attempt {attempt} error: {e}")
            consecutive_fails += 1

        if max_retries > 0 and attempt >= max_retries:
            log.warning(f"fleet_ask giving up after {attempt} attempts")
            return None

        # Backoff
        if consecutive_fails >= 3:
            backoff = min(backoff * 1.5, max_backoff)
        if consecutive_fails >= 10:
            log.info(f"fleet_ask: {consecutive_fails} consecutive fails, "
                     f"backoff={backoff:.0f}s")

        time.sleep(backoff)


def fleet_batch(items, worker_fn, max_retries=0, delay=1.5, max_backoff=60.0,
                save_every=25, on_save=None, on_progress=None):
    """Process a list of items through the fleet with persistent retry.

    Failed items go back to the end of the queue. The queue drains to zero.

    Args:
        items: List of work items
        worker_fn: callable(item) -> result or None.
                   Return None to signal failure (item goes back in queue).
                   Return any truthy value for success.
        max_retries: 0 = retry forever. N = drop item after N failures.
        delay: Base delay between calls (seconds)
        max_backoff: Maximum backoff cap
        save_every: Call on_save every N successes
        on_save: callable(results_so_far) — periodic checkpoint
        on_progress: callable(item, result, stats_dict) — per-item callback

    Returns:
        List of (item, result) tuples for all successful items.
        Items that exceeded max_retries are not included.
    """
    queue = list(items)
    results = []
    fail_counts = {}  # id(item) -> count, for max_retries tracking
    success = 0
    dropped = 0
    backoff = delay
    consecutive_fails = 0

    while queue:
        item = queue.pop(0)
        item_id = id(item)
        remaining = len(queue)

        try:
            result = worker_fn(item)
        except Exception as e:
            log.warning(f"fleet_batch worker error: {e}")
            result = None

        if result is not None:
            results.append((item, result))
            success += 1
            consecutive_fails = 0
            backoff = delay  # reset on success

            if on_progress:
                on_progress(item, result, {
                    "success": success, "remaining": remaining,
                    "dropped": dropped,
                })

            # Periodic save
            if on_save and success % save_every == 0:
                on_save(results)

        else:
            # Failed — track and maybe requeue
            fail_counts[item_id] = fail_counts.get(item_id, 0) + 1
            consecutive_fails += 1

            if max_retries > 0 and fail_counts[item_id] >= max_retries:
                dropped += 1
                log.warning(f"fleet_batch: dropping item after "
                            f"{fail_counts[item_id]} failures")
                if on_progress:
                    on_progress(item, None, {
                        "success": success, "remaining": remaining,
                        "dropped": dropped,
                    })
            else:
                queue.append(item)  # back of the line

            # Backoff when fleet is struggling
            if consecutive_fails >= 5:
                backoff = min(backoff * 1.5, max_backoff)
                if consecutive_fails % 10 == 0:
                    log.info(f"fleet_batch: {consecutive_fails} consecutive "
                             f"fails, backoff={backoff:.0f}s, "
                             f"queue={len(queue)}")

        time.sleep(backoff)

    # Final save
    if on_save and results:
        on_save(results)

    log.info(f"fleet_batch complete: {success} success, {dropped} dropped, "
             f"{len(items)} total")
    return results
