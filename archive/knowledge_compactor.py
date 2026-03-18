#!/usr/bin/env python3
import argparse
import logging
import signal
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import psycopg2
from psycopg2 import sql
from psycopg2.extras import DictCursor

# Constants
DEFAULT_INTERVAL = 86400  # 24 hours in seconds
DEFAULT_AGE_THRESHOLD = 30  # 30 days
LOG_FILE = Path("core/compaction.log")
DB_CONFIG = {
    "dbname": "willow",
    "user": "willow",
    "password": "willow",
    "host": "localhost",
    "port": "5432"
}

class KnowledgeCompactor:
    def __init__(self, interval: int, age_threshold: int):
        self.interval = interval
        self.age_threshold = age_threshold
        self.running = True
        self.logger = self._setup_logging()
        self.db_conn = None

    def _setup_logging(self) -> logging.Logger:
        """Configure structured logging."""
        logger = logging.getLogger("knowledge_compactor")
        logger.setLevel(logging.INFO)

        # File handler
        file_handler = logging.FileHandler(LOG_FILE)
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        ))
        logger.addHandler(file_handler)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        ))
        logger.addHandler(console_handler)

        return logger

    def _connect_db(self) -> Optional[psycopg2.extensions.connection]:
        """Establish database connection."""
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            conn.autocommit = False
            return conn
        except psycopg2.Error as e:
            self.logger.error(f"Database connection failed: {e}")
            return None

    def _disconnect_db(self):
        """Close database connection if open."""
        if self.db_conn and not self.db_conn.closed:
            self.db_conn.close()

    def _get_old_knowledge(self) -> list:
        """Query knowledge older than age_threshold days."""
        query = sql.SQL("""
            SELECT id, content, created_at
            FROM knowledge
            WHERE created_at < NOW() - INTERVAL '%s days'
            ORDER BY created_at ASC
        """) % sql.Literal(self.age_threshold)

        try:
            with self.db_conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute(query)
                return cursor.fetchall()
        except psycopg2.Error as e:
            self.logger.error(f"Error fetching old knowledge: {e}")
            return []

    def _summarize_knowledge(self, content: str) -> str:
        """Summarize knowledge using LLM (placeholder implementation)."""
        # In a real implementation, this would call an LLM API
        return f"SUMMARY: {content[:100]}..."  # Truncated for demo

    def _archive_knowledge(self, knowledge_id: int, summary: str) -> bool:
        """Move knowledge to archive and update main table with summary."""
        try:
            # Start transaction
            with self.db_conn.cursor() as cursor:
                # Archive the original knowledge
                archive_query = sql.SQL("""
                    INSERT INTO knowledge_archive (id, content, created_at)
                    SELECT id, content, created_at
                    FROM knowledge
                    WHERE id = %s
                """)
                cursor.execute(archive_query, (knowledge_id,))

                # Update main table with summary
                update_query = sql.SQL("""
                    UPDATE knowledge
                    SET content = %s, is_archived = TRUE
                    WHERE id = %s
                """)
                cursor.execute(update_query, (summary, knowledge_id))

                # Commit transaction
                self.db_conn.commit()
                return True
        except psycopg2.Error as e:
            self.db_conn.rollback()
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

            knowledge_id = item['id']
            content = item['content']
            created_at = item['created_at']

            self.logger.info(f"Compacting knowledge ID: {knowledge_id} (created: {created_at})")

            # Summarize the knowledge
            summary = self._summarize_knowledge(content)

            # Archive the knowledge
            if self._archive_knowledge(knowledge_id, summary):
                compacted_count += 1
                size_saved += len(content) - len(summary)

        duration = time.time() - start_time
        self.logger.info(f"Compaction completed. Compacted: {compacted_count}, Size saved: {size_saved} bytes, Duration: {duration:.2f}s")

        return {
            "count": compacted_count,
            "size_saved": size_saved,
            "duration": duration
        }

    def _handle_signal(self, signum, frame):
        """Handle shutdown signals."""
        self.logger.info("Received shutdown signal, stopping...")
        self.running = False
        self._disconnect_db()
        sys.exit(0)

    def run(self):
        """Main daemon loop."""
        # Set up signal handlers
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        self.logger.info(f"Starting knowledge compactor (interval: {self.interval}s, age threshold: {self.age_threshold}d)")

        while self.running:
            try:
                # Connect to database
                self.db_conn = self._connect_db()
                if not self.db_conn:
                    self.logger.error("Failed to connect to database, retrying in 60 seconds...")
                    time.sleep(60)
                    continue

                # Perform compaction
                self._compact_knowledge()

                # Disconnect from database
                self._disconnect_db()

                # Wait for next interval
                if self.running:
                    self.logger.info(f"Waiting for next compaction in {self.interval} seconds...")
                    time.sleep(self.interval)

            except Exception as e:
                self.logger.error(f"Unexpected error: {e}")
                self._disconnect_db()
                time.sleep(60)  # Wait before retrying

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
        # Daemonize the process (simplified)
        import daemon
        from daemon import pidfile

        context = daemon.DaemonContext(
            working_directory=str(Path.cwd()),
            umask=0o002,
            pidfile=pidfile.TimeoutPIDLockFile("/var/run/knowledge_compactor.pid")
        )

        with context:
            compactor.run()
    else:
        compactor.run()

if __name__ == "__main__":
    main()
