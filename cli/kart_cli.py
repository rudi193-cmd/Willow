#!/usr/bin/env python3
"""
Kart CLI - Command Line Interface for Kart Orchestrator

Usage:
    kart "task description"
    kart --resume /path/to/seed_packet.json
    kart --status
    kart --tasks
    kart --tools

GOVERNANCE: All operations validated through Kart orchestrator
AUTHOR: Kart Orchestration System
VERSION: 1.0
CHECKSUM: ΔΣ=42
"""

import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core import rings, graft, tool_engine, agent_registry

# Configuration
USERNAME = "Sweet-Pea-Rudi19"
AGENT_NAME = "kart"


def _server_online() -> bool:
    """Quick connectivity check — returns True if Willow server is reachable."""
    try:
        import urllib.request
        urllib.request.urlopen("http://localhost:8420/api/agents/health", timeout=1)
        return True
    except Exception:
        return False


def display_result(result: Dict[str, Any]):
    """Display orchestration result in a user-friendly format."""
    print("\n" + "=" * 60)

    if result.get("success"):
        print("[COMPLETED] TASK COMPLETED")
        print("=" * 60)
        print()
        print(result.get("result", "Done"))
        print()

        # Show steps if available
        steps = result.get("steps", [])
        if steps:
            print(f"Steps executed: {len(steps)}")
            for step in steps:
                tool = step.get("tool")
                success = step.get("result", {}).get("success", False)
                status = "[OK]" if success else "[FAIL]"
                print(f"  {status} Step {step['step']}: {tool}")

    else:
        print("[FAILED] TASK FAILED" if "PENDING" not in result.get("result", "") else "[PAUSED] TASK PAUSED")
        print("=" * 60)
        print()
        print(result.get("result", "Unknown error"))
        print()

        # Show steps
        steps = result.get("steps", [])
        if steps:
            print(f"Steps completed before pause/failure: {len(steps)}")
            for step in steps[-5:]:  # Show last 5 steps
                tool = step.get("tool")
                print(f"  Step {step['step']}: {tool}")

        # Show SEED_PACKET if task was paused
        if result.get("seed_packet"):
            print()
            print(f"SEED_PACKET saved: {result['seed_packet']}")
            print(f"Resume with: kart --resume {result['seed_packet']}")

        # Show message if available
        if result.get("message"):
            print()
            print(result["message"])

    print()
    print(f"Session ID: {result.get('session_id', 'unknown')}")
    print("=" * 60)


def cmd_execute(task: str):
    """Execute a task."""
    print(f"Kart: Executing task...")
    print(f"Task: {task}")
    print()

    result = rings.execute_task(
        username=USERNAME,
        user_request=task,
        agent_name=AGENT_NAME
    )

    display_result(result)
    return 0 if result.get("success") else 1


def cmd_resume(seed_packet_path: str):
    """Resume a task from SEED_PACKET."""
    print(f"Kart: Resuming task from SEED_PACKET...")
    print(f"SEED_PACKET: {seed_packet_path}")
    print()

    result = rings.resume_task(
        username=USERNAME,
        seed_packet_path=seed_packet_path,
        agent_name=AGENT_NAME
    )

    display_result(result)
    return 0 if result.get("success") else 1


def cmd_status():
    """Show Kart status."""
    print()
    print("Kart Orchestrator Status")
    print("=" * 60)

    # Get agent info
    agent_info = agent_registry.get_agent(USERNAME, AGENT_NAME)

    if agent_info:
        print(f"Agent: {agent_info.get('display_name', AGENT_NAME)}")
        print(f"Trust Level: {agent_info.get('trust_level', 'UNKNOWN')}")
        print(f"Type: {agent_info.get('agent_type', 'unknown')}")
        print(f"Registered: {agent_info.get('registered_at', 'unknown')}")
    else:
        print(f"Agent: {AGENT_NAME} (NOT REGISTERED)")

    # Server connectivity
    server_up = _server_online()
    server_label = 'ONLINE (port 8420)' if server_up else 'OFFLINE — local mode active'
    print(f"\nServer: {server_label}")

    # Get tools
    tools = tool_engine.list_tools(AGENT_NAME, USERNAME)
    print(f"\nAvailable Tools: {len(tools)}")
    for tool in tools:
        print(f"  - {tool['name']}: {tool['description']}")

    # Get task stats
    stats = graft.get_stats(USERNAME, AGENT_NAME)
    print(f"\nTask Statistics:")
    print(f"  Total: {stats['total']}")
    print(f"  Pending: {stats['pending']}")
    print(f"  In Progress: {stats['in_progress']}")
    print(f"  Completed: {stats['completed']}")
    print(f"  Failed: {stats['failed']}")

    print("=" * 60)
    print()

    return 0


