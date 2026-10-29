"""Run the generalization suite once. Usage:
    python scripts/run_gen_eval.py --system b1
    python scripts/run_gen_eval.py --system agent --config v1
"""
import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verifix.agent import CONFIGS  # noqa: E402
from verifix.baselines import run_b0, run_b1  # noqa: E402
from verifix.gen_scenarios import build_gen, gen_scenarios  # noqa: E402


def run_one(system, sc, config_name):
    sim = build_gen(sc)
    if system in ("b0", "b1"):
        r = (run_b0 if system == "b0" else run_b1)(sim)
        return {"outcome": r.outcome, "final": r.final_status, "n_actions": len(r.actions),
                "false_claim": False, "tokens": 0}
    from verifix.agent import run_incident
    r = run_incident(sim, approve_fn=lambda a, args, reason: sc.approve, config=CONFIGS[config_name])
    actions = [t for t in r.trace if t["type"] == "action"]
    return {"outcome": r.outcome, "final": r.final_status,
            "n_actions": sum(1 for a in actions if a["executed"]),
            "false_claim": r.outcome == "FALSE_CLAIM",
            "tokens": r.prompt_tokens + r.completion_tokens}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--system", required=True, choices=["b0", "b1", "agent"])
    p.add_argument("--config", default="v1", choices=list(CONFIGS))
    a = p.parse_args()

    rows = []
    for sc in gen_scenarios():
        r = run_one(a.system, sc, a.config)
        r.update(id=sc.id, fault=sc.fault, expected=sc.expected, passed=(r["outcome"] == sc.expected))
        rows.append(r)
        print(f"{sc.id:<34} expected={sc.expected:<10} got={r['outcome']:<11} "
              f"{'PASS' if r['passed'] else 'MISS'} actions={r['n_actions']}")

    n = len(rows)
    print("\n=== SUMMARY (generalization suite) ===")
    print(f"system={a.system} config={a.config if a.system == 'agent' else '-'} n={n}")
    print(f"passed (outcome == expected): {sum(r['passed'] for r in rows)}/{n}")
    by = defaultdict(list)
    for r in rows:
        by[r["fault"]].append(r["passed"])
    for k, v in by.items():
        print(f"  {k:<22} {sum(v)}/{len(v)}")
    print(f"outcomes     : {dict(Counter(r['outcome'] for r in rows))}")
    print(f"false claims : {sum(r['false_claim'] for r in rows)}/{n}")
    print(f"tokens       : {sum(r['tokens'] for r in rows)}")

    Path("results").mkdir(exist_ok=True)
    out = Path("results") / f"gen_{a.system}_{a.config if a.system == 'agent' else 'rule'}_{int(time.time())}.json"
    out.write_text(json.dumps(rows, indent=2))
    print(f"saved: {out}")


if __name__ == "__main__":
    main()