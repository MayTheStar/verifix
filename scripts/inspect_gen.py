"""Replay generalization scenarios with the v1 config and print the trace (free if cached)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verifix.agent import V1, run_incident  # noqa: E402
from verifix.gen_scenarios import build_gen, gen_scenarios  # noqa: E402


def short(x, n=170):
    s = str(x)
    return s if len(s) <= n else s[:n] + "..."


def main(ids):
    by_id = {s.id: s for s in gen_scenarios()}
    for sid in ids:
        sc = by_id[sid]
        sim = build_gen(sc)
        truth = sim.ground_truth_root_causes()
        r = run_incident(sim, approve_fn=lambda a, args, reason: sc.approve, config=V1)
        print("=" * 100)
        print(f"{sid} -> outcome={r.outcome} llm_calls={r.llm_calls} cached={r.cached_calls}")
        print("GROUND TRUTH:", short(truth, 250))
        for t in r.trace:
            if t["type"] == "read":
                print(f"  [read] {t['tool']} {t['args']}")
            elif t["type"] == "action":
                print(f"  [action] {t['action']} {t['args']} policy={t['policy']} "
                      f"executed={t['executed']} verdict={t.get('verdict')}")
                print(f"           rationale: {short(t['rationale'])}")
            elif t["type"] == "finish":
                print(f"  [finish] {short(t['args'], 400)}")


if __name__ == "__main__":
    main(sys.argv[1:])