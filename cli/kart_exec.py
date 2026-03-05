"""
Kart - Autonomous AI Assistant (Claude Code equivalent)
Free-tier LLM with multi-step tool execution
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core import agent_engine

class Kart:
    def __init__(self, username: str = "Sweet-Pea-Rudi19"):
        self.engine = agent_engine.AgentEngine(username, "kart")
        self.username = username
    
    def execute(self, task: str, max_steps: int = 15):
        """Execute task autonomously."""
        conversation = []
        all_tools = []
        step = 0
        current_message = task
        
        while step < max_steps:
            step += 1
            result = self.engine.chat(current_message, conversation_history=conversation)
            
            if not isinstance(result, dict):
                return {"success": False, "error": "Invalid response"}
            
            response = result.get("response", "")
            tools = result.get("tool_calls", [])
            
            if tools:
                all_tools.extend(tools)
                for t in tools:
                    name = t.get("tool", "?")
                    ok = t.get("result", {}).get("success", False)
                    print(f"  {'OK' if ok else 'X '} {name}")
            
            conversation.append({"role": "user", "content": current_message})
            conversation.append({"role": "assistant", "content": response})
            
            if not tools and response:
                return {
                    "success": True,
                    "response": response,
                    "steps": step,
                    "tools": len(all_tools),
                    "provider": result.get("provider", "?")
                }
            
            if tools:
                summary = [f"{t.get('tool')}: {'ok' if t.get('result',{}).get('success') else 'fail'}" 
                          for t in tools]
                current_message = f"Results: {'; '.join(summary)}. Continue."
            else:
                current_message = "Continue task."
        
        return {
            "success": False,
            "error": f"Max steps reached ({max_steps})",
            "response": response if 'response' in locals() else "",
            "steps": step,
            "tools": len(all_tools)
        }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: kart \"task description\"")
        print("\nExamples:")
        print('  kart "List Python files in core"')
        print('  kart "Read README.md and summarize"')
        print('  kart "Find all .md files"')
        sys.exit(1)
    
    task = " ".join(sys.argv[1:])
    print(f"Kart: {task}")
    print()
    
    try:
        k = Kart()
        result = k.execute(task)
        
        print()
        if result["success"]:
            print(result["response"])
            print()
            print(f"[Done: {result['steps']} steps, {result['tools']} tools, {result.get('provider','?')}]")
        else:
            print(f"Error: {result.get('error','Unknown')}")
            if result.get("response"):
                print(result["response"])
    except KeyboardInterrupt:
        print("\n\nInterrupted")
    except Exception as e:
        print(f"\nError: {e}")
