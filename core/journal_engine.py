import json
import uuid
import argparse
import sys as _sys
from pathlib import Path
from datetime import datetime

_WIN = _sys.platform == "win32"
WILLOW_ROOT = Path(r"C:\Users\Sean\Documents\GitHub\Willow" if _WIN
                   else "/mnt/c/Users/Sean/Documents/GitHub/Willow")


def _journal_dir(username: str) -> Path:
    d = WILLOW_ROOT / "artifacts" / username / "journal"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _find_session_file(username: str, session_id: str) -> Path | None:
    for f in _journal_dir(username).glob(f"*_{session_id}.jsonl"):
        return f
    return None


def create_session(username: str, consent_state: str = "learn") -> str:
    session_id = uuid.uuid4().hex[:8]
    date_str = datetime.now().strftime("%Y-%m-%d")
    path = _journal_dir(username) / f"{date_str}_{session_id}.jsonl"
    event = {"type": "session.start", "timestamp": datetime.now().isoformat(),
             "payload": {"session_id": session_id, "user": username,
                         "consent_state": consent_state}}
    path.write_text(json.dumps(event) + "\n", encoding="utf-8")
    return session_id


def append_event(username: str, session_id: str, event_type: str, payload: dict) -> bool:
    path = _find_session_file(username, session_id)
    if not path:
        return False
    event = {"type": event_type, "timestamp": datetime.now().isoformat(), "payload": payload}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")
    return True


def end_session(username: str, session_id: str) -> bool:
    ok = append_event(username, session_id, "session.end",
                      {"session_id": session_id, "ended_at": datetime.now().isoformat()})
    if ok:
        session_file = _find_session_file(username, session_id)
        if session_file:
            import threading
            from core import atom_extractor
            t = threading.Thread(
                target=atom_extractor.run,
                args=(username, session_file),
                daemon=True,
            )
            t.start()
    return ok


def list_sessions(username: str, date: str = None) -> list:
    results = []
    pattern = f"{date}_*.jsonl" if date else "*.jsonl"
    for f in sorted(_journal_dir(username).glob(pattern)):
        parts = f.stem.split("_", 1)
        session_id = parts[1] if len(parts) == 2 else f.stem
        date_str = parts[0] if len(parts) == 2 else "unknown"
        events = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
        results.append({"session_id": session_id, "date": date_str,
                        "file": str(f), "event_count": len(events)})
    return results


def read_session(username: str, session_id: str) -> list:
    path = _find_session_file(username, session_id)
    if not path:
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def main():
    parser = argparse.ArgumentParser(description="Willow Journal Engine")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("new"); p.add_argument("--user", default="Sweet-Pea-Rudi19")
    p = sub.add_parser("add")
    p.add_argument("--user", default="Sweet-Pea-Rudi19")
    p.add_argument("--session", required=True)
    p.add_argument("--type", default="note")
    p.add_argument("--payload", required=True)
    p = sub.add_parser("end")
    p.add_argument("--user", default="Sweet-Pea-Rudi19"); p.add_argument("--session", required=True)
    p = sub.add_parser("list"); p.add_argument("--user", default="Sweet-Pea-Rudi19")
    p.add_argument("--date", default=None)
    p = sub.add_parser("read")
    p.add_argument("--user", default="Sweet-Pea-Rudi19"); p.add_argument("--session", required=True)

    args = parser.parse_args()

    if args.cmd == "new":
        sid = create_session(args.user)
        print(f"Session created: {sid}")
    elif args.cmd == "add":
        ok = append_event(args.user, args.session, getattr(args, "type"), {"text": args.payload})
        print("Added" if ok else "Session not found")
    elif args.cmd == "end":
        ok = end_session(args.user, args.session)
        print("Ended" if ok else "Session not found")
    elif args.cmd == "list":
        sessions = list_sessions(args.user, args.date)
        if not sessions:
            print("No sessions found.")
        for s in sessions:
            print(f"{s['date']}  {s['session_id']}  ({s['event_count']} events)")
    elif args.cmd == "read":
        events = read_session(args.user, args.session)
        for e in events:
            print(json.dumps(e, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
