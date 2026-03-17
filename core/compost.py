#!/usr/bin/env python3
"""
Knowledge Compactor — Compost Daemon

Governance-compliant: proposes compaction, does NOT execute without approval.
Original content is NEVER deleted automatically.

Flow:
  1. Query knowledge older than age_threshold days without summaries
  2. Generate summary via fleet (best-effort)
  3. Write summary to the summary column (additive — content_snippet is NEVER touched)
  4. Log what was compacted for audit

What this daemon does NOT do:
  - Delete content_snippet (irreversible — forbidden without approval)
  - Modify any field other than summary (where summary IS NULL)
  - Run without logging every change

ΔΣ=42
"""
import argparse
import logging
import signal
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.db import get_connection as _gc

DEFAULT_INTERVAL = 86400  # 24 hours
DEFAULT_AGE_THRESHOLD = 30  # 30 days
MAX_BATCH = 50  # max items per cycle to avoid fleet overload
LOG_FILE = Path("core/compaction.log")


class KnowledgeCompactor:
    def __init__(self, interval: int, age_threshold: int):
        self.interval = interval
        self.age_threshold = age_threshold
        self.running = True
        self.logger = self._setup_logging()

    def _setup_logging(self) -> logging.Logger:
        logger = logging.getLogger("compost")
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            file_handler = logging.FileHandler(LOG_FILE)
            file_handler.setFormatter(logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            ))
            logger.addHandler(file_handler)
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            ))
            logger.addHandler(console_handler)
        return logger

    def _get_unsummarized_old_knowledge(self) -> list:
        """Query knowledge older than threshold that has no summary yet."""
        conn = _gc()
        try:
            cutoff = (datetime.now() - timedelta(days=self.age_threshold)).strftime('%Y-%m-%d %H:%M:%S')
            rows = conn.execute(
                """SELECT id, title, content_snippet, created_at
                   FROM knowledge
                   WHERE created_at < ?
                     AND summary IS NULL
                     AND content_snippet IS NOT NULL
                     AND LENGTH(content_snippet) > 50
                   ORDER BY created_at ASC
                   LIMIT ?""",
                (cutoff, MAX_BATCH)
            ).fetchall()
            return rows
        except Exception as e:
            self.logger.error(f"Error fetching old knowledge: {e}")
            return []
        finally:
            conn.close()

    def _generate_summary(self, content: str, title: str = "") -> str:
        """Generate summary via free fleet. Returns None if fleet unavailable."""
        try:
            from core import llm_router
            llm_router.load_keys_from_json()
            prompt = f"Summarize this knowledge entry in 2-3 sentences. Be factual and concise.\n\nTitle: {title}\n\nContent:\n{content[:2000]}"
            response = llm_router.ask(prompt, preferred_tier="free", task_type="text_summarization")
            if response and response.content:
                return response.content.strip()[:500]
        except Exception as e:
            self.logger.warning(f"Fleet summary failed: {e}")
        return None

    def _write_summary(self, knowledge_id: int, summary: str) -> bool:
        """Write summary to knowledge row. ADDITIVE ONLY — never touches content_snippet."""
        conn = _gc()
        try:
            conn.execute(
                "UPDATE knowledge SET summary = ? WHERE id = ? AND summary IS NULL",
                (summary, knowledge_id)
            )
            conn.commit()
            return True
        except Exception as e:
            self.logger.error(f"Error writing summary for {knowledge_id}: {e}")
            return False
        finally:
            conn.close()

    def _compact_cycle(self) -> dict:
        """One compaction cycle: find unsummarized old knowledge, generate summaries."""
        start_time = time.time()
        summarized = 0

        rows = self._get_unsummarized_old_knowledge()
        if not rows:
            self.logger.info("No unsummarized old knowledge found")
            return {"summarized": 0, "duration": 0}

        self.logger.info(f"Found {len(rows)} items needing summaries")

        for row in rows:
            if not self.running:
                break

            kid = row[0]
            title = row[1] or ""
            content = row[2] or ""

            summary = self._generate_summary(content, title)
            if summary and self._write_summary(kid, summary):
                summarized += 1
                self.logger.info(f"COMPOST: summarized #{kid} ({len(content)}c → {len(summary)}c)")

        duration = time.time() - start_time
        self.logger.info(f"Cycle complete: {summarized} summarized in {duration:.1f}s")
        return {"summarized": summarized, "duration": duration}

    def _handle_signal(self, signum, frame):
        self.logger.info("Received shutdown signal, stopping...")
        self.running = False
        sys.exit(0)

    def run(self):
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
        self.logger.info(
            f"Starting knowledge compactor (interval: {self.interval}s, "
            f"age threshold: {self.age_threshold}d, additive-only mode)"
        )
        while self.running:
            try:
                self._compact_cycle()
                if self.running:
                    self.logger.info(f"Next cycle in {self.interval}s...")
                    time.sleep(self.interval)
            except Exception as e:
                self.logger.error(f"Unexpected error: {e}")
                time.sleep(60)


def main():
    parser = argparse.ArgumentParser(description="Knowledge compaction daemon (additive-only)")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL)
    parser.add_argument("--age-threshold", type=int, default=DEFAULT_AGE_THRESHOLD)
    parser.add_argument("--daemon", action="store_true")
    args = parser.parse_args()
    compactor = KnowledgeCompactor(args.interval, args.age_threshold)
    compactor.run()


if __name__ == "__main__":
    main()
