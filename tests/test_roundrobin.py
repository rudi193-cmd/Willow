#!/usr/bin/env python3
"""Test round-robin provider rotation."""

import sys
sys.path.insert(0, 'core')
import llm_router

llm_router.load_keys_from_json()

print("Testing round-robin rotation...")
print("=" * 60)

# Make 10 requests - should rotate through providers
for i in range(10):
    resp = llm_router.ask("test", preferred_tier="free", use_round_robin=True)
    if resp:
        print(f"Request {i+1}: {resp.provider}")
    else:
        print(f"Request {i+1}: FAILED")

print("\n" + "=" * 60)
print("Expected: Should cycle through different providers")
print("Not expected: Same provider for all 10 requests")
