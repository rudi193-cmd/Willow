#!/usr/bin/env python3
import argparse
import json
import logging
import signal
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional

class PersonaScheduler:
    def __init__(self, config_path: Path, interval: int = 60):
        self.config_path = config_path
        self.interval = interval
        self.running = False
        self._setup_logging()
        self._load_config()
        self._setup_signal_handlers()

    def _setup_logging(self):
        log_path = Path(__file__).parent / "persona_scheduler.log"
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler(log_path),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger("PersonaScheduler")

    def _load_config(self):
        try:
            with open(self.config_path, 'r') as f:
                self.config = json.load(f)
            self.logger.info(f"Loaded persona config from {self.config_path}")
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            raise

    def _setup_signal_handlers(self):
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

    def _handle_shutdown(self, signum, frame):
        self.logger.info("Shutdown signal received, stopping gracefully...")
        self.running = False

    def _execute_persona(self, persona_name: str, persona_config: Dict[str, Any]) -> bool:
        try:
            self.logger.info(f"Executing persona: {persona_name}")
            # Placeholder for actual persona execution logic
            # In a real implementation, this would call the appropriate persona handler
            output = f"Executed {persona_name} with config: {persona_config}"
            self.logger.info(f"Persona {persona_name} completed successfully")
            return True, output
        except Exception as e:
            self.logger.error(f"Persona {persona_name} failed: {e}")
            return False, str(e)

    def _check_triggers(self) -> Dict[str, Any]:
        # Placeholder for trigger checking logic
        # In a real implementation, this would check for event triggers
        return {"triggered_personas": []}

    def run(self):
        self.running = True
        self.logger.info(f"Starting persona scheduler with interval {self.interval} seconds")

        while self.running:
            try:
                start_time = time.time()

                # Check for triggered personas
                triggers = self._check_triggers()
                for persona_name in triggers.get("triggered_personas", []):
                    if persona_name in self.config:
                        success, output = self._execute_persona(persona_name, self.config[persona_name])
                        self.logger.info(f"Triggered execution of {persona_name}: {output}")

                # Execute scheduled personas
                for persona_name, persona_config in self.config.items():
                    if persona_config.get("schedule", {}).get("enabled", False):
                        # In a real implementation, this would check the schedule
                        # For this example, we'll just execute all enabled personas
                        success, output = self._execute_persona(persona_name, persona_config)
                        self.logger.info(f"Scheduled execution of {persona_name}: {output}")

                # Sleep for the remaining interval time
                elapsed = time.time() - start_time
                sleep_time = max(0, self.interval - elapsed)
                time.sleep(sleep_time)

            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")
                time.sleep(self.interval)  # Prevent tight loop on errors

        self.logger.info("Persona scheduler stopped")

def main():
    parser = argparse.ArgumentParser(description="Persona Scheduler Daemon")
    parser.add_argument("--interval", type=int, default=60,
                        help="Interval between checks in seconds (default: 60)")
    _default_config = Path(__file__).parent.parent / "data" / "personas.json"
    parser.add_argument("--config", type=Path, default=_default_config,
                        help="Path to persona config file (default: data/personas.json)")
    parser.add_argument("--daemon", action="store_true",
                        help="Run as a daemon (background process)")

    args = parser.parse_args()

    if args.daemon:
        # In a real implementation, this would fork and daemonize
        # For this example, we'll just run in the foreground
        print("Running in daemon mode (foreground for this example)")
        print("To properly daemonize, implement fork() and daemonization logic")

    scheduler = PersonaScheduler(args.config, args.interval)
    scheduler.run()

if __name__ == "__main__":
    main()
