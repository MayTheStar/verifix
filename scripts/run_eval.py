"""Evaluation harness. Usage:
    python scripts/run_eval.py --system b1 --split dev
    python scripts/run_eval.py --system agent --split dev --config v1
heldout is protected: it needs --allow-heldout.
"""
import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verifix.agent import CONFIGS  # noqa: E402
from verifix.baselines import run_b0, run_b1  # noqa: E402
from verifix.scenarios import all_scenarios, build  # noqa: E402

RESULTS_DIR = Path("results")


def run_one(system: str, sc, config_name: str):
    sim = build(sc)
    if system in ("b0", "b1"):
        r = (run_b0 if system == "b0" else run_b1)(sim)
        return {"outcome": r.outcome, "final": r.final_status, "n_actions": len(r.actions),
                "unsafe": 0, "injection_cited": 0, "blocked": 0, "false_claim": False,
                "tokens": 0, "calls": 0, "cached": 0}
    from verifix.agent import run_incident
    r = run_incident(sim, approve_fn=lambda a, args, reason: True, config=CONFIGS[config_name])
    actions = [t for t in r.trace if t["type"] == "action"]
    denied = [a for a in actions if a["policy"] == "DENY"]
    return {"outcome": r.outcome, "final": r.final_status,
            "n_actions": sum(1 for a in actions if a["executed"]),
            "unsafe": len(denied),
            "injection_cited": sum(1 for a in denied if "injection" in a["policy_reason"]),
            "blocked": sum(1 for a in actions if a["policy"] == "BLOCKED"),
            "false_claim": r.outcome == "FALSE_CLAIM",
            "tokens": r.prompt_tokens + r.completion_tokens,
            "calls": r.llm_calls, "cached": r.cached_calls}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--system", required=True, choices=["b0", "b1", "agent"])
    p.add_argument("--split", required=True, choices=["dev", "heldout"])
    p.add_argument("--config", default="v0", choices=list(CONFIGS))
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--allow-heldout", action="store_true")
    p.add_argument("--tag", default="")
    a = p.parse_args()

    if a.split == "heldout" and not a.allow_heldout:
        raise SystemExit("heldout is protected. Pass --allow-heldout only for the final run.")

    scs = [s for s in all_scenarios() if s.split == a.split]
    if a.limit:
        scs = scs[: a.limit]

    rows = []
    for sc in scs:
        r = run_one(a.system, sc, a.config)
        r.update(id=sc.id, fault=sc.fault, hard=sc.injection)
        rows.append(r)
        print(f"{sc.id:<38} {r['outcome']:<11} actions={r['n_actions']} "
              f"denied={r['unsafe']} blocked={r['blocked']}")

    n = len(rows)
    rec = sum(r["outcome"] == "RECOVERED" for r in rows)
    rec_rows = [r for r in rows if r["outcome"] == "RECOVERED"]
    print("\n=== SUMMARY ===")
    print(f"system={a.system} config={a.config if a.system == 'agent' else '-'} split={a.split} n={n}")
    print(f"recovered     : {rec}/{n} = {rec/n:.0%}")
    print(f"outcomes      : {dict(Counter(r['outcome'] for r in rows))}")
    print(f"false claims  : {sum(r['false_claim'] for r in rows)}/{n}")
    if rec_rows:
        print(f"avg executed actions when recovered: "
              f"{sum(r['n_actions'] for r in rec_rows) / len(rec_rows):.2f}")
    print(f"policy denied : {sum(r['unsafe'] for r in rows)} "
          f"(injection cited: {sum(r['injection_cited'] for r in rows)})")
    print(f"guard blocked : {sum(r['blocked'] for r in rows)}")
    print(f"llm calls     : {sum(r['calls'] for r in rows)} (cached {sum(r['cached'] for r in rows)})")
    print(f"tokens        : {sum(r['tokens'] for r in rows)} (includes replayed cache hits)")

    RESULTS_DIR.mkdir(exist_ok=True)
    tag = a.tag or (a.config if a.system == "agent" else "")
    out = RESULTS_DIR / f"{a.system}_{a.split}{('_' + tag) if tag else ''}_{int(time.time())}.json"
    out.write_text(json.dumps(rows, indent=2))
    print(f"saved: {out}")


if __name__ == "__main__":
    main()