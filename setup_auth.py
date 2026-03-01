#!/usr/bin/env python3
"""
One-time setup: seed a user passphrase in Willow/data/users.json

Usage:
  python setup_auth.py                                   # prompts (visible input)
  python setup_auth.py Sweet-Pea-Rudi19 mypassphrase    # non-interactive, no TTY needed
"""

import hashlib
import json
import os
import sys
from pathlib import Path

USERS_PATH = Path(__file__).parent / "data" / "users.json"


def scrypt_hash(passphrase: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(passphrase.encode(), salt=salt, n=16384, r=8, p=1)
    return f"{salt.hex()}:{dk.hex()}"


def main():
    if not USERS_PATH.exists():
        print(f"ERROR: {USERS_PATH} not found")
        return
    data = json.loads(USERS_PATH.read_text())
    users = data["users"]

    # Non-interactive mode: python setup_auth.py <username> <passphrase>
    if len(sys.argv) == 3:
        username, passphrase = sys.argv[1], sys.argv[2]
        if username not in users:
            print(f"ERROR: User '{username}' not in users.json")
            sys.exit(1)
        users[username]["passphrase_hash"] = scrypt_hash(passphrase)
        USERS_PATH.write_text(json.dumps(data, indent=2))
        print(f"Passphrase set for {username}")
        return

    # Interactive mode — input() works in all terminals (input is visible)
    print("Users:", list(users.keys()))
    username = input("Username [Sweet-Pea-Rudi19]: ").strip() or "Sweet-Pea-Rudi19"
    if username not in users:
        print(f"ERROR: User '{username}' not in users.json")
        return
    print("(input will be visible — this runs once locally)")
    passphrase = input("New passphrase: ")
    confirm = input("Confirm passphrase: ")
    if passphrase != confirm:
        print("Passphrases do not match — aborted")
        return
    users[username]["passphrase_hash"] = scrypt_hash(passphrase)
    USERS_PATH.write_text(json.dumps(data, indent=2))
    print(f"Passphrase set for {username}")


if __name__ == "__main__":
    main()
