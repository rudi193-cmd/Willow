#!/usr/bin/env python3
"""Test cascade logging."""

import logging
logging.basicConfig(level=logging.INFO, format='%(message)s')

import sys
sys.path.insert(0, 'core')
import llm_router

print("Testing LLM Router cascade with logging...")
print("=" * 60)

llm_router.load_keys_from_json()
resp = llm_router.ask('Say "hello" in one word')

print("=" * 60)
if resp:
    print(f"SUCCESS: Got response from {resp.provider}")
else:
    print("FAILED: No providers responded")