def cmd_server_restart():
    """Restart the Willow server. REPL context stays; new server code is loaded."""
    import urllib.request
    import time
    print("Sending restart signal to Willow server...")
    try:
        req = urllib.request.Request(
            "http://localhost:8420/api/admin/restart",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3)
    except Exception:
        pass  # Connection drops mid-restart — expected
    print("Waiting for server", end="", flush=True)
    for _ in range(20):
        time.sleep(1)
        print(".", end="", flush=True)
        try:
            urllib.request.urlopen("http://localhost:8420/api/agents/health", timeout=1)
            print(" back up!")
            return
        except Exception:
            pass
    print("\nTimed out — server may still be starting.")


def cmd_agent_restart():
    """Restart Kart agent context. CLI-only safe — no server required."""
    import json
    from datetime import datetime as _dt
    print("\nRestarting agent context...")

    session_path = Path(__file__).parent.parent / "artifacts" / "kart" / "sessions"
    session_path.mkdir(parents=True, exist_ok=True)
    marker = {
        "type": "agent_restart",
        "timestamp": _dt.now().isoformat(),
        "agent": AGENT_NAME,
        "user": USERNAME,
        "message": "Agent context reset by user via :agent_restart"
    }
    ts = _dt.now().strftime("%Y%m%d-%H%M%S")
    (session_path / f"agent-restart-{ts}.json").write_text(json.dumps(marker, indent=2))

    print("Agent context cleared. Starting fresh.")
    print()
    cmd_status()
    return 0


def cmd_tasks(status_filter: str = None):
    """List tasks."""
    tasks = graft.list_tasks(USERNAME, AGENT_NAME, status=status_filter)

    print()
    print(f"Kart Tasks{f' ({status_filter})' if status_filter else ''}")
    print("=" * 60)

    if not tasks:
        print("No tasks found.")
    else:
        for task in tasks[:10]:  # Show last 10
            status_symbol = {
                "pending": "[PENDING]",
                "in_progress": "[RUNNING]",
                "completed": "[DONE]",
                "failed": "[FAILED]"
            }.get(task["status"], "[?]")

            print(f"{status_symbol} {task['task_id']}: {task['subject']}")
            print(f"   Status: {task['status']}")
            print(f"   Created: {task['created_at']}")
            print()

        if len(tasks) > 10:
            print(f"... and {len(tasks) - 10} more tasks")

    print("=" * 60)
    print()

    return 0


def cmd_tools():
    """List available tools."""
    tools = tool_engine.list_tools(AGENT_NAME, USERNAME)

    print()
    print("Kart Tools")
    print("=" * 60)

    for tool in tools:
        print(f"\n{tool['name']}")
        print(f"  Description: {tool['description']}")
        print(f"  Parameters: {', '.join(tool['parameters'].keys())}")
        print(f"  Trust Level: {tool['required_trust']}")

    print()
    print("=" * 60)
    print()

    return 0


def cmd_repl():
    cmd_status()
    if not _server_online():
        print("\n[OFFLINE] Willow server not detected \u2014 running in local mode")
        print("  Fleet LLM and local tools available.")
        print("  Server-dependent tools (delegate_to_agent) will skip gracefully.")
        print("  Run :status after starting the server to confirm reconnection.\n")
    print("\nKart REPL  |  type a task, or :status :tasks :tools :server_restart :agent_restart :quit\n")
    while True:
        try:
            line = input("kart> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye.")
            break
        if not line:
            continue
        if line in (":quit", ":exit", "quit", "exit"):
            print("Bye.")
            break
        elif line == ":status":
            cmd_status()
        elif line == ":tasks":
            cmd_tasks(None)
        elif line == ":tools":
            cmd_tools()
        elif line in (":server_restart", ":sr"):
            cmd_server_restart()
        elif line in (":agent_restart", ":ar"):
            cmd_agent_restart()
        elif line.startswith(":"):
            print(f"Unknown command: {line}")
        else:
            cmd_execute(line)
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Kart Orchestrator CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  kart "Find all Python files in core/ that import llm_router"
  kart "Create a README.md listing all modules in core/"
  kart --resume artifacts/kart/sessions/kart-2026-02-08-143015.json
  kart --status
  kart --tasks
  kart --tasks --filter completed
  kart --tools
        """
    )

    parser.add_argument('task', nargs='?', help='Task description to execute')
    parser.add_argument('--resume', '-r', metavar='SEED_PACKET', help='Resume from SEED_PACKET')
    parser.add_argument('--status', '-s', action='store_true', help='Show Kart status')
    parser.add_argument('--tasks', '-t', action='store_true', help='List tasks')
    parser.add_argument('--filter', '-f', help='Filter tasks by status')
    parser.add_argument('--tools', action='store_true', help='List available tools')

    args = parser.parse_args()

    # Dispatch commands
    if args.status:
        return cmd_status()
    elif args.tasks:
        return cmd_tasks(args.filter)
    elif args.tools:
        return cmd_tools()
    elif args.resume:
        return cmd_resume(args.resume)
    elif args.task:
        return cmd_execute(args.task)
    else:
        return cmd_repl()


if __name__ == "__main__":
    sys.exit(main() or 0)
