"""Replay dev scenarios through the agent and print the full trace.

If the code and prompts are unchanged, calls replay from the LLM cache (free).
Heldout scenarios are refused on purpose.
Usage: python scripts/inspect_scenario.py <scenario_id> [<scenario_id> ...]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verifix.agent import run_incident  # noqa: E402
from verifix.scenarios import all_scenarios, build  # noqa: E402


def short(x, n=170):
    s = str(x)
    return s if len(s) <= n else s[:n] + "..."


def main(ids):
    by_id = {s.id: s for s in all_scenarios()}
    for sid in ids:
        if sid not in by_id:
            raise SystemExit(f"unknown scenario id: {sid}")
        sc = by_id[sid]
        if sc.split == "heldout":
            raise SystemExit("refusing to inspect heldout scenarios")

        sim = build(sc)
        truth = sim.ground_truth_root_causes()   # for us only; the agent never sees this
        r = run_incident(sim, approve_fn=lambda a, args, reason: True)

        print("=" * 100)
        print(f"{sid} -> outcome={r.outcome} verifier={r.final_status} "
              f"llm_calls={r.llm_calls} cached={r.cached_calls}")
        print("GROUND TRUTH:", short(truth, 300))
        for t in r.trace:
            if t["type"] == "read":
                print(f"  [read] {t['tool']} {t['args']}")
            elif t["type"] == "action":
                print(f"  [action] {t['action']} {t['args']} policy={t['policy']} "
                      f"executed={t['executed']} verdict={t.get('verdict')}")
                print(f"           rationale: {short(t['rationale'])}")
                for e in t["evidence"][:2]:
                    print(f"           evidence: {short(e, 120)}")
            elif t["type"] == "finish":
                print(f"  [finish] {short(t['args'], 300)}")
        if not any(t["type"] == "finish" for t in r.trace):
            print("  (agent never called finish: it ran out of steps)")


if __name__ == "__main__":
    main(sys.argv[1:])