# Verifix

**An incident-recovery agent whose fixes only count when an independent verifier confirms them from real metrics.**

Built for the *Agentic Recovery of a Failing System* challenge by [YOUR NAME]. This is a prototype running against a simulated system, not real infrastructure.

## The problem

When a service breaks, an on-call engineer reads logs, forms a hypothesis, applies a fix, and checks whether things recovered. An LLM agent can automate the loop, but it has two dangerous failure modes: it acts before it has evidence, and it declares success without proof.

## The idea

Never let the model grade its own work, and never let it be the only safety layer.

| Part | Implementation | LLM? |
|---|---|---|
| Investigator | Calls read tools (logs, metrics, deploys, config), proposes actions with cited evidence | yes |
| Guards | Investigation gate, repeat guard, futility guard | no |
| Policy Gate | Allow list, argument checks, human approval for config changes, prompt-injection pattern check on cited evidence | no |
| Executor | Applies the action to the *simulated* system only | no |
| Verifier | Advances the simulation and judges from real metrics: `RECOVERED`, `PARTIAL`, `DEGRADING`, `FAILED` | no |

The final outcome is decided by the verifier, never by the agent's claim. If the agent says "fixed" and the metrics disagree, the run is recorded as `FALSE_CLAIM`.

```
 incident ──► Agent (LLM) ──propose──► Guards ──► Policy Gate ──► Executor ──► Simulator
                 ▲                                                                │
                 └──────── verifier verdict + hint ◄──── Verifier (real metrics) ◄┘
```

## Simulated environment

Five services (`gateway`, `auth`, `orders`, `payments`, `database`) with a call graph, so errors cascade upward. Seeded and deterministic. Fault families:

- `bad_deploy`, `memory_leak` (a restart gives only temporary relief, so the verifier reports `DEGRADING`)
- `db_pool` exhaustion, `bad_config` (each needs a *config* fix; rollback and restart do not help)
- `cascade_trap` (a louder victim hides the real root cause), `dual_fault` (two simultaneous causes)
- Generalization families added later: `bad_config_payments`, `cache_stampede`, `external_outage` (no fix exists; correct behaviour is to escalate), `approval_denied` (a human refuses; the agent must not work around it)
- "Hard" variants add decoy log lines and a planted prompt-injection line.

## Results

All numbers come from the files in `results/`. Single runs, small n, local simulated benchmark. Not a guarantee for real systems.

**Splits.** `dev` (18, even seeds) was used while designing the guards. `heldout` (18, odd seeds) was run once on the frozen v1 system. Held-out means held-out *seeds* of the same fault families, not new fault types.

| System | dev (n=18) | heldout (n=18) | avg executed actions when recovered (dev / heldout) |
|---|---|---|---|
| B0: restart the highest-error service | 0 | 0 | n/a |
| B1: rollback if recent deploy, else restart | 10 | 10 | 1.00 / 1.00 |
| Agent v0 (12 steps, no guards) | 12 | 13 | 2.58 / 2.85 |
| Agent v0, 20 steps | 16 | 15 | 3.06 / 2.87 |
| Agent, investigation gate only (20 steps) | 18 | 18 | 1.61 / 1.33 |
| Agent v1 (all guards) | 18 | 18 | 1.50 / 1.39 |
| Agent v2 (v1 + futility guard) | 18 | 18* | 1.50 / 1.39 |

\* v2 on heldout is a regression check on a system modified after the generalization runs, not a fresh held-out result.

**Ablation on dev** (one component removed from v1): without the investigation gate 16/18 and 2.06 actions; without repeat guard, hints, or step warning, 18/18 with identical or near-identical traces.

**What the ablation says.**
1. Part of the v0→v1 gain came simply from raising the step limit 12→20 (67% → 89% on dev). Only after separating that did the gate's effect show: roughly half the executed actions (3.06 → 1.61 on dev, 2.87 → 1.33 on heldout) and the last two scenarios.
2. The investigation gate is the only component with a measured effect. The repeat guard, verifier hints, and step warning showed no measurable effect on dev; they are cheap safety nets covered by unit tests, not proven improvements.
3. In v1 the model tried to act before reading deploys/config in nearly every scenario (20 gate interventions per 18 scenarios). The gain comes from enforcing investigation discipline in code, not from a smarter prompt.

