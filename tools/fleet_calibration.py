"""
fleet_calibration.py — Fleet Provider Calibration Test

Sends identical prompts to every available fleet provider (including Anthropic),
scores each response using the BASE 17 calibration rubric [CTX:10CA7],
and stores results for tiered routing decisions.

Usage:
    python tools/fleet_calibration.py              # Run all tests
    python tools/fleet_calibration.py --dry-run    # Show providers, skip calls

Authority: Sean Campbell
System: Willow
ΔΣ=42
"""

import sys
import os
import json
import time
import argparse
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'core'))

import llm_router
from core.compact import register, resolve

# Calibration rubric ID
CALIBRATION_RUBRIC = '10CA7'

# Test prompts — each tests a different capability
TEST_PROMPTS = [
    {
        "id": "json-structured",
        "name": "Structured JSON output",
        "task_type": "general_completion",
        "prompt": """Return ONLY valid JSON (no markdown, no explanation):
{"name": "Albert Einstein", "field": "physics", "key_contribution": "<one sentence>", "born": <year>, "Nobel_year": <year>}""",
    },
    {
        "id": "summarize",
        "name": "Text summarization",
        "task_type": "text_summarization",
        "prompt": """Summarize in exactly 2 sentences:

The double-slit experiment demonstrates wave-particle duality, one of the fundamental
concepts of quantum mechanics. When particles such as electrons are fired at a barrier
with two slits, they create an interference pattern on a screen behind the barrier,
suggesting wave-like behavior. However, when detectors are placed at the slits to
observe which slit each particle passes through, the interference pattern disappears
and the particles behave as individual particles. This phenomenon, known as the
observer effect, has profound implications for our understanding of reality at the
quantum scale and remains one of the most debated topics in physics.""",
    },
    {
        "id": "rubric-score",
        "name": "Rubric-based scoring (JAC-style)",
        "task_type": "general_completion",
        "prompt": """Score this abstract on a scale of 1-10 for clarity and 1-10 for novelty.
Return ONLY JSON: {"clarity": <int>, "novelty": <int>, "reasoning": "<2 sentences>"}

Abstract: We propose a novel framework for understanding dark energy as an emergent
property of quantum vacuum fluctuations at cosmological scales. By extending the
holographic principle to include time-dependent boundary conditions, we derive a
modified Friedmann equation that naturally produces accelerating expansion without
requiring a cosmological constant.""",
    },
    {
        "id": "instruction-follow",
        "name": "Precise instruction following",
        "task_type": "general_completion",
        "prompt": """List exactly 5 prime numbers between 50 and 100. Format as a JSON array.
Do NOT include any explanation or text — ONLY the JSON array.""",
    },
    {
        "id": "reasoning",
        "name": "Multi-step reasoning",
        "task_type": "general_completion",
        "prompt": """A farmer has 3 fields. Field A produces 2x the wheat of Field B.
Field C produces half of what Field A produces. Together they produce 900 kg.
How much does each field produce? Return ONLY JSON:
{"field_a": <int>, "field_b": <int>, "field_c": <int>, "total": 900}""",
    },
]


def get_all_providers():
    """Get every provider that has a valid key, including paid."""
    llm_router.load_keys_from_json()
    available = llm_router.get_available_providers()
    all_providers = []
    for tier in ['free', 'cheap', 'paid']:
        for p in available.get(tier, []):
            all_providers.append(p)
    return all_providers


