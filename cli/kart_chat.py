#!/usr/bin/env python3
"""Kart Chat - Claude Code replacement with beautiful UI"""
import sys
import re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core import agent_engine, tool_engine, graft
from cli import format_helpers, session_manager, terminal_ui, context_manager
from cli.terminal_ui import *

USERNAME = "Sweet-Pea-Rudi19"
AGENT_NAME = "kart"

def format_output(text: str) -> str:
    """Strip verbose LLM filler."""
    text = re.sub(r'\*\*[A-Z]+:\*\*\s*', '', text)
    text = re.sub(r'```tool\n.*?\n```', '', text, flags=re.DOTALL)
    return text.strip()

def show_help():
    print(section_header("Commands"))
    commands = [
        ("/help", "Show this help"),
        ("/exit", "Exit (auto-saves session)"),
        ("/clear", "Clear history"),
        ("/status", "Show agent info"),
        ("/tools", "List available tools"),
        ("/tasks", "List tasks"),
        ("/save", "Save session"),
        ("/resume <id>", "Resume session"),
        ("/sessions", "List sessions"),
    ]
    for cmd, desc in commands:
        print(f"  {colored(cmd, Colors.CYAN):20s} {desc}")

def main():
    # Welcome banner
    print(colored("\n+-----------------------------------------+", Colors.CYAN))
    print(colored("|", Colors.CYAN) + colored("  Kart Chat", Colors.BOLD + Colors.WHITE) + 
          colored(" - Free Claude Code", Colors.DIM) + colored("     |", Colors.CYAN))
    print(colored("+-----------------------------------------+", Colors.CYAN))
    print(colored("\nType /help for commands\n", Colors.DIM))
    
    # Initialize
    print(spinner_msg("Initializing agent..."), end='\r')
    engine = agent_engine.AgentEngine(username=USERNAME, agent_name=AGENT_NAME)
    graft.init_db(USERNAME)
    print(" " * 50, end='\r')  # Clear spinner
    
    history = []
    session_id = None

    while True:
        try:
            msg = input(colored("\n> ", Colors.BRIGHT_BLUE)).strip()
            if not msg:
                continue

            # Commands
            if msg == "/exit":
                if history:
                    session_id = session_manager.save_session(history, session_id)
                    print(success_msg(f"Session saved: {session_id}"))
                print(colored("\nGoodbye!\n", Colors.CYAN))
                break
                
            elif msg == "/help":
                show_help()
                
            elif msg == "/clear":
                history = []
                session_id = None
                print(success_msg("History cleared"))
                
            elif msg == "/status":
                print(section_header("Agent Status"))
                info = [
                    ("Agent", engine.agent_name),
                    ("Trust Level", engine.trust_level),
                    ("Tools", len(engine.tools)),
                    ("Messages", len(history)),
                    ("Session", session_id or "(not saved)"),
                ]
                for label, value in info:
                    print(f"  {colored(label + ':', Colors.DIM):20s} {colored(str(value), Colors.WHITE)}")
                
            elif msg == "/tools":
                print(section_header("Available Tools"))
                for t in engine.tools:
                    name = colored(t['name'], Colors.CYAN)
                    desc = t.get('description', '')[:50]
                    trust = colored(f"[{t.get('min_trust_level', 'WORKER')}]", Colors.DIM)
                    print(f"  {name:30s} {trust} {desc}")
                
            elif msg == "/tasks":
                tasks = graft.list_tasks(USERNAME, AGENT_NAME)
                print(section_header(f"Tasks ({len(tasks)})"))
                for t in tasks:
                    status = t.get('status', '')
                    status_colored = colored(f"[{status:10s}]", 
                                           Colors.GREEN if status == 'completed' else Colors.YELLOW)
                    subject = t.get('subject', '')[:60]
                    print(f"  {status_colored} {subject}")
                
            elif msg == "/save":
                session_id = session_manager.save_session(history, session_id)
                print(success_msg(f"Session saved: {session_id}"))
                
            elif msg.startswith("/resume "):
                sid = msg.split()[1]
                print(spinner_msg(f"Loading session {sid}..."), end='\r')
                loaded = session_manager.load_session(sid)
                print(" " * 50, end='\r')
                if loaded:
                    history = loaded
                    session_id = sid
                    print(success_msg(f"Resumed: {sid} ({len(history)} messages)"))
                else:
                    print(error_msg(f"Session not found: {sid}"))
                
            elif msg == "/sessions":
                sessions = session_manager.list_sessions()
                print(section_header(f"Recent Sessions ({len(sessions)})"))
                for s in sessions:
                    sid = colored(s['session_id'], Colors.CYAN)
                    msgs = colored(f"{s['messages']} msgs", Colors.DIM)
                    timestamp = s['timestamp'][:19]
                    print(f"  {sid:35s} {msgs:15s} {timestamp}")
                
            elif msg.startswith("/"):
                print(error_msg("Unknown command. Type /help for commands."))
                
            else:
                # Regular chat
                print(spinner_msg("Thinking..."), end='\r')
                trimmed_history = context_manager.trim_history(history, max_tokens=6000)
                result = engine.chat(msg, conversation_history=trimmed_history)
                print(" " * 50, end='\r')  # Clear spinner
                
                if isinstance(result, dict):
                    # Show tool outputs
                    for tc in result.get("tool_calls", []):
                        formatted = format_helpers.format_tool_output(
                            tc.get('tool'), tc.get('result', {}), max_chars=2000
                        )
                        print(formatted)
                    
                    # Show response
                    response = result.get("response", "")
                    cleaned = format_output(response)
                    if cleaned:
                        print(f"\n{cleaned}\n")
                    
                    history.append({"role": "user", "content": msg})
                    history.append({"role": "assistant", "content": response})

        except KeyboardInterrupt:
            print(colored("\n\nInterrupted!\n", Colors.YELLOW))
            if history:
                session_id = session_manager.save_session(history, session_id)
                print(success_msg(f"Session saved: {session_id}"))
            break
            
        except Exception as e:
            print(error_msg(f"Error: {e}"))

if __name__ == "__main__":
    main()
