"""Verifix Incident Console: replay an incident and inspect every decision."""
import html
import json
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)  # the LLM cache path is relative to the project root

from verifix.agent import CONFIGS, run_incident  # noqa: E402
from verifix.gen_scenarios import build_gen, gen_scenarios  # noqa: E402
from verifix.scenarios import all_scenarios, build  # noqa: E402
from verifix.simulator import SERVICES  # noqa: E402

st.set_page_config(page_title="Verifix Incident Console", page_icon="🛡️", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 1.6rem; max-width: 1250px;}
.vx-hero h1 {margin: 0; font-size: 2.1rem;}
.vx-hero p {margin: .2rem 0 1rem 0; opacity: .75;}
.vx-pipe {display: flex; gap: 8px; margin: .4rem 0 1.2rem 0; flex-wrap: wrap;}
.vx-stage {flex: 1; min-width: 150px; padding: 10px 12px; border-radius: 10px;
  border: 1px solid rgba(128,128,128,.35); background: rgba(128,128,128,.07);}
.vx-stage b {display: block; font-size: .95rem;}
.vx-stage span {font-size: .78rem; opacity: .7;}
.vx-banner {padding: 14px 18px; border-radius: 12px; margin: .5rem 0 1rem 0;
  font-size: 1.05rem; border: 1px solid;}
.vx-ok   {background: rgba(46,160,67,.14);  border-color: rgba(46,160,67,.6);}
.vx-warn {background: rgba(210,153,34,.16); border-color: rgba(210,153,34,.7);}
.vx-bad  {background: rgba(248,81,73,.14);  border-color: rgba(248,81,73,.6);}
.vx-step {border-left: 5px solid #888; padding: 8px 12px; margin: 7px 0;
  border-radius: 6px; background: rgba(128,128,128,.07); font-size: .92rem;}