def call_provider_direct(provider, prompt, max_tokens=1024):
    """Call a specific provider directly, bypassing health checks and round-robin."""
    import requests as req

    start = time.time()
    try:
        # OCI Gemini (uses oci SDK directly)
        if provider.env_key == "ORACLE_OCI":
            from pathlib import Path
            creds_path = Path("credentials.json")
            if not creds_path.exists():
                return None, 0, "no credentials.json"
            with open(creds_path) as f:
                creds = json.load(f)
            oci_conf = creds.get("ORACLE_OCI", {})
            compartment_id = oci_conf.get("compartment_id")
            config_path = oci_conf.get("config_path", str(Path.home() / ".oci" / "config"))
            import oci
            from oci.generative_ai_inference import GenerativeAiInferenceClient
            from oci.generative_ai_inference.models import (
                GenericChatRequest as GCR, OnDemandServingMode, ChatDetails,
                TextContent, UserMessage,
            )
            oci_config = oci.config.from_file(config_path)
            client = GenerativeAiInferenceClient(config=oci_config, service_endpoint=provider.base_url)
            response = client.chat(ChatDetails(
                compartment_id=compartment_id,
                serving_mode=OnDemandServingMode(model_id=provider.model),
                chat_request=GCR(
                    messages=[UserMessage(content=[TextContent(text=prompt)])],
                    max_tokens=max_tokens,
                ),
            ))
            elapsed = time.time() - start
            choice = response.data.chat_response.choices[0]
            if choice.message and choice.message.content:
                return choice.message.content[0].text, elapsed, None
            return None, elapsed, "empty OCI response"

        # Ollama
        elif provider.name.startswith("Ollama"):
            r = req.post(provider.base_url, json={
                "model": provider.model,
                "prompt": prompt,
                "stream": False,
            }, timeout=60)
            elapsed = time.time() - start
            if r.ok:
                return r.json().get("response", ""), elapsed, None
            return None, elapsed, f"HTTP {r.status_code}"

        # Google Gemini
        elif "generativelanguage.googleapis.com" in provider.base_url:
            api_key = os.environ.get(provider.env_key, "")
            url = f"{provider.base_url}{provider.model}:generateContent?key={api_key}"
            r = req.post(url, json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": max_tokens},
            }, timeout=60)
            elapsed = time.time() - start
            if r.ok:
                data = r.json()
                text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                return text, elapsed, None
            return None, elapsed, f"HTTP {r.status_code}: {r.text[:100]}"

        # Anthropic
        elif "anthropic.com" in provider.base_url:
            api_key = os.environ.get(provider.env_key, "")
            r = req.post(provider.base_url, headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }, json={
                "model": provider.model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }, timeout=60)
            elapsed = time.time() - start
            if r.ok:
                data = r.json()
                text = data.get("content", [{}])[0].get("text", "")
                return text, elapsed, None
            return None, elapsed, f"HTTP {r.status_code}: {r.text[:100]}"

        # OpenAI-compatible (Groq, Cerebras, SambaNova, Novita, Together, OpenRouter, OpenAI)
        else:
            api_key = os.environ.get(provider.env_key, "")
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            # OpenRouter needs extra header
            if "openrouter" in provider.base_url:
                headers["HTTP-Referer"] = "https://willow.local"
            r = req.post(provider.base_url, headers=headers, json={
                "model": provider.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
            }, timeout=60)
            elapsed = time.time() - start
            if r.ok:
                data = r.json()
                text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return text, elapsed, None
            return None, elapsed, f"HTTP {r.status_code}: {r.text[:200]}"

    except Exception as e:
        elapsed = time.time() - start
        return None, elapsed, str(e)[:200]


def score_response(prompt_text, response_text, judge_provider=None):
    """Score a response using the calibration rubric via a different provider."""
    rubric = resolve(CALIBRATION_RUBRIC)
    if not rubric:
        return {"error": "Calibration rubric not found", "total": 0}

    judge_prompt = f"""{rubric['content']}

ORIGINAL PROMPT:
{prompt_text}

MODEL RESPONSE:
{response_text}"""

    # Use the judge provider or fall back to fleet
    if judge_provider:
        result, _, err = call_provider_direct(judge_provider, judge_prompt)
    else:
        resp = llm_router.ask(judge_prompt, preferred_tier="free")
        result = resp.content if resp else None

    if not result:
        return {"error": "Judge call failed", "total": 0}

    # Parse JSON from response
    try:
        # Strip markdown fences if present
        clean = result.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
            clean = clean.rsplit("```", 1)[0]
        return json.loads(clean.strip())
    except json.JSONDecodeError:
        return {"error": "Judge returned invalid JSON", "raw": result[:300], "total": 0}


