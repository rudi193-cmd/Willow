"""
Kart Executor - Multi-step autonomous execution wrapper
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core import agent_engine

class KartExecutor:
    """Autonomous multi-step task executor (Claude Code equivalent)."""
    
    def __init__(self, username: str, agent_name: str = "kart"):
        self.engine = agent_engine.AgentEngine(username, agent_name)
        self.username = username
        self.agent_name = agent_name
    
    def execute(self, task: str, max_steps: int = 10, verbose: bool = True):
        """
        Execute task autonomously with multi-step tool chaining.
        Keeps executing tools until task is complete.
        """
        if verbose:
            print(f"[{self.agent_name}] Starting task...")
        
        conversation = []
        all_tools = []
        step = 0
        
        # Initial message
        current_message = task
        
        while step < max_steps:
            step += 1
            if verbose:
                print(f"[{self.agent_name}] Step {step}...")
            
            # Get response
            result = self.engine.chat(current_message, conversation_history=conversation)
            
            if not isinstance(result, dict):
                return {
                    "success": False,
                    "error": "Invalid response format",
                    "steps": step
                }
            
            response_text = result.get("response", "")
            tool_calls = result.get("tool_calls", [])
            
            # Track tools used
            if tool_calls:
                all_tools.extend(tool_calls)
                if verbose:
                    print(f"[{self.agent_name}] Executed {len(tool_calls)} tool(s)")
                    for tc in tool_calls:
                        tool_name = tc.get("tool", "?")
                        success = tc.get("result", {}).get("success", False)
                        print(f"  {'[OK]' if success else '[FAIL]'} {tool_name}")
            
            # Update conversation
            conversation.append({"role": "user", "content": current_message})
            conversation.append({"role": "assistant", "content": response_text})
            
            # Check if complete (no tool calls and has response)
            if not tool_calls and response_text:
                return {
                    "success": True,
                    "response": response_text,
                    "tool_calls": all_tools,
                    "steps": step,
                    "provider": result.get("provider", "unknown")
                }
            
            # Continue with tool results
            if tool_calls:
                # Build next message from tool results
                tool_summary = []
                for tc in tool_calls:
                    tool = tc.get("tool", "?")
                    res = tc.get("result", {})
                    if res.get("success"):
                        tool_summary.append(f"{tool}: success")
                    else:
                        tool_summary.append(f"{tool}: {res.get('error', 'failed')}")
                
                current_message = f"Tool results: {'; '.join(tool_summary)}. Continue with the task."
            else:
                # No tools but no complete response either
                current_message = "Please continue or complete the task."
        
        # Max steps reached
        return {
            "success": False,
            "error": f"Reached max steps ({max_steps})",
            "response": response_text if 'response_text' in locals() else "",
            "tool_calls": all_tools,
            "steps": step
        }

if __name__ == "__main__":
    USERNAME = "Sweet-Pea-Rudi19"
    
    if len(sys.argv) < 2:
        print("Usage: python kart_executor.py \"task description\"")
        sys.exit(1)
    
    task = " ".join(sys.argv[1:])
    
    executor = KartExecutor(USERNAME, "kart")
    result = executor.execute(task)
    
    print("\n" + "=" * 60)
    if result["success"]:
        print("COMPLETED")
        print("=" * 60)
        print(f"\n{result['response']}\n")
        print(f"Steps: {result['steps']}, Provider: {result.get('provider', '?')}")
    else:
        print("FAILED")
        print("=" * 60)
        print(f"\n{result.get('error', 'Unknown error')}\n")
    print("=" * 60)
