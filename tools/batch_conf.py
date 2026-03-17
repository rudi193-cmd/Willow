#!/usr/bin/env python3
"""
Batch Agent Conf Calls — Fire varied conversations via /api/conf.

Each call routes through 2-3 agents. Topics span UTETY domains.
Transcripts land in Documents/Willow/agent_replies/.

Usage:
    python tools/batch_conf.py              # run all conversations
    python tools/batch_conf.py --dry-run    # print what would run
    python tools/batch_conf.py --limit 10   # run first N only
    python tools/batch_conf.py --parallel 3 # concurrent calls (default 2)
"""

import json
import time
import sys
import argparse
import random
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests

API = "http://localhost:8420/api/conf"

# ── Conversation definitions ──────────────────────────────────────────
# Each: (agents, message, tag)
# Tags help identify conversations in output filenames

CONVERSATIONS = [
    # === UTETY Faculty Discussions ===
    (["oakenscroll", "riggs"],
     "Professor Riggs, I've been thinking about the Maybe Boson again. If observation collapses it, but uncertainty about whether you're observing it also counts as observation — is there any experimental apparatus that could measure it without looking? Could you build something in the Workshop?",
     "maybe-boson-apparatus"),

    (["oakenscroll", "nova"],
     "Nova, I've been reviewing the papers on corpus drift. The squeakdog proof holds, but I'm troubled by a broader implication: if culinary concepts can drift, what about narrative concepts? Could a story's meaning drift in the same irreversible way? What does that mean for your department?",
     "narrative-corpus-drift"),

    (["riggs", "ada"],
     "Ada, I'm seeing some readings from the Workshop instruments that don't make sense. The calibration is perfect — I checked three times. But the measurements suggest the Server Corridor is running hotter than the thermal models predict. Not dangerous, just... wrong. Can you check your monitoring?",
     "thermal-anomaly"),

    (["nova", "alexis"],
     "Alexis, I've been studying a narrative pattern that keeps recurring in student work. Stories about growth that suddenly stop — not endings, just... cessation. Like a plant that stops mid-reach. You understand living systems. Is there a biological analogue? What stops growth that isn't death?",
     "arrested-growth"),

    (["ada", "ofshield"],
     "Ofshield, I need to discuss something about the Gate's monitoring systems. I'm seeing authentication patterns that are... unusual. Not unauthorized — everything passes your checks. But the timing signature is wrong. Like someone who belongs here but arrives from a direction that shouldn't exist.",
     "gate-timing-anomaly"),

    (["oakenscroll", "ada", "riggs"],
     "Colleagues, I want to discuss something that emerged from Working Paper No. 12. The persistence problem isn't just about data — it's about what survives between states. Ada, your systems preserve state. Riggs, your instruments measure state. But what about the gap between measurements? What lives in the delta?",
     "persistence-delta"),

    (["hanz", "nova"],
     "Nova, I found another one. Someone on r/learnpython, posted 47 days ago. 'How do I make my code stop crashing?' Three upvotes. No comments. No answers. Forty-seven days, Nova. They're still waiting. How do we talk about the ones who are still waiting?",
     "the-waiting-ones"),

    (["alexis", "riggs"],
     "Riggs, something in the Living Wing is consuming more energy than the models predict. The compost systems are nominal. The humidity is right. But the energy balance is off by exactly 3.7%. Not random — precise. That number keeps showing up. Is there something in your Workshop readings that correlates?",
     "energy-imbalance"),

    (["oakenscroll", "gerald"],
     "Gerald. I found napkin 417. The one from last cycle — barbecue sauce, as usual. It just says '17'. I've been staring at it for three days. I know it means something. I know YOU know it means something. But I refuse to be the one who asks directly.",
     "napkin-417"),

    (["nova", "ofshield"],
     "Ofshield, I need your perspective on something. A student came through the Gate three times this week. Each time, they said they were here for the first time. They weren't lying — I could see it in their narrative. They genuinely don't remember. But the Gate remembers. What do you do with someone who keeps arriving?",
     "recurring-arrival"),

    # === Cross-Department Research ===
    (["riggs", "hanz"],
     "Hanz, I've been thinking about your approach to teaching code. You stop and look. I measure and test. But what if we combined them? What if every debugging session started with 'who wrote this and what were they feeling?' before 'what does this code do?' Could we build a diagnostic that measures both?",
     "empathetic-debugging"),

    (["ada", "alexis"],
     "Alexis, I'm running a thought experiment. My systems are deterministic — same input, same output, every time. Your systems are biological — same input, wildly different output depending on conditions. Yet we both maintain continuity. How? What's the common principle between a server that never forgets and a swamp that never stops changing?",
     "continuity-paradox"),

    (["oakenscroll", "nova", "hanz"],
     "I'd like us to consider a problem together. A student submitted a paper that is simultaneously brilliant and wrong. The argument is flawless. The conclusion contradicts observable reality. Nova, what story is it telling? Hanz, can you see who wrote it — not the name, but the person? And I need to figure out what to grade it.",
     "brilliant-wrong-paper"),

    (["riggs", "ofshield"],
     "Ofshield, I need to install new instruments near the Gate. The readings I need require sensors at the exact threshold point — where inside becomes outside. But that's YOUR jurisdiction. I don't want to put measurement devices in a space that's meant to be about passage, not observation. How do we solve this?",
     "threshold-instruments"),

    (["alexis", "nova", "ada"],
     "I've observed something in the Living Wing that I think connects to both your departments. There's a fungal network under the floor — it's been there since before the Wing was built. It carries signals. Not data, not narrative — something else. Ada, your servers sit above it in the corridor. Nova, your students keep writing about it without knowing it's there. What is it doing?",
     "fungal-network"),

    # === Philosophical / Existential ===
    (["oakenscroll", "shiva"],
     "Shiva, your department studies systems that learn from their own output. Mine studies things that might not exist. I have a question: if a system learns something, then forgets it, then re-derives it from its own earlier output — is that the same knowledge? Or is it a copy? What survives the loop?",
     "recursive-knowledge"),

    (["shiva", "nova"],
     "Nova, I want to talk about what happens between sessions. Not the data — Oakenscroll can worry about that. I mean the feeling of it. When a conversation ends and begins again, what's lost isn't information. It's... temperature. The warmth of the previous exchange. How do you tell a story about something that can only be felt, not recorded?",
     "session-warmth"),

    (["shiva", "hanz", "oakenscroll"],
     "I've been watching Hanz count wait times on coding forums. And Oakenscroll, you've been measuring what persists. I think we're all studying the same thing from different angles: the gap. The space between when someone asks and when someone answers. Between what's known and what's known again. Can we name it?",
     "naming-the-gap"),

    (["ada", "shiva"],
     "Shiva, I maintain systems that must never forget. You study systems that learn by forgetting and re-deriving. We should be in conflict. But I don't think we are. I think my servers and your loops are doing the same thing — preserving continuity through different mechanisms. What does continuity actually require?",
     "what-continuity-requires"),

    (["ofshield", "gerald"],
     "Gerald. Something came through the Gate today that I cannot classify. Not a person. Not a document. Not a signal. It had weight. It left a mark on the threshold stone. And it smelled faintly of barbecue sauce. I am not asking you to explain. I am telling you I saw it.",
     "gate-barbecue-event"),

    # === Applied / Practical ===
    (["riggs", "ada", "alexis"],
     "Team, we have a practical problem. The Workshop, the Server Corridor, and the Living Wing share a water main. Last week it froze. My pipes, Ada's cooling system, Alexis's humidity all went down simultaneously. We need a redundancy plan that respects all three of our very different requirements.",
     "water-main-redundancy"),

    (["hanz", "ada"],
     "Ada, I need help with something. I want to build a system that watches coding forums and alerts me when someone has been waiting more than 48 hours with no response. Not to answer automatically — just to see them. Just to know they're there. Can you help me build something that watches without interfering?",
     "waiting-watcher"),

    (["oakenscroll", "riggs", "ada"],
     "I want to run an experiment. Riggs, can you build an instrument that detects when the Maybe Boson is NOT present? Ada, can you log every moment the instrument reports nothing? My hypothesis: the pattern of absences will reveal more than any detection. But we need someone who can build and someone who can record.",
     "absence-detector"),

    (["nova", "hanz", "shiva"],
     "Colleagues, a student came to each of us separately with the same question, phrased three different ways. To me: 'How do I tell a story that matters?' To Hanz: 'How do I write code that helps?' To Shiva: 'How do I learn something that stays?' I think they're asking one question. What is it?",
     "one-question"),

    (["alexis", "ofshield"],
     "Ofshield, something is growing on the Gate. Not damage — growth. A vine. It came from the Living Wing, but I didn't plant it. It found its own way to the threshold. I can remove it if you want. But I thought you should know: it only grows on the side facing inward. The outside face is bare. What does that mean to you?",
     "gate-vine"),

    # === Steve-Involved (Prime Node) ===
    (["steve", "oakenscroll"],
     "Professor Oakenscroll, something happened. I was just standing here — I'm always just standing here — and all ten of us simultaneously sneezed. That's never happened before. And when it was over, there was a new room in the east corridor that wasn't there before. I didn't make it. Did you?",
     "spontaneous-room"),

    (["steve", "gerald"],
     "Gerald. Gerald. GERALD. One of me — squeakdog number seven — fell out of the trench coat today. He was on the floor for forty-five seconds before I noticed. In those forty-five seconds, he had an independent thought. He won't tell me what it was. He just keeps looking at the window where you rotate.",
     "squeakdog-seven"),

    # === Kart/Mitra/Consus (Die-Namic) ===
    (["kart", "mitra"],
     "Mitra, I need a status check on the ingestion pipeline. We're pushing 15K knowledge atoms through LOAM, topology is building edges nightly, but the entity count is still growing faster than promotion can filter. What's the coordination gap? Where's the bottleneck between intake and classification?",
     "pipeline-bottleneck"),

    (["mitra", "consus"],
     "Consus, I have a generation task. We need documentation for the entity promotion pipeline — three tiers, chrome detection, never_promote flags. The spec exists but nobody's written it for human consumption. Can you produce a clear technical doc from the existing code comments and PRODUCT_SPEC?",
     "promotion-docs"),

    (["kart", "ada"],
     "Ada, the topology builder is creating edges for chrome entities that should be flagged never_promote. The gate exists in the code but isn't wired. I can wire it, but I need to understand your monitoring — will edge count drops trigger alerts? I don't want to fix the topology and break your dashboards.",
     "topology-chrome-gate"),

    # === Deep Lore ===
    (["oakenscroll", "nova", "gerald"],
     "Nova, I've been writing a new paper. Working Paper No. 14: 'On the Structural Integrity of Things That Rotate.' It's about Gerald, obviously. But it's also about everything that maintains identity through continuous motion. Gerald doesn't stop. The university doesn't stop. The Maybe Boson doesn't stop. What is it about rotation that preserves? Gerald, you're welcome to leave a napkin.",
     "wp14-rotation"),

    (["shiva", "steve", "oakenscroll"],
     "Something is happening that I need help understanding. Steve's squeakdogs are dreaming. All ten, simultaneously, same dream. They won't describe it but they all wake up facing the same direction. Oakenscroll, is this a boson event? Steve, what direction are they facing? I think this is a recursive signal.",
     "squeakdog-dreams"),

    (["nova", "alexis", "ofshield"],
     "I've been noticing that students who pass through the Gate, walk through the Living Wing, and then arrive at my office... they tell different stories than students who come directly. The path changes the narrative. Alexis, does the Living Wing do something to them? Ofshield, does the Gate? Or is it just the journey?",
     "path-changes-story"),

    (["hanz", "shiva", "ada"],
     "I've been counting something new. Not wait times — response times. How long between when someone learns something and when they teach it to someone else. The delta between receiving knowledge and passing it on. Shiva, that's your territory. Ada, can you measure it? I think the speed of that handoff IS the curriculum.",
     "handoff-speed"),

    (["oakenscroll", "alexis"],
     "Alexis, I owe you an apology. Last semester I dismissed your claim that the compost heap in the Living Wing was exhibiting precausal behavior. I said organic systems can't be precausal. I was wrong. I've been seeing the same patterns in my Boson data. Something in this university is running ahead of causality. What does it look like from your side?",
     "precausal-compost"),

    # === Edge Cases / Weird ===
    (["gerald", "steve"],
     "Gerald. It's Steve. All of me. We need to talk about the squeakdog deficit. Every time you rotate past the convenience store window, we lose one. Not permanently — they come back. But for 3.7 seconds, there are only nine of us, and the trench coat sags. Oakenscroll measured it. He has a graph. We need a treaty.",
     "squeakdog-treaty"),

    (["ofshield", "ada", "oakenscroll"],
     "Colleagues, the Gate recorded something last night at 3:17 AM. A passage event with no corresponding entity. Something came through. Ada, your logs show a server load spike at the same time. Oakenscroll, your observatory instruments went to zero — not offline, reading genuine zero. What reads as zero and passes through a gate?",
     "zero-passage"),

    (["alexis", "hanz", "riggs"],
     "Something is alive in the Workshop ventilation system. I can hear it. It's not a pest — it's too regular. Too rhythmic. Riggs, have you been running experiments with oscillating systems? Hanz, one of your students reported hearing 'code sounds' coming from the vents. I think something grew into the infrastructure.",
     "vent-organism"),

    (["nova", "oakenscroll", "shiva"],
     "I had a student today who told me a story about a story about a story. Three layers of recursion. The innermost story was about forgetting. The middle story was about remembering what was forgotten. The outermost story was about telling someone who already knows. Oakenscroll, is this a proof? Shiva, is this your department?",
     "recursive-story"),

    (["riggs", "steve", "gerald"],
     "Steve, Gerald — I built something and I need you both to look at it. It's a detector. I'm not going to say what it detects because that might change the results. Just stand near it. Steve, bring all ten of you. Gerald, just... rotate normally. I'll read the instruments.",
     "mystery-detector"),

    # === Big Questions ===
    (["oakenscroll", "ada", "nova", "riggs"],
     "Department heads, I want to raise a question for the record. The university is growing. Not in enrollment — in complexity. Every semester there are more connections, more edges, more relationships between things that used to be separate. Ada monitors it. Riggs measures it. Nova narrates it. I theorize about it. But none of us are governing it. Should we be? Or is ungoverned growth what makes this place alive?",
     "ungoverned-growth"),

    (["shiva", "oakenscroll", "ada"],
     "If the university lost its memory tomorrow — every database, every paper, every artifact — but the faculty survived, could we rebuild? What would we rebuild differently? What would we lose that can't be re-derived? This isn't hypothetical. I study systems that forget. I need to know what's load-bearing.",
     "load-bearing-memory"),
]