def run_calibration(dry_run=False, include_paid=True):
    """Run calibration across all providers."""
    providers = get_all_providers()
    if not include_paid:
        providers = [p for p in providers if p.tier != "paid"]

    print(f"\n{'='*70}")
    print(f"FLEET CALIBRATION — {datetime.now().isoformat()}")
    print(f"Rubric: [CTX:{CALIBRATION_RUBRIC}] (fleet-calibration-v1)")
    print(f"Providers: {len(providers)}")
    print(f"Test prompts: {len(TEST_PROMPTS)}")
    print(f"Total calls: {len(providers) * len(TEST_PROMPTS)}")
    print(f"{'='*70}\n")

    for p in providers:
        print(f"  [{p.tier:5s}] {p.name:25s} model={p.model[:40]}")
    print()

    if dry_run:
        print("[DRY RUN] Skipping actual calls.")
        return

    results = []

    for test in TEST_PROMPTS:
        print(f"\n--- Test: {test['name']} ({test['id']}) ---")
        for provider in providers:
            sys.stdout.write(f"  {provider.name:25s} ... ")
            sys.stdout.flush()

            response, elapsed, error = call_provider_direct(provider, test["prompt"])

            if error:
                print(f"FAIL ({elapsed:.1f}s) — {error[:60]}")
                results.append({
                    "test_id": test["id"],
                    "provider": provider.name,
                    "tier": provider.tier,
                    "model": provider.model,
                    "elapsed_s": round(elapsed, 2),
                    "error": error,
                    "scores": None,
                    "total": 0,
                })
                continue

            response_preview = (response or "")[:80].replace("\n", " ")
            print(f"OK ({elapsed:.1f}s) [{len(response or '')} chars] {response_preview}...")

            # Score the response
            score = score_response(test["prompt"], response)
            total = score.get("total", 0)
            scores = score.get("scores", {})

            if total > 0:
                print(f"    Score: {total}/50 — IF:{scores.get('instruction_following',0)} CO:{scores.get('completeness',0)} AC:{scores.get('accuracy',0)} JS:{scores.get('json_compliance',0)} CH:{scores.get('coherence',0)}")
            elif score.get("error"):
                print(f"    Score: JUDGE FAILED — {score.get('error','')[:60]}")

            results.append({
                "test_id": test["id"],
                "provider": provider.name,
                "tier": provider.tier,
                "model": provider.model,
                "elapsed_s": round(elapsed, 2),
                "response_chars": len(response or ""),
                "response_preview": (response or "")[:200],
                "scores": scores if scores else None,
                "total": total,
                "judge_notes": score.get("notes", ""),
                "truncated": score.get("truncated", False),
                "hallucinated": score.get("hallucinated", False),
            })

            # Be nice to rate limits
            time.sleep(0.5)

    # Summary
    print(f"\n{'='*70}")
    print("CALIBRATION SUMMARY")
    print(f"{'='*70}")

    # Aggregate by provider
    provider_scores = {}
    for r in results:
        pname = r["provider"]
        if pname not in provider_scores:
            provider_scores[pname] = {"total": 0, "count": 0, "fails": 0, "tier": r["tier"], "times": []}
        if r.get("error"):
            provider_scores[pname]["fails"] += 1
        elif r["total"] > 0:
            provider_scores[pname]["total"] += r["total"]
            provider_scores[pname]["count"] += 1
        provider_scores[pname]["times"].append(r["elapsed_s"])

    # Sort by average score
    ranked = sorted(
        provider_scores.items(),
        key=lambda x: (x[1]["total"] / max(x[1]["count"], 1)),
        reverse=True,
    )

    print(f"\n{'Provider':30s} {'Tier':6s} {'Avg':5s} {'Tests':5s} {'Fails':5s} {'Avg Time':8s}")
    print("-" * 70)
    for name, data in ranked:
        avg = data["total"] / max(data["count"], 1)
        avg_time = sum(data["times"]) / max(len(data["times"]), 1)
        print(f"{name:30s} {data['tier']:6s} {avg:5.1f} {data['count']:5d} {data['fails']:5d} {avg_time:7.1f}s")

    # Save results
    out_path = os.path.join(os.path.dirname(__file__), '..', 'artifacts', 'fleet_calibration.json')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "rubric_id": CALIBRATION_RUBRIC,
            "providers_tested": len(providers),
            "tests_per_provider": len(TEST_PROMPTS),
            "results": results,
            "summary": {name: {
                "avg_score": round(d["total"] / max(d["count"], 1), 1),
                "tests_passed": d["count"],
                "tests_failed": d["fails"],
                "avg_time_s": round(sum(d["times"]) / max(len(d["times"]), 1), 2),
                "tier": d["tier"],
            } for name, d in ranked},
        }, f, indent=2)
    print(f"\nResults saved: {out_path}")

    # Register summary as compact context for future routing decisions
    summary_lines = [f"Fleet calibration {datetime.now().date()}:"]
    for name, data in ranked:
        avg = data["total"] / max(data["count"], 1)
        summary_lines.append(f"  {name} ({data['tier']}): {avg:.0f}/50 avg, {data['fails']} fails")
    summary_id = register(
        content="\n".join(summary_lines),
        category="pattern",
        label="fleet-calibration-latest",
        agent="ganesha",
        ttl_hours=7*24,  # 1 week
    )
    print(f"Summary registered as [CTX:{summary_id}]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fleet Provider Calibration")
    parser.add_argument("--dry-run", action="store_true", help="List providers without calling")
    parser.add_argument("--no-paid", action="store_true", help="Skip paid providers")
    args = parser.parse_args()

    run_calibration(dry_run=args.dry_run, include_paid=not args.no_paid)
