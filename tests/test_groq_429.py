#!/usr/bin/env python3
"""Test Groq 429 handling and cascade."""

import sys
sys.path.insert(0, 'core')
import llm_router

# Load keys
llm_router.load_keys_from_json()

print("Testing cascade with Groq 429...")
print("=" * 60)

# Try a simple request
response = llm_router.ask("Say 'test' in one word", preferred_tier="free")

if response:
    print(f"\n[OK] Got response from: {response.provider}")
    print(f"Tier: {response.tier}")
    print(f"Content: {response.content[:100]}")
else:
    print("\n[FAIL] No response received - cascade failed")

# Print what providers are available
print("\n" + "=" * 60)
print("Available providers:")
avail = llm_router.get_available_providers()
for tier, providers in avail.items():
    print(f"\n{tier.upper()}:")
    for p in providers:
        print(f"  - {p.name}")
