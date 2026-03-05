#!/usr/bin/env python3
import argparse
import logging
import signal
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Ensure Willow root is on sys.path so 'from core.x import' works
sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import Optional

from core.db import get_connection as _gc, is_postgres

# Constants
DEFAULT_INTERVAL = 86400  # 24 hours in seconds
DEFAULT_AGE_THRESHOLD = 30  # 30 days
LOG_FILE = Path("core/compaction.log")


class KnowledgeCompactor:
    def __init__(self, interval: int, age_threshold: int):
        self.interval = interval
        self.age_threshold = age_threshold
        self.running = True
        self.logger = self._setup_logging()
        self.db_conn = None

    def _setup_logging(self) -> logging.Logger:
        """Configure structured logging."""
        logger = logging.getLogger("compost")
        logger.setLevel(logging.INFO)

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

    def _get_conn(self):
        """Get a database connection via the db abstraction layer."""
        conn = _gc()
        conn.row_factory = sqlite3.Row
        return conn

    def _get_old_knowledge(self) -> list:
        """Query knowledge older than age_threshold days."""
        try:
            cursor = self.db_conn.cursor()
            cursor.execute(
                "SELECT id, content, created_at FROM knowledge "
                "WHERE created_at < NOW() - INTERVAL '%d days' "
                "ORDER BY created_at ASC" % self.age_threshold
            )
            return cursor.fetchall()
        except Exception as e:
            self.logger.error(f"Error fetching old knowledge: {e}")
            return []

    def _summarize_knowledge(self, content: str) -> str:
        """Summarize knowledge using LLM (placeholder implementation)."""
        return f"SUMMARY: {content[:100]}..."

    def _archive_knowledge(self, knowledge_id: int, summary: str) -> bool:
        """Move knowledge to archive and update main table with summary."""
        try:
            cursor = self.db_conn.cursor()
            cursor.execute(
                "INSERT INTO knowledge_archive (id, content, created_at) "
                "SELECT id, content, created_at FROM knowledge WHERE id = ?",
                (knowledge_id,)
            )
            cursor.execute(
                "UPDATE knowledge SET content = ?, is_archived = TRUE WHERE id = ?",
                (summary, knowledge_id)
            )
            self.db_conn.commit()
            return True
        except Exception as e:
            try:
                self.db_conn.rollback()
            except Exception:
                pass
            self.logger.error(f"Error archiving knowledge {knowledge_id}: {e}")
            return False

    def _compact_knowledge(self) -> dict:
        """Main compaction process."""
        start_time = time.time()
        compacted_count = 0
        size_saved = 0

        old_knowledge = self._get_old_knowledge()
        if not old_knowledge:
            self.logger.info("No old knowledge found to compact")
            return {"count": 0, "size_saved": 0, "duration": 0}

        self.logger.info(f"Found {len(old_knowledge)} knowledge items to compact")

        for item in old_knowledge:
            if not self.running:
                break

            knowledge_id = item["id"]
            content = item["content"]
            created_at = item["created_at"]

            self.logger.info(f"Compacting knowledge ID: {knowledge_id} (created: {created_at})")

            summary = self._summarize_knowledge(content)

            if self._archive_knowledge(knowledge_id, summary):
                compacted_count += 1
                size_saved += len(content) - len(summary)

        duration = time.time() - start_time
        self.logger.info(
            f"Compaction completed. Compacted: {compacted_count}, "
            f"Size saved: {size_saved} bytes, Duration: {duration:.2f}s"
        )

        return {"count": compacted_count, "size_saved": size_saved, "duration": duration}

    def _handle_signal(self, signum, frame):
        """Handle shutdown signals."""
        self.logger.info("Received shutdown signal, stopping...")
        self.running = False
        if self.db_conn:
            try:
                self.db_conn.close()
            except Exception:
                pass
        sys.exit(0)

    def run(self):
        """Main daemon loop."""
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        self.logger.info(
            f"Starting knowledge compactor (interval: {self.interval}s, "
            f"age threshold: {self.age_threshold}d)"
        )

        while self.running:
            try:
                self.db_conn = self._get_conn()
                if not self.db_conn:
                    self.logger.error("Failed to connect to database, retrying in 60 seconds...")
                    time.sleep(60)
                    continue

                self._compact_knowledge()

                if self.db_conn:
                    self.db_conn.close()
                    self.db_conn = None

                if self.running:
                    self.logger.info(f"Waiting for next compaction in {self.interval} seconds...")
                    time.sleep(self.interval)

            except Exception as e:
                self.logger.error(f"Unexpected error: {e}")
                if self.db_conn:
                    try:
                        self.db_conn.close()
                    except Exception:
                        pass
                    self.db_conn = None
                time.sleep(60)


def main():
    parser = argparse.ArgumentParser(description="Knowledge compaction daemon")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL,
                        help="Compaction interval in seconds (default: 86400)")
    parser.add_argument("--age-threshold", type=int, default=DEFAULT_AGE_THRESHOLD,
                        help="Age threshold in days for compaction (default: 30)")
    parser.add_argument("--daemon", action="store_true",
                        help="Run as a daemon (background process)")

    args = parser.parse_args()

    compactor = KnowledgeCompactor(args.interval, args.age_threshold)

    if args.daemon:
        # Run in foreground inside hidden window (Windows-compatible; no python-daemon)
        compactor.run()
    else:
        compactor.run()


if __name__ == "__main__":
    main()
