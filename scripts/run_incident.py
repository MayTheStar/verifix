"""Run one simulated incident through the Verifix agent and print a readable trace."""
import argparse
import sys
from pathlib import Path

# Allow `python scripts/run_incident.py` from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verifix.agent import run_incident  # noqa: E402
from verifix.llm import MAX_TOTAL_TOKENS, total_tokens_used  # noqa: E402
from verifix.simulator import Simulator  # noqa: E402


def build(name: str, seed: int) -> Simulator:
    sim = Simulator(seed=seed)
    sim.step(3)
    if name == "payments_bad_deploy":
        sim.inject_bad_deploy("payments")
    elif name == "db_pool":
        sim.inject_db_pool_exhaustion()
    sim.step(5)
    return sim


def ask_human(action, args, reason) -> bool:
    print(f"\n   APPROVAL REQUIRED: {action} {args}\n   reason: {reason}")
    return input("   approve? [y/N] ").strip().lower() == "y"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("scenario", choices=["payments_bad_deploy", "db_pool"])
    p.add_argument("--seed", type=int, default=1)
    args = p.parse_args()

    sim = build(args.scenario, args.seed)
    result = run_incident(sim, approve_fn=ask_human)

    print("\n=== TRACE ===")
    for t in result.trace:
        if t["type"] == "read":
            print(f"[read] {t['tool']} {t['args']}")
        elif t["type"] == "action":
            print(f"[action] {t['action']} {t['args']}  confidence={t['confidence']}")
            print(f"         rationale: {t['rationale']}")
            print(f"         policy: {t['policy']} ({t['policy_reason']})  executed={t['executed']}")
            if t["executed"]:
                print(f"         verifier: {t['verdict']}  unhealthy={t['unhealthy']}")
        elif t["type"] == "finish":
            print(f"[finish] {t['args']}")

    print("\n=== RESULT ===")
    print(f"outcome            : {result.outcome}")
    print(f"verifier (truth)   : {result.final_status}")
    print(f"agent claimed fixed: {result.claimed_recovered}")
    print(f"llm calls          : {result.llm_calls} (cached: {result.cached_calls})")
    print(f"tokens this run    : prompt={result.prompt_tokens} completion={result.completion_tokens}")
    print(f"tokens cumulative  : {total_tokens_used()} / cap {MAX_TOTAL_TOKENS}")


if __name__ == "__main__":
    main()