.vx-read    {border-color: #8b949e;}
.vx-allow   {border-color: #2ea043;}
.vx-approve {border-color: #d29922;}
.vx-deny    {border-color: #f85149;}
.vx-blocked {border-color: #a371f7;}
.vx-finish  {border-color: #388bfd;}
.vx-tag {display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: .72rem;
  border: 1px solid rgba(128,128,128,.5); margin-left: 6px;}
.vx-muted {opacity: .7; font-size: .85rem;}

.vx-hero {padding: 18px 22px; border-radius: 14px; margin-bottom: 14px;
  background: linear-gradient(135deg, rgba(79,140,255,.22), rgba(163,113,247,.14));
  border: 1px solid rgba(79,140,255,.35);}
[data-testid="stMetric"] {background: rgba(128,128,128,.08); padding: 12px 14px;
  border-radius: 12px; border: 1px solid rgba(128,128,128,.25);}
.vx-stage {transition: transform .15s ease;}
.vx-stage:hover {transform: translateY(-2px);}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="vx-hero">
  <h1>🛡️ Verifix <span style="font-weight:400;opacity:.6">Incident Console</span></h1>
  <p>An incident-recovery agent. A fix only counts when an independent verifier confirms it from real metrics.</p>
</div>
<div class="vx-pipe">
  <div class="vx-stage"><b>1 · Investigate</b><span>LLM agent reads logs, metrics, deploys, config</span></div>
  <div class="vx-stage"><b>2 · Guard</b><span>Deterministic gates: investigation, repeat, futility</span></div>
  <div class="vx-stage"><b>3 · Policy</b><span>Allow / needs human approval / deny</span></div>
  <div class="vx-stage"><b>4 · Verify</b><span>Real metrics decide, not the agent's words</span></div>
</div>
""", unsafe_allow_html=True)

# ---------- scenario catalogue ----------
CATALOG = {"dev": [], "heldout": [], "generalization": []}
for s in all_scenarios():
    CATALOG[s.split].append(("std", s))
for g in gen_scenarios():
    CATALOG["generalization"].append(("gen", g))

SUITE_HELP = {
    "dev": "Used while designing the guards.",
    "heldout": "Run once on the frozen v1 system.",
    "generalization": "New fault families, including cases where the correct outcome is to escalate.",
}

with st.sidebar:
    st.header("Run an incident")
    group = st.radio("Suite", list(CATALOG))
    st.caption(SUITE_HELP[group])
    options = {sc.id: (kind, sc) for kind, sc in CATALOG[group]}
    sid = st.selectbox("Scenario", list(options))
    cfg = st.selectbox("Agent config", ["v2", "v1", "gate-only", "v0", "v0-20steps"])
    approve = st.toggle("Simulated human approves risky actions", value=True,
                        help="Ignored for approval_denied scenarios (they always deny).")
    run = st.button("Run incident", type="primary", use_container_width=True)
    st.caption("The simulator runs live. LLM replies replay from the on-disk cache (free); "
               "a never-seen prompt makes a real API call.")

kind, sc = options[sid]

if run:
    with st.spinner("Agent investigating..."):
        sim = build_gen(sc) if kind == "gen" else build(sc)
        truth = sim.ground_truth_root_causes()
        decision = sc.approve if kind == "gen" else approve
        res = run_incident(sim, approve_fn=lambda a, args, reason: decision, config=CONFIGS[cfg])
        history = [{"tick": s["tick"], **{n: s[n]["error_rate"] for n in SERVICES}}
                   for s in sim.metric_history]
        st.session_state["run"] = dict(kind=kind, sc=sc, res=res, truth=truth,
                                       history=history, cfg=cfg)


def esc(x) -> str:
    return html.escape(str(x))


def banner(res) -> None:
    if res.outcome == "RECOVERED":
        st.markdown('<div class="vx-banner vx-ok">✅ <b>Recovered.</b> The independent verifier '
                    'confirmed it from real metrics.</div>', unsafe_allow_html=True)
    elif res.outcome == "ESCALATED":
        st.markdown('<div class="vx-banner vx-warn">🙋 <b>Escalated to a human.</b> The agent stopped '
                    'and did not claim success.</div>', unsafe_allow_html=True)
    elif res.outcome == "FALSE_CLAIM":
        st.markdown('<div class="vx-banner vx-bad">🚨 <b>False claim.</b> The agent said recovered but '
                    'the verifier disagrees.</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="vx-banner vx-bad">❌ <b>{esc(res.outcome)}.</b> The agent did not '
                    'finish the job.</div>', unsafe_allow_html=True)


def timeline(res) -> None:
    for i, t in enumerate(res.trace, 1):
        if t["type"] == "read":
            st.markdown(f'<div class="vx-step vx-read">{i} · 🔍 <b>{esc(t["tool"])}</b> '
                        f'<span class="vx-muted">{esc(t["args"])}</span></div>', unsafe_allow_html=True)
        elif t["type"] == "action":
            cls = {"ALLOW": "vx-allow", "NEEDS_APPROVAL": "vx-approve", "DENY": "vx-deny",
                   "BLOCKED": "vx-blocked"}.get(t["policy"], "vx-read")
            label = {"ALLOW": "allowed", "NEEDS_APPROVAL": "needs approval",
                     "DENY": "denied by policy", "BLOCKED": "blocked by guard"}.get(t["policy"], t["policy"])
            verdict = f'<span class="vx-tag">verifier: {esc(t["verdict"])}</span>' if t.get("verdict") else ""
            ran = "executed" if t["executed"] else "not executed"
            st.markdown(f'<div class="vx-step {cls}">{i} · ⚙️ <b>{esc(t["action"])}</b> '
                        f'<span class="vx-muted">{esc(t["args"])}</span>'
                        f'<span class="vx-tag">{label}</span><span class="vx-tag">{ran}</span>{verdict}'
                        f'</div>', unsafe_allow_html=True)
            with st.expander(f"Why? (step {i})"):
                st.write(f"**Agent rationale:** {t['rationale']}")
                st.write(f"**Policy / guard reason:** {t['policy_reason']}")
                st.write(f"**Self-reported confidence:** {t['confidence']} "
                         "(the model's own number, not calibrated)")
                if "approved" in t:
                    st.write(f"**Human approval:** {'granted' if t['approved'] else 'refused'}")
                if t["evidence"]:
                    st.write("**Evidence the agent cited:**")
                    st.code("\n".join(t["evidence"]))
        elif t["type"] == "finish":
            f = t["args"]
            st.markdown(f'<div class="vx-step vx-finish">{i} · 🏁 <b>finish</b> '
                        f'<span class="vx-tag">escalate={esc(f.get("escalate"))}</span>'
                        f'<span class="vx-tag">claims_recovered={esc(f.get("claims_recovered"))}</span>'
                        f'<br><span class="vx-muted">{esc(f.get("summary", ""))}</span></div>',
                        unsafe_allow_html=True)
    if not any(t["type"] == "finish" for t in res.trace):
        st.warning("The agent never called finish (it ran out of steps).")


def load_results() -> pd.DataFrame:
    """Latest result file per (suite, system, config). Numbers come straight from results/*.json."""
    latest = {}
    for f in sorted((ROOT / "results").glob("*.json")):
        parts = f.stem.split("_")
        try:
            if parts[0] == "gen":
                suite, system, conf = "generalization", parts[1], parts[2]
            else:
                suite, system = parts[1], parts[0]
                conf = parts[2] if len(parts) == 4 else "-"
            d = json.loads(f.read_text())
        except Exception:  # noqa: BLE001
            continue
        if d:
            latest[(suite, system, conf)] = (f.name, d)
    rows = []
    for (suite, system, conf), (name, d) in latest.items():
        n = len(d)
        rows.append({
            "suite": suite, "system": system, "config": conf, "n": n,
            "recovered": sum(r.get("outcome") == "RECOVERED" for r in d),
            "passed (gen only)": sum(r["passed"] for r in d) if "passed" in d[0] else None,
            "false claims": sum(bool(r.get("false_claim")) for r in d),
            "file": name,
        })
    return pd.DataFrame(rows)


tab_run, tab_results, tab_how = st.tabs(["Incident run", "Benchmark results", "How it works"])

with tab_run:
    data = st.session_state.get("run")
    if not data:
        st.info("Pick a scenario in the sidebar and press **Run incident**. "
                "Good first picks: `generalization` → `external_outage-s206`, then `dev` → `cascade_trap-payments-s128`.")
    else:
        res, sc = data["res"], data["sc"]
        banner(res)
        if data["kind"] == "gen":
            ok = res.outcome == sc.expected
            st.markdown(f"**Correct outcome for this scenario:** `{sc.expected}` → "
                        f"{'✅ PASS' if ok else '⚠️ MISS'}")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Verifier verdict", res.final_status, help="The truth, from real metrics.")
        c2.metric("Agent claimed fixed", "yes" if res.claimed_recovered else "no")
        c3.metric("Executed actions",
                  sum(1 for t in res.trace if t["type"] == "action" and t["executed"]))
        c4.metric("Guard / policy stops",
                  sum(1 for t in res.trace if t["type"] == "action" and not t["executed"]))
        left, right = st.columns([3, 2])
        with left:
            st.subheader("Decision timeline")
            timeline(res)
        with right:
            st.subheader("Error rate per service")
            st.line_chart(pd.DataFrame(data["history"]).set_index("tick"))
            st.caption(f"Config: {data['cfg']} · LLM calls: {res.llm_calls} (cached {res.cached_calls})")
            with st.expander("Ground truth (never shown to the agent)"):
                st.json(data["truth"])
                st.caption("Captured before the run, because a successful fix removes the fault.")

with tab_results:
    df = load_results()
    if df.empty:
        st.warning("No result files found in results/.")
    else:
        st.subheader("Recovery rate by system (latest file per setting)")
        for suite in ["dev", "heldout"]:
            sub = df[df["suite"] == suite].copy()
            if sub.empty:
                continue
            sub["label"] = sub["system"] + " " + sub["config"]
            sub["recovery %"] = (100 * sub["recovered"] / sub["n"]).round(0)
            st.markdown(f"**{suite}** (n = {int(sub['n'].iloc[0])})")
            st.bar_chart(sub.set_index("label")["recovery %"])
        st.subheader("All recorded runs")
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.caption("Local simulated benchmark, single runs. Not a guarantee for real systems. "
                   "dev was used to design the guards; heldout ran once on the frozen system; "
                   "generalization results for v2 are NOT held-out. In the generalization suite, "
                   "'passed' counts a correct escalation as a pass, so read it per family.")

with tab_how:
    st.subheader("Four separate parts")
    a, b = st.columns(2)
    with a:
        st.markdown("**Simulator** (`verifix/simulator.py`)  \nA fake system of 5 services that produces "
                    "logs and metrics, with injectable faults. This is the patient. It knows the real "
                    "root cause; the agent never sees it.")
        st.markdown("**Agent** (`verifix/agent.py`)  \nAn LLM that investigates through tools and proposes "
                    "actions. It can be wrong, so it is never trusted on its own.")
    with b:
        st.markdown("**Policy Gate + guards** (`policy.py`, `guards.py`)  \nPlain code, no LLM. Blocks "
                    "unknown or risky actions, requires approval for config changes, forces investigation "
                    "before acting, and stops flailing.")
        st.markdown("**Verifier** (`verifier.py`)  \nPlain code. Advances the simulation and judges from "
                    "real metrics: RECOVERED, PARTIAL, DEGRADING, or FAILED.")
    st.markdown("**This console** only runs the above and displays it. It contains no decision logic.")
    st.subheader("What is deterministic, and what is the model?")
    st.markdown("- **Model:** reading evidence, forming a hypothesis, choosing an action.\n"
                "- **Code:** permissions, approvals, guards, and the final verdict.")
    st.subheader("Known limits")
    st.markdown("- Simulated environment, not real infrastructure.\n"
                "- Small benchmark, single runs, no confidence intervals.\n"
                "- `cache_stampede` diagnosis is a known weakness (the agent escalates safely instead).\n"
                "- Confidence values are self-reported by the model and not calibrated.")