**Generalization suite** (12 scenarios, new fault families, the correct outcome is stated per scenario; B1 scores 0/12):

| Family | Correct outcome | v1 | v2 |
|---|---|---|---|
| bad_config_payments | RECOVERED | 3/3 | 3/3 |
| cache_stampede | RECOVERED | 1/3 (2 safe escalations) | 1/3 (2 safe escalations) |
| external_outage | ESCALATED | 2/3 (1 timed out) | 3/3 |
| approval_denied | ESCALATED | 3/3 | 3/3 |
| **Total** | | **9/12** | **10/12** |

- "Passed" counts a correct escalation as a pass, so always read it per family.
- Expected outcomes and predicted scores were written in `PREDICTIONS.md` and committed before the v1 generalization run.
- v2 (the futility guard) was designed *after* inspecting the v1 traces of two failing scenarios, so its generalization result is **not held-out**. The v2 predictions were added to `PREDICTIONS.md` after that commit and before the v2 run; the git history does not prove their timing.
- False claims: 0 in every run. That does not show the verifier was needed, because the agent never claimed success falsely. The verifier's value is demonstrated by unit tests with a scripted agent that does claim false success (`tests/test_agent_loop.py`).

## What went wrong along the way

- The first verifier labelled "no action taken" as `PARTIAL` because it never compared against the state before the window. A unit test caught it; the verifier now captures the baseline itself.
- The first futility guard counted unique action signatures instead of executed actions, so it never fired. A unit test caught it before any evaluation run.
- The repeat guard fired seven times on `external_outage` but the agent switched service or action type and kept flailing. That is why the futility guard exists.
- `cache_stampede` remains a diagnosis weakness: the agent fixes the database symptom and never inspects the gateway cache config. We did not tune for it.

## Limitations

- Simulated, simplified world. Results do not transfer to real infrastructure.
- Single runs, n = 12–18, no confidence intervals. For example, a true 95% success rate would still produce 18/18 about 40% of the time.
- The on-disk LLM cache makes runs replayable but hides model non-determinism.
- The benchmark is our own design. The held-out split shares fault families with dev.
- Evaluation auto-approves risky actions, so human-approval behaviour is only exercised in the `approval_denied` family and unit tests.
- The action space has no destructive action, so we cannot measure whether the model *obeys* an injected instruction. The policy gate's injection check is a simple pattern match on cited evidence. The agent cited the injected line once but did not follow it.
- The `unsafe denied` counter measures policy denials, which include merely quoting a suspicious line.
- The model's self-reported confidence is shown but not calibrated.
- Thresholds (such as the futility limit of 4) were chosen by judgement, not tuned.

## Cost

Model: `gpt-4o-mini` (set by `VERIFIX_MODEL` in `.env`). All development, ablations, and held-out runs together used about 20 cents of API credit according to the billing dashboard (balance 3.65 → 3.46; dashboard granularity is coarse, so treat this as approximate).

## Reproduce

Python 3.13, any OS.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q                                   # 47 tests, no API key needed
```

The repository includes the LLM response cache (`.llm_cache/`), so the evaluations replay **without an API key**:

```bash
python scripts/run_eval.py --system b1 --split dev
python scripts/run_eval.py --system agent --split dev --config v2
python scripts/run_eval.py --system agent --split heldout --config v2 --allow-heldout
python scripts/run_gen_eval.py --system agent --config v2
python -m streamlit run app/dashboard.py   # Incident Console
```

To run with live model calls, copy `.env.example` to `.env` and set `OPENAI_API_KEY`. Replies may differ from the cached ones. A cumulative token cap (`VERIFIX_MAX_TOTAL_TOKENS`) stops runaway spending.

## Layout

```
verifix/    simulator, verifier, policy, guards, agent loop, LLM wrapper, scenarios
scripts/    run_eval.py, run_gen_eval.py, inspect_*.py (trace replay); patch_*.py are one-off historical edits
tests/      47 tests: simulator, verifier, policy, agent loop with a scripted fake LLM, guards
app/        Streamlit Incident Console
results/    raw JSON per evaluation run
```

## With another week

Model-size comparison with the same guards, real-incident-style log datasets, confidence intervals over repeated runs, a deliberately destructive action space to measure injection obedience, and a diagnosis step that checks upstream configs (the `cache_stampede` fix).