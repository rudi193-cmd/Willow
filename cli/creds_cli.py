#!/usr/bin/env python3
"""creds_cli.py - Willow credential vault CLI"""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "core"))
from credentials import (
    set_cred, get_cred, delete_cred, list_creds,
    push_to_env, export_env_file, migrate_from_json,
)

def main():
    p = argparse.ArgumentParser(description="Willow credential vault")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("set")
    s.add_argument("name"); s.add_argument("value"); s.add_argument("--env", default=None)

    g = sub.add_parser("get"); g.add_argument("name")
    sub.add_parser("list")
    d = sub.add_parser("delete"); d.add_argument("name")
    m = sub.add_parser("migrate"); m.add_argument("json_path")
    sub.add_parser("env")
    e = sub.add_parser("export"); e.add_argument("path")

    args = p.parse_args()
    if args.cmd == "set":
        set_cred(args.name, args.value, args.env)
        print(f"Set: {args.name}" + (f" (env={args.env})" if args.env else ""))
    elif args.cmd == "get":
        v = get_cred(args.name)
        if v is None:
            print(f"Not found: {args.name}", file=sys.stderr); sys.exit(1)
        print(v)
    elif args.cmd == "list":
        rows = list_creds()
        if not rows:
            print("No credentials stored."); return
        for r in rows:
            hint = f"  -> {r['env_key']}" if r["env_key"] else ""
            print(f"  {r['name']}{hint}  (updated {r['updated_at'][:10]})")
    elif args.cmd == "delete":
        print("Deleted." if delete_cred(args.name) else f"Not found: {args.name}")
    elif args.cmd == "migrate":
        print(f"Migrated {migrate_from_json(args.json_path)} credentials")
    elif args.cmd == "env":
        print(f"Pushed {push_to_env()} credentials to environment")
    elif args.cmd == "export":
        print(f"Wrote {export_env_file(args.path)} credentials to {args.path}")

if __name__ == "__main__":
    main()