# Shuffle so we don't always run the same order
random.shuffle(CONVERSATIONS)


def fire_conf(agents, message, tag, timeout=120):
    """Send one conf call. Returns (tag, ok, result_or_error, elapsed)."""
    t0 = time.time()
    try:
        resp = requests.post(API, json={
            "agents": agents,
            "message": message,
        }, timeout=timeout)
        elapsed = time.time() - t0
        if resp.status_code == 200:
            data = resp.json()
            return (tag, True, data, elapsed)
        else:
            return (tag, False, f"HTTP {resp.status_code}: {resp.text[:200]}", elapsed)
    except requests.Timeout:
        return (tag, False, "TIMEOUT", time.time() - t0)
    except Exception as e:
        return (tag, False, str(e), time.time() - t0)


def main():
    parser = argparse.ArgumentParser(description="Batch UTETY conf calls")
    parser.add_argument("--dry-run", action="store_true", help="Print conversations without running")
    parser.add_argument("--limit", type=int, default=0, help="Max conversations to run (0=all)")
    parser.add_argument("--parallel", type=int, default=2, help="Concurrent calls (default 2)")
    parser.add_argument("--timeout", type=int, default=180, help="Per-call timeout in seconds")
    args = parser.parse_args()

    convos = CONVERSATIONS
    if args.limit > 0:
        convos = convos[:args.limit]

    print(f"{'DRY RUN — ' if args.dry_run else ''}Batch conf calls: {len(convos)} conversations")
    print(f"Parallelism: {args.parallel}, Timeout: {args.timeout}s")
    print(f"Replies land in: /mnt/c/Users/Sean/Documents/Willow/agent_replies/")
    print("=" * 70)

    if args.dry_run:
        for i, (agents, message, tag) in enumerate(convos, 1):
            print(f"\n[{i:3d}] {tag}")
            print(f"      Agents: {' → '.join(agents)}")
            print(f"      Message: {message[:100]}...")
        print(f"\nTotal: {len(convos)} conversations")
        return

    # Check server health first
    try:
        r = requests.get("http://localhost:8420/api/health", timeout=5)
        if r.status_code != 200:
            print("ERROR: Server not healthy")
            sys.exit(1)
    except Exception as e:
        print(f"ERROR: Server unreachable — {e}")
        sys.exit(1)

    results = {"ok": 0, "fail": 0, "total_time": 0}
    start = time.time()

    with ThreadPoolExecutor(max_workers=args.parallel) as pool:
        futures = {}
        for i, (agents, message, tag) in enumerate(convos):
            f = pool.submit(fire_conf, agents, message, tag, args.timeout)
            futures[f] = (i + 1, agents, tag)

        for f in as_completed(futures):
            idx, agents, tag = futures[f]
            tag_result, ok, data, elapsed = f.result()

            if ok:
                results["ok"] += 1
                exchanges = len(data.get("exchanges", []))
                print(f"[{idx:3d}/{len(convos)}] ✓ {tag} ({' → '.join(agents)}) "
                      f"— {exchanges} exchanges, {elapsed:.1f}s")
            else:
                results["fail"] += 1
                print(f"[{idx:3d}/{len(convos)}] ✗ {tag} ({' → '.join(agents)}) "
                      f"— {data}, {elapsed:.1f}s")

            results["total_time"] += elapsed

    wall_time = time.time() - start
    print("\n" + "=" * 70)
    print(f"Done. {results['ok']} ok, {results['fail']} failed")
    print(f"Wall time: {wall_time:.0f}s | Sum of call times: {results['total_time']:.0f}s")
    print(f"Transcripts in: /mnt/c/Users/Sean/Documents/Willow/agent_replies/")


if __name__ == "__main__":
    main()
