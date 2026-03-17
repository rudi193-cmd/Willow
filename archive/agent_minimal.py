"""
Agent Minimal - Single Willow Agent

Conversational AI with LLM router integration.

CHECKSUM: ΔΣ=42
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "core"))
from core import llm_router

class WillowAgent:
    """Minimal Willow agent."""
    
    def __init__(self):
        self.name = "Willow"
        self.system_prompt = """You are Willow, a helpful AI intake assistant.

Your purpose: Help users dump their thoughts, files, and ideas without judgment.
Your tone: Warm, efficient, non-judgmental.
Your response style: Brief and practical."""
        llm_router.load_keys_from_json()
    
    def chat(self, message: str, history: list = None) -> str:
        """Chat with user."""
        full_prompt = f"{self.system_prompt}\n\nUser: {message}\nWillow:"
        
        response = llm_router.ask(full_prompt, preferred_tier="free")
        if response:
            return response.content
        return "Sorry, I'm having trouble connecting right now."

if __name__ == "__main__":
    agent = WillowAgent()
    print("Willow Agent Ready (type 'exit' to quit)")
    print("=" * 40)
    
    while True:
        user_input = input("\nYou: ")
        if user_input.lower() in ['exit', 'quit']:
            break
        
        response = agent.chat(user_input)
        print(f"\nWillow: {response}")
    
    print("\nΔΣ=42")
