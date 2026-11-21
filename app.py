import os
from dataclasses import replace, asdict
from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import ui
from ui import GREEN, AMBER, BLUE, RED, GREY, style_fig, header, section, kpis, chips
from engine.models import ProcessInputs, EconomicInputs, calculate_technical, calculate_economics, MODEL_REGISTRY
from engine.predict import BiocharPredictor, CLASSES, TARGETS, stable_fraction_from_hc
from engine.design import FEEDSTOCKS, design_inputs, evaluate_design, search_designs, tornado
from engine.processes import PROCESSES
from engine.particle import ParticleParams, simulate_particle, verify_conduction
from engine.pathways import pathways_df, SRC as PATH_SRC
from engine.thermo import HAVE_COOLPROP
from engine.mathdocs import BY_PAGE
from ai.llm import ask, list_models, LLMError, DEFAULT_MODEL

st.set_page_config(page_title="MENA Biochar Platform", page_icon="\u267b\ufe0f", layout="wide", initial_sidebar_state="expanded")
ui.inject()
S = st.session_state

@st.cache_resource(show_spinner="Training the prediction models on the literature dataset (one-off, ~10 s)...")
def get_predictor(): return BiocharPredictor.train(run_cv=True)

@st.cache_data(show_spinner="Running particle simulation...")
def sim_cached(pp_dict, t_end, dt): return simulate_particle(ParticleParams(**pp_dict), t_end, dt)

@st.cache_data(show_spinner=False)
def verification_cached(): return verify_conduction()

# ------------------------------------------------------------------ state
S.setdefault("process", ProcessInputs()); S.setdefault("economics", EconomicInputs(carbon_credit_usd_tco2e=0.0))
S.setdefault("design", {"process": "slow_pyrolysis", "feed": "Date palm residues", "htt": 540.0, "dur": 120.0, "hr": 10.0, "liquid_share": 0.55})
S.design.setdefault("process", "slow_pyrolysis")
S.setdefault("yield_source", "Predicted (data-driven)")
S.setdefault("particle", {"d": 20.0, "h": 50.0, "rho": 600.0, "kv": 0.15, "kc": 0.10, "cpv": 1500.0, "cpc": 1100.0, "lnA": 22.2, "E": 141.2, "dH": 0.0})
S.setdefault("chat", {})
PRED = lambda: S.yield_source.startswith("Predicted")
PROC = lambda: PROCESSES[S.design["process"]]

def fmt(v, unit=""):
    if v is None or (isinstance(v, float) and np.isnan(v)): return "n/a"
    return f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.2f}"

def get_key():
    k = S.get("groq_key") or ""
    if not k:
        try: k = st.secrets.get("GROQ_API_KEY", "")
        except Exception: k = ""
    return k or os.environ.get("GROQ_API_KEY", "")

def source_note(model_ids):
    for mid in model_ids:
        m = MODEL_REGISTRY[mid]
        with st.expander(f"{mid} \u00b7 {m['name']}"):
            st.write(m["method"]); st.code(m["equation"], language=None)
            st.markdown(f"**Source:** [{m['source']}]({m['url']})"); st.caption(m["status"])

def render_math(key):
    for kind, text in BY_PAGE[key]:
        (st.markdown if kind == "md" else st.latex)(text)

def log_view(df, name):
    st.dataframe(df, width="stretch", hide_index=True)
    st.download_button("Download log (CSV)", df.to_csv(index=False).encode("utf-8"), f"{name}.csv", "text/csv", key=f"dl_{name}")
    st.caption("Regenerated from the current inputs on every run. Each row names the equation, the inputs used and the model or assumption behind it.")

# ------------------------------------------------------------------ scenario pipeline
def set_process(name):
    """Switch process type and reset temperature, residence time and particle defaults to that process."""
    pr = PROCESSES[name]; d = S.design
    d.update({"process": name, "htt": float(pr["T_default"]), "dur": float(pr["dur_default"])})
    S.particle["d"], S.particle["h"] = pr["particle_defaults"]["d"], pr["particle_defaults"]["h"]
    if not PRED(): S.process = replace(S.process, process_type=name)

def current_scenario():
    if PRED():
        d = S.design
        return design_inputs(get_predictor(), d["feed"], d["htt"], d["dur"], d["hr"], S.process, S.economics, d["liquid_share"], process=d["process"])
    return replace(S.process, process_type=S.design["process"]), S.economics, None

def make_pp(htt, yc, process=None):
    q = S.particle; process = process or S.design["process"]
    dd = q["d"] if process == S.design["process"] else PROCESSES[process]["particle_defaults"]["d"]
    hh = q["h"] if process == S.design["process"] else PROCESSES[process]["particle_defaults"]["h"]
    return ParticleParams(diameter_mm=dd, T_inf_C=float(htt), h_W_m2K=hh, char_mass_fraction=float(yc), k_virgin=q["kv"], k_char=q["kc"], rho_virgin=q["rho"],
                          cp_virgin=q["cpv"], cp_char=q["cpc"], ln_A=q["lnA"], E_kJ_mol=q["E"], dH_J_kg=q["dH"])

def pipeline():
    p, e, pr = current_scenario(); proc = PROC()
    pp = make_pp(p.reactor_temp_C, p.char_yield_dry); dur_s = S.design["dur"] * 60
    sim = None
    if proc["particle"] != "none":
        t_end = float(min(max(dur_s, 600 if proc["particle"] == "full" else 1200), 14400))
        sim = sim_cached(asdict(pp), t_end, 0.1 if t_end <= 600 else (0.5 if t_end <= 3600 else 1.0))
    t = calculate_technical(p); ec = calculate_economics(t, p, e)
    return dict(p=p, e=e, pr=pr, pp=pp, sim=sim, t=t, ec=ec, dur_min=S.design["dur"], proc=proc)

def breakeven_carbon_price(ec, t):
    rem = t["net_removal_proxy_tco2e_y"]
    if rem <= 0: return None
    return max(0.0, (ec["annualised_capex_usd_y"] + ec["operating_cost_usd_y"] - (ec["total_revenue_usd_y"] - ec["carbon_revenue_usd_y"])) / rem)

def status_checks(R):
    t, sim, pr, proc = R["t"], R["sim"], R["pr"], R["proc"]; c = []
    c.append(("Mass balance closes", "ok" if abs(t["mass_balance_residual_t_y"]) < 1e-6 else "bad"))
    c.append((f"Carbon balance: {t['carbon_retained_fraction']:.0%} of feed C in char", "ok" if t["carbon_balance_ok"] else "bad"))
    if proc["particle"] == "full" and sim is not None:
        if sim["t_target_s"] is None: c.append(("Particle never reaches 95% conversion", "bad"))
        elif sim["t_target_s"] / 60 <= R["dur_min"]: c.append((f"Particle converts in {sim['t_target_s']/60:.2g} min (residence {R['dur_min']:.2g})", "ok"))
        else: c.append((f"Particle needs {sim['t_target_s']/60:.2g} min > residence {R['dur_min']:.2g}", "bad"))
    elif proc["particle"] == "heatup" and sim is not None:
        c.append((f"Particle centre heated in {(sim['t_center_within_5K_s'] or float('nan'))/60:.2g} min", "ok" if sim["t_center_within_5K_s"] else "warn"))
    else: c.append(("Particle model not applicable", "na"))
    c.append(("Heat self-sufficient" if t["heat_deficit_GJ_y"] <= 0 else "External heat needed", "ok" if t["heat_deficit_GJ_y"] <= 0 else "warn"))
    if proc.get("max_moisture") and R["p"].moisture_wet_basis > proc["max_moisture"]: c.append((f"Feed moisture above {proc['max_moisture']:.0%} limit", "bad"))
    if S.design["process"] != "slow_pyrolysis": c.append(("Screening-level process data", "warn"))
    elif pr and pr["extrapolating"]: c.append(("Predictor extrapolating", "warn"))
    c.append((f"Solver verified ({verification_cached()['max_error_pct']:.2f}% vs analytical)", "ok" if verification_cached()["max_error_pct"] < 0.5 else "bad"))
    return c

def _r(o):
    if isinstance(o, float): return float(f"{o:.4g}")
    if isinstance(o, dict): return {k: _r(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)): return [_r(v) for v in o]
    return o

def snapshot(R, parts):
    t, ec, p, sim, proc = R["t"], R["ec"], R["p"], R["sim"], R["proc"]
    out = {"scenario": {"process": proc["label"], "process_status": proc["status"], "feedstock": S.design["feed"] if PRED() else "manual inputs", "HTT_C": p.reactor_temp_C, "residence_min": R["dur_min"]},
           "status_checks": [f"{a} [{b}]" for a, b in status_checks(R)],
           "assumption_status": "Costs, prices, carbon price, liquid/gas split, particle properties, feed carbon, HTC lines and the H/C permanence map are PLACEHOLDER or typical values, not sourced data."}
    if "prediction" in parts and R["pr"]:
        pr = R["pr"]; out["prediction"] = {"yield_pct": pr["Yield"], "carbon_pct": pr["C"], "H_C": pr["H_C"], "stable_fraction": p.stable_carbon_fraction, "extrapolating": pr["extrapolating"],
                                            "cv_r2_yield": get_predictor().cv["Yield"]["r2"], "cv_r2_H_C": get_predictor().cv["H_C"]["r2"]}
    if "technical" in parts:
        keys = ["dry_feed_t_y", "feed_water_t_y", "slurry_water_t_y", "char_t_y", "liquid_t_y", "gas_t_y", "mass_balance_residual_t_y", "carbon_retained_fraction", "useful_process_heat_GJ_y", "purchased_heat_requirement_GJ_y",
                "coproduct_chemical_energy_GJ_y", "recoverable_coproduct_heat_GJ_y", "heat_deficit_GJ_y", "heat_surplus_GJ_y", "net_removal_proxy_tco2e_y", "water_property_source"]
        out["technical"] = {k: t[k] for k in keys}
        if sim is not None: out["particle"] = {"diameter_mm": R["pp"].diameter_mm, "h_W_m2K": R["pp"].h_W_m2K, "t95_min": (sim["t_target_s"] or 0) / 60, "Biot": sim["Biot"], "regime": sim["regime"], "tau_heat_s": sim["tau_heat_s"], "tau_kin_s": sim["tau_kin_s"]}
    if "economics" in parts:
        out["economics"] = {k: ec[k] for k in ["total_revenue_usd_y", "operating_cost_usd_y", "ebitda_like_usd_y", "annualised_capex_usd_y", "annual_economic_surplus_usd_y", "npv_usd", "irr", "simple_payback_y", "carbon_revenue_usd_y", "char_revenue_usd_y"]}
        out["economics"]["carbon_credit_price_usd_tco2e"] = R["e"].carbon_credit_usd_tco2e; out["economics"]["breakeven_carbon_price_usd_tco2e"] = breakeven_carbon_price(ec, t)
    if "optimizer" in parts and S.get("opt"):
        o = S.opt; keys = ["process", "feedstock", "HTT", "duration_min", "pred_yield_pct", "pred_H_C", "t95_min", "annual_economic_surplus_usd_y", "net_removal_proxy_tco2e_y"]
        out["optimizer"] = {"stats": o["stats"], "objective": o["objective"], "best": {k: o["best"][k] for k in keys} if o["best"] else None, "n_feasible": len(o["rows"]), "n_pareto": len(o["front"])}
    return _r(out)

def ai_panel(page, snap, fallback=None):
    section("AI engineering analyst")
    if page == "Technical":
        snap = dict(snap)
        snap["governing_equations"] = [x[1] for x in BY_PAGE["technical"] if x[0] == "tex"]
        snap.setdefault("calculation_log", [])
        snap["analysis_instructions"] = "Explain actual calculations step by step. Refer to calculation-log rows by name, show the numerical drivers, distinguish assumptions from literature properties, identify dominant heat terms and flag model limitations. Do not merely restate KPI values."
    key = get_key(); hist = S.chat.setdefault(page, [])
    def run(q):
        try:
            with st.spinner("Thinking..."):
                ans = ask(page, snap, q, key, S.get("groq_model") or DEFAULT_MODEL, history=[{"role": h["role"], "content": h["content"]} for h in hist])
            hist.append({"role": "user", "content": q or "Explain this page"}); hist.append({"role": "assistant", "content": ans})
        except LLMError as ex: st.error(str(ex))
    with st.container(border=True):
        if not key:
            st.caption("Add a Groq API key in the sidebar to switch on the AI analyst for this page.")
            for n in (fallback or []): st.markdown(f"- {n}")
            return
        c1, c2 = st.columns([1, 4])
        if c1.button("Explain this page", key=f"ex_{page}", type="primary"): run(None)
        with c2.form(f"ask_{page}", clear_on_submit=True, border=False):
            q = st.text_input("Ask about these results", placeholder="e.g. Why is the optimum at this temperature?", label_visibility="collapsed", key=f"q_{page}")
            if st.form_submit_button("Ask") and q: run(q)
        for h in hist[-6:]:
            with st.chat_message(h["role"]): st.markdown(h["content"])
        if hist and st.button("Clear conversation", key=f"clr_{page}"): S.chat[page] = []; st.rerun()

# ------------------------------------------------------------------ sidebar
PAGES = ["Executive dashboard", "Rough estimates", "Technical", "Economic", "Optimize"]
with st.sidebar:
    st.markdown('<div class="brand">MENA Biochar<span>Engineering platform</span></div>', unsafe_allow_html=True)
    st.write("")
    page = st.radio("Navigation", PAGES, label_visibility="collapsed")
    st.write("")
    d_ = S.design
    st.markdown(f'<div class="scn"><b>Active scenario</b><br>{PROCESSES[d_["process"]]["label"]}<br>{d_["feed"] if PRED() else "manual inputs"} \u00b7 {d_["htt"]:.0f} \u00b0C</div>', unsafe_allow_html=True)
    st.write("")
    with st.expander("AI analyst settings", expanded=not bool(get_key())):
        st.text_input("Groq API key", type="password", key="groq_key", help="Kept only in this browser session. Or set GROQ_API_KEY / st.secrets.")
        st.text_input("Model", value=DEFAULT_MODEL, key="groq_model")
        if st.button("List available models") and get_key():
            try: S.groq_models = list_models(get_key())
            except LLMError as ex: st.error(str(ex))
        if S.get("groq_models"): st.caption("Available: " + ", ".join(S.groq_models[:12]))
    st.caption("Screening-level tool. Costs and several process inputs are placeholders; see the Assumptions tab.")

# ------------------------------------------------------------------ input helpers
def scenario_controls(prefix):
    d = S.design; names = list(PROCESSES)
    with st.container(border=True):
        c0, c1 = st.columns([2, 3])
        sel = c0.selectbox("Process", names, index=names.index(d["process"]), format_func=lambda n: PROCESSES[n]["label"], key=f"{prefix}_proc")
        if sel != d["process"]: set_process(sel); st.rerun()
        pr = PROCESSES[sel]
        c1.markdown(f"<div class='small' style='padding-top:1.7rem'>{pr['desc']}</div>", unsafe_allow_html=True)
        a, b, c, e_ = st.columns(4)
        d["feed"] = a.selectbox("Feedstock", list(FEEDSTOCKS), index=list(FEEDSTOCKS).index(d["feed"]), key=f"{prefix}_feed")
        lo, hi = pr["T"]; d["htt"] = float(b.slider("Temperature (\u00b0C)", lo, hi, int(min(max(d["htt"], lo), hi)), 10 if hi - lo >= 100 else 5, key=f"{prefix}_htt_{sel}"))
        if pr["dur_options"]:
            cur = int(d["dur"]) if int(d["dur"]) in pr["dur_options"] else pr["dur_options"][2]
            d["dur"] = float(c.select_slider("Residence time (min)", list(pr["dur_options"]), value=cur, key=f"{prefix}_dur_{sel}"))
        else: d["dur"] = float(c.number_input("Residence time (min)", 0.02, 600.0, float(d["dur"]), 0.5 if d["dur"] >= 1 else 0.05, key=f"{prefix}_durn_{sel}"))
        if sel == "slow_pyrolysis":
            d["hr"] = float(e_.slider("Heating rate (\u00b0C/min)", 5, 30, int(d["hr"]), key=f"{prefix}_hr"))
            d["liquid_share"] = st.slider("Liquid share of non-char products (assumption, not predicted)", 0.0, 1.0, float(d["liquid_share"]), 0.05, key=f"{prefix}_ls")
        else: e_.caption("Product split from published typical values; heating rate not a model input for this process.")
    return d

def plant_inputs(p, prefix="pl"):
    a, b, c = st.columns(3)
    p.wet_feed_t_y = a.number_input("Wet feedstock (t/y)", min_value=1.0, value=float(p.wet_feed_t_y), step=500.0, key=prefix + "_wet")
    p.feed_temp_C = a.number_input("Feed temperature (\u00b0C)", value=float(p.feed_temp_C), key=prefix + "_ft")
    p.solid_cp_kJ_kgK = a.number_input("Dry solids cp (kJ/kg/K)", min_value=0.1, value=float(p.solid_cp_kJ_kgK), key=prefix + "_cp")
    p.heat_loss_fraction = b.slider("Heat-loss fraction", 0.0, 0.6, float(p.heat_loss_fraction), 0.01, key=prefix + "_loss")
    p.dryer_efficiency = b.slider("Heating efficiency", 0.1, 1.0, float(p.dryer_efficiency), 0.01, key=prefix + "_eff")
    p.pyrolysis_enthalpy_kJ_kg_dry = b.number_input("Reaction heat (kJ/kg dry, endothermic +)", value=float(p.pyrolysis_enthalpy_kJ_kg_dry), step=50.0, key=prefix + "_dh")
    p.recoverable_coproduct_heat_fraction = c.slider("Recoverable co-product heat", 0.0, 1.0, float(p.recoverable_coproduct_heat_fraction), 0.01, key=prefix + "_rec")
    p.liquid_to_heat_fraction = c.slider("Liquid product diverted to process heat", 0.0, 1.0, float(p.liquid_to_heat_fraction), 0.05, key=prefix + "_liqheat", help="Diverted liquid is burned for heat and excluded from liquid sales revenue.")
    p.gas_lhv_MJ_kg = c.number_input("Gas LHV (MJ/kg)", min_value=0.0, value=float(p.gas_lhv_MJ_kg), key=prefix + "_gl")
    p.liquid_lhv_MJ_kg = c.number_input("Liquid LHV (MJ/kg)", min_value=0.0, value=float(p.liquid_lhv_MJ_kg), key=prefix + "_ll")
    if S.design["process"] == "htc":
        a, b = st.columns(2)
        p.htc_water_to_dry_ratio = a.number_input("HTC slurry water per kg dry feed", 1.0, 30.0, float(p.htc_water_to_dry_ratio), 0.5, key=prefix + "_hw", help="Reviews report solid:water ratios of 1:5 to 1:25.")
        p.htc_heat_recovery_fraction = b.slider("HTC heat-exchanger recovery", 0.0, 0.9, float(p.htc_heat_recovery_fraction), 0.05, key=prefix + "_hr_")
    p.use_steam_tables = st.checkbox("Use IAPWS steam tables (CoolProp) for water", value=bool(p.use_steam_tables) and HAVE_COOLPROP, disabled=not HAVE_COOLPROP, key=prefix + "_st")
    return p

def particle_inputs():
    q = S.particle; mode = PROC()["particle"]
    if mode == "none": st.info("The particle model does not apply to hydrothermal carbonisation (wet, pressurised, different kinetics)."); return
    if mode == "heatup": st.caption("For this process the particle model gives heat-up behaviour only; its kinetics are for pyrolysis devolatilisation.")
    a, b, c = st.columns(3)
    q["d"] = a.number_input("Particle diameter (mm)", min_value=0.5, max_value=100.0, value=float(q["d"]), step=0.5, key=f"pa_d_{S.design['process']}")
    q["h"] = b.number_input("Surface heat-transfer coeff. h (W/m\u00b2/K)", min_value=5.0, max_value=2000.0, value=float(q["h"]), step=5.0, key=f"pa_h_{S.design['process']}", help="Lumped convection + radiation; reactor dependent (assumption).")
    q["rho"] = c.number_input("Virgin density (kg/m\u00b3)", min_value=100.0, value=float(q["rho"]), step=25.0, key="pa_rho")
    with st.expander("Particle properties and kinetics"):
        a, b, c = st.columns(3)
        q["kv"] = a.number_input("k virgin (W/m/K)", min_value=0.01, value=float(q["kv"]), key="pa_kv"); q["kc"] = a.number_input("k char (W/m/K)", min_value=0.01, value=float(q["kc"]), key="pa_kc")
        q["cpv"] = b.number_input("cp virgin (J/kg/K)", min_value=500.0, value=float(q["cpv"]), key="pa_cpv"); q["cpc"] = b.number_input("cp char (J/kg/K)", min_value=500.0, value=float(q["cpc"]), key="pa_cpc")
        q["lnA"] = c.number_input("ln A (1/s)", value=float(q["lnA"]), key="pa_lnA", help="Di Blasi & Branca 2001, beech wood: 22.2")
        q["E"] = c.number_input("E (kJ/mol)", min_value=10.0, value=float(q["E"]), key="pa_E", help="Di Blasi & Branca 2001: 141.2")
        q["dH"] = st.number_input("Particle reaction enthalpy (J/kg converted, endothermic +)", value=float(q["dH"]), step=10000.0, key="pa_dH")
        st.caption("Kinetic defaults are for beech wood (573-708 K). Other feedstocks and higher temperatures are extrapolations.")

def sankey(t):
    labels = ["Wet feed", "Water", "Dry feed", "Biochar / solid", "Liquid", "Gas", "Other"]
    src = [0, 0, 2, 2, 2, 2]; dst = [1, 2, 3, 4, 5, 6]
    val = [t["feed_water_t_y"], t["dry_feed_t_y"], t["char_t_y"], t["liquid_t_y"], t["gas_t_y"], t["other_t_y"]]
    keep = [i for i, v in enumerate(val) if v > 1e-9]
    fig = go.Figure(go.Sankey(node=dict(label=labels, pad=18, thickness=14, color=["#33434d", "#6aa7d6", GREEN, "#2b2b2b", AMBER, GREY, "#c8c8c8"]),
                    link=dict(source=[src[i] for i in keep], target=[dst[i] for i in keep], value=[val[i] for i in keep], color="rgba(127,140,150,.28)")))
    return style_fig(fig, 300, legend=False)

# ------------------------------------------------------------------ calculation logs
def _fv(v):
    if isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool): return "n/a" if v != v else f"{v:,.6g}"
    return str(v)

def _row(rows, step, eq, inp, val, unit, model): rows.append({"Step": step, "Equation": eq, "Inputs": inp, "Result": _fv(val), "Unit": str(unit), "Model / source": model})

def log_estimates(feed, cls, htt, dur, hr, r, sf, t0, ec0, process):
    rows = []; pr = PROCESSES[process]
    _row(rows, "Inputs", "x = [HTT, ln(1+t), heating rate, class]", f"{pr['label']}; {feed} -> class '{cls}'; HTT {htt} C; t {dur} min; beta {hr} C/min", "", "", "ML-001")
    for k_, nm in [("Yield", "Char yield"), ("C", "Carbon in char"), ("Ash", "Ash"), ("H_C", "H/C")]:
        v = r[k_]; _row(rows, nm, "mean over trees; sigma = std over trees", f"n_obs = {get_predictor().n_obs.get(k_, 'n/a')}", v["mean"], f"+/- {v['std']:.3g}", "ML-001" if process == "slow_pyrolysis" else f"{pr['yield_source']} / ML-001")
    _row(rows, "Stable-C fraction", "interp(H/C -> f_stable)", f"H/C = {r['H_C']['mean']:.3f}", sf, "-", "PERM-001 (placeholder map)")
    _row(rows, "Basis feed", "m_dry = m_wet (1 - Xw)", f"m_wet = 10,000 t/y", t0["dry_feed_t_y"], "t/y", "MASS-001")
    _row(rows, "Biochar", "m_char = m_dry Y_char", "", t0["char_t_y"], "t/y", "MASS-001")
    _row(rows, "Carbon retained", "C_char / C_feed", "", t0["carbon_retained_fraction"], "-", "carbon balance")
    _row(rows, "Net removal proxy", "m_char c f_stable 44/12 - lifecycle", "", t0["net_removal_proxy_tco2e_y"], "t CO2e/y", "PERM-001")
    _row(rows, "Economic surplus (placeholder prices)", "EBITDA - CAPEX_ann", "", ec0["annual_economic_surplus_usd_y"], "USD/y", "ECON-001")
    return pd.DataFrame(rows)

def log_technical(R):
    p, t, pp, sim, pr = R["p"], R["t"], R["pp"], R["sim"], R["pr"]; rows = []; add = lambda *a: _row(rows, *a)
    ysrc = "ML-001 (predicted)" if (pr and S.design["process"] == "slow_pyrolysis") else (R["proc"]["yield_source"] if pr else "user input")
    add("Process", "-", R["proc"]["label"], 0, "", R["proc"]["status"])
    add("Dry feed", "m_dry = m_wet (1 - Xw)", f"{p.wet_feed_t_y:,.6g} x (1 - {p.moisture_wet_basis:.6g})", t["dry_feed_t_y"], "t/y", "MASS-001")
    add("Feed water", "m_w = m_wet - m_dry", f"{p.wet_feed_t_y:,.6g} - {t['dry_feed_t_y']:,.6g}", t["feed_water_t_y"], "t/y", "MASS-001")
    if p.process_type == "htc": add("Slurry water", "max(rho_w m_dry, m_w)", f"rho_w = {p.htc_water_to_dry_ratio}", t["slurry_water_t_y"], "t/y", "HTC energy balance")
    add("Char / hydrochar", "m_char = m_dry Y_char", f"{t['dry_feed_t_y']:,.6g} x {p.char_yield_dry:.6g}; yield source: {ysrc}", t["char_t_y"], "t/y", "MASS-001")
    add("Liquid", "m_liq = m_dry Y_liq", f"Y_liq = {p.liquid_yield_dry:.3f}", t["liquid_t_y"], "t/y", "process split")
    add("Gas", "m_gas = m_dry Y_gas", f"Y_gas = {p.gas_yield_dry:.3f}", t["gas_t_y"], "t/y", "process split")
    add("Mass residual", "m_dry - sum(products)", "", t["mass_balance_residual_t_y"], "t/y", "MASS-001")
    add("Feed carbon", "C_feed = m_dry x_C", f"{t['dry_feed_t_y']:.6g} t/y x {p.feed_carbon_fraction_dry:.6g} (typical, unsourced)", t["feed_carbon_t_y"], "t C/y", "assumption")
    add("Char carbon", "C_char = m_char c_char", f"{t['char_t_y']:.6g} t/y x {p.char_carbon_fraction:.6g}", t["char_carbon_t_y"], "t C/y", "ML-001 / process table")
    add("Carbon retained in char", "C_char / C_feed (must be <= 1)", "", t["carbon_retained_fraction"], "-", "carbon balance")
    add("Water sensible heat", "m_w (h_f - h_in)" if p.process_type != "htc" else "m_slurry (h_f(Tr) - h_in)", f"mass={t['slurry_water_t_y'] if p.process_type == 'htc' else t['feed_water_t_y']:.6g} t/y; T_in={p.feed_temp_C:.6g} C; T_r={p.reactor_temp_C:.6g} C; source={t['water_property_source']}", t["water_sensible_GJ_y"], "GJ/y", "ENERGY-001")
    add("Water vaporisation", "m_w h_fg (0 for HTC)", f"{t['feed_water_t_y']:.6g} t/y x {p.water_latent_kJ_kg:.6g} kJ/kg; 1 atm" if p.process_type != "htc" else "HTC: no phase change", t["water_vaporisation_GJ_y"], "GJ/y", "ENERGY-001")
    add("Steam superheat", "m_w (h(T_r) - h_g) (0 for HTC)", f"m_w={t['feed_water_t_y']:.6g} t/y; T_r={p.reactor_temp_C:.6g} C; cp_v={p.steam_cp_kJ_kgK:.6g}", t["steam_superheat_GJ_y"], "GJ/y", "ENERGY-001")
    add("Solids sensible heat", "m_dry cp (T_r - T_in)", f"{t['dry_feed_t_y']:,.6g} t/y x {p.solid_cp_kJ_kgK:.6g} kJ/kg/K x ({p.reactor_temp_C:.6g}-{p.feed_temp_C:.6g}) K", t["solids_sensible_GJ_y"], "GJ/y", "ENERGY-001")
    add("Reaction heat", "m_dry dH", f"{t['dry_feed_t_y']:,.6g} t/y x {p.pyrolysis_enthalpy_kJ_kg_dry:.6g} kJ/kg (user input)", t["reaction_heat_GJ_y"], "GJ/y", "assumption")
    add("Useful process heat", "sum (x (1 - eps_hx) for HTC)", "", t["useful_process_heat_GJ_y"], "GJ/y", "ENERGY-001")
    add("Gross heat duty", "Q_useful / (1 - f_loss)", f"{t['useful_process_heat_GJ_y']:.6g} / (1 - {p.heat_loss_fraction:.6g})", t["gross_heat_duty_GJ_y"], "GJ/y", "ENERGY-001")
    add("Purchased heat requirement", "Q_gross / eta", f"{t['gross_heat_duty_GJ_y']:.6g} / {p.dryer_efficiency:.6g}", t["purchased_heat_requirement_GJ_y"], "GJ/y", "ENERGY-001")
    add("Co-product chemical energy", "m_gas LHV_g + m_liq LHV_l", f"gas={t['gas_t_y']:.6g} t/y x {p.gas_lhv_MJ_kg:.6g}; liquid-to-heat={p.liquid_to_heat_fraction:.6g} x {t['liquid_t_y']:.6g} t/y x {p.liquid_lhv_MJ_kg:.6g} MJ/kg", t["coproduct_chemical_energy_GJ_y"], "GJ/y", "assumption")
    add("Recoverable heat", "f_rec x chemical energy", f"{t['coproduct_chemical_energy_GJ_y']:.6g} x {p.recoverable_coproduct_heat_fraction:.6g}", t["recoverable_coproduct_heat_GJ_y"], "GJ/y", "assumption")
    add("Liquid diverted to heat", "m_liquid x f_liquid_to_heat x LHV", f"diverted = {p.liquid_to_heat_fraction:.0%}; excluded from sales", t["liquid_to_heat_energy_GJ_y"], "GJ/y", "user allocation")
    add("Heat deficit (+) / surplus (-)", "purchased - recoverable", "", t["heat_deficit_GJ_y"] - t["heat_surplus_GJ_y"], "GJ/y", "ENERGY-001")
    add("Stored CO2 (gross)", "m_char c f_stable 44/12", f"{t['char_t_y']:.6g} x {p.char_carbon_fraction:.6g} x {p.stable_carbon_fraction:.6g} x 44/12", t["gross_stored_co2_t_y"], "t CO2/y", "PERM-001")
    add("Net removal proxy", "gross - lifecycle", f"lifecycle = {p.lifecycle_emissions_tco2e_y} (not modelled)", t["net_removal_proxy_tco2e_y"], "t CO2e/y", "screening proxy")
    if sim is not None:
        add("Biot number", "h R / k", f"h = {pp.h_W_m2K}, R = {pp.diameter_mm/2:.2f} mm, k = {pp.k_virgin}", sim["Biot"], "-", "PART-001")
        add("Thermal time scale", "R^2 / (pi^2 alpha)", "", sim["tau_heat_s"], "s", "PART-001")
        add("Kinetic time scale", "ln(1/(1-X)) / k(T_inf)", f"E = {pp.E_kJ_mol}, ln A = {pp.ln_A}", sim["tau_kin_s"], "s", "KIN-001")
        add("Time to 95% conversion", "mass-average virgin consumed", f"{sim['cells']} cells, dt = {sim['dt_s']} s", (sim["t_target_s"] or float("nan")), "s", "PART-001")
    return pd.DataFrame(rows)

def log_economic(R):
    ec, e, t = R["ec"], R["e"], R["t"]; rows = []; add = lambda *a: _row(rows, *a)
    add("Capital recovery factor", "i(1+i)^n / ((1+i)^n - 1)", f"i = {e.discount_rate:.3f}, n = {e.project_life_y}", ec["crf"], "-", "ECON-001")
    add("Annualised CAPEX", "CAPEX x CRF x a", f"CAPEX = {e.capex_usd:,.0f} USD; a = {e.annualisation_fraction}", ec["annualised_capex_usd_y"], "USD/y", "ECON-001")
    add("Feedstock + logistics", "m_wet (c_feed + c_log)", f"{t['wet_feed_t_y']:,.0f} t/y x ({e.feedstock_cost_usd_t_wet} + {e.logistics_cost_usd_t_wet})", ec["feedstock_logistics_cost_usd_y"], "USD/y", "placeholder prices")
    add("Electricity", "m_dry x kWh/t x price", f"{e.electricity_use_kwh_t_dry} kWh/t dry; {e.electricity_price_usd_kwh} USD/kWh", ec["electricity_cost_usd_y"], "USD/y", "placeholder")
    add("Purchased heat", "Q_deficit x price", f"{t['heat_deficit_GJ_y']:,.0f} GJ/y x {e.purchased_heat_price_usd_GJ}", ec["purchased_heat_cost_usd_y"], "USD/y", "ECON-001")
    add("Maintenance", "f_maint x CAPEX", f"f = {e.maintenance_fraction_capex_y}", ec["maintenance_usd_y"], "USD/y", "placeholder")
    add("Labour + other OPEX", "L + O", "", ec["labour_usd_y"] + ec["other_opex_usd_y"], "USD/y", "placeholder")
    add("Operating cost", "sum of the above", "", ec["operating_cost_usd_y"], "USD/y", "ECON-001")
    add("Biochar revenue", "m_char x price", f"{t['char_t_y']:,.1f} t/y x {e.char_price_usd_t}", ec["char_revenue_usd_y"], "USD/y", "placeholder price")
    add("Liquid revenue", "m_liq x price", f"{t['liquid_t_y']:,.1f} t/y x {e.liquid_price_usd_t}", ec["liquid_revenue_usd_y"], "USD/y", "placeholder price")
    add("Electricity export revenue", "Q_surplus x 277.78 x eta_el x f_export x price", f"surplus {t['heat_surplus_GJ_y']:,.0f} GJ/y", ec["electricity_revenue_usd_y"], "USD/y", "ECON-001")
    add("Carbon revenue", "max(0, CO2_net) x p_C", f"{t['net_removal_proxy_tco2e_y']:,.0f} t x {e.carbon_credit_usd_tco2e}", ec["carbon_revenue_usd_y"], "USD/y", "scenario assumption")
    add("EBITDA-like", "R - OPEX", "", ec["ebitda_like_usd_y"], "USD/y", "ECON-001")
    add("Economic surplus", "EBITDA - CAPEX_ann", "", ec["annual_economic_surplus_usd_y"], "USD/y", "ECON-001")
    add("NPV", "-CAPEX + sum EBITDA/(1+i)^t", "", ec["npv_usd"], "USD", "ECON-001")
    add("IRR", "root of NPV(r) = 0", "", ec["irr"] if ec["irr"] is not None else float("nan"), "-", "ECON-001")
    add("Simple payback", "CAPEX / EBITDA", "", ec["simple_payback_y"] if ec["simple_payback_y"] is not None else float("nan"), "y", "ECON-001")
    be = breakeven_carbon_price(ec, t); add("Breakeven carbon price", "(CAPEX_ann + OPEX - (R - R_carbon)) / CO2_net", "", be if be is not None else float("nan"), "USD/tCO2e", "derived")
    return pd.DataFrame(rows)

def log_optimize(o, constrain, use_particle, safety):
    rows = []; st_ = o["stats"]
    for pn in o["processes"]:
        pr = PROCESSES[pn]; lo, hi = ((300, 800) if pn == "slow_pyrolysis" else pr["T"])
        _row(rows, f"Grid: {pr['label']}", "T x residence x heating rate" if pn == "slow_pyrolysis" else "T only", f"T {lo}-{hi} C; residence {'15,30,60,120,240' if pn == 'slow_pyrolysis' else pr['dur_default']} min", "", "", pr["yield_source"])
    _row(rows, "Designs evaluated", "count", "", st_["evaluated"], "", "DESIGN-001")
    _row(rows, f"Constraint: H/C <= {o.get('max_hc', 0.7):.2f}", "reject if H/C above limit", "on" if constrain else "off", st_["rejected_hc"], "rejected", "PERM-001")
    _row(rows, "Constraint: particle conversion", "reject if t_res < s x t95", f"s = {safety}" if use_particle else "off", st_["rejected_conversion"], "rejected", "PART-001")
    _row(rows, "Constraint: carbon balance", "reject if C_char / C_feed > 1", "", st_["rejected_carbon"], "rejected", "carbon balance")
    _row(rows, "Feasible designs", "count", "", len(o["rows"]), "", "DESIGN-001")
    _row(rows, "Pareto front", "non-dominated in (surplus, removal)", "", len(o["front"]), "designs", "DESIGN-001")
    _row(rows, "Objective", o["objective"], f"carbon price {o['cc']} USD/tCO2e", "", "", "DESIGN-001")
    if o["best"]:
        b = o["best"]; _row(rows, "Best design", "argmin / argmax of objective", f"{b['process']}, {b['feedstock']}, {b['HTT']:.0f} C, {b['duration_min']:.3g} min", b["annual_economic_surplus_usd_y"], "USD/y surplus", "DESIGN-001")
    t95 = {}
    for r_ in o["rows"]:
        if r_["t95_min"] is not None: t95[(r_["process"], r_["HTT"])] = r_["t95_min"]
    for (pn, h), v in sorted(t95.items())[:40]: _row(rows, f"Particle t95 ({pn})", "PART-001 simulation", f"T = {h:.0f} C", v, "min", "PART-001")
    return pd.DataFrame(rows)

def assumptions_table(R):
    p, e, pp, pr = R["p"], R["e"], R["pp"], R["pr"]; proc = R["proc"]
    rows = [("Process", proc["label"], proc["status"], "Screening" if S.design["process"] != "slow_pyrolysis" else "Data-driven"),
            ("Char yield, C, H/C", f"{p.char_yield_dry:.3f}, {p.char_carbon_fraction:.2f}, stable {p.stable_carbon_fraction:.2f}", "ML-001 / process table; stable fraction from placeholder map (PERM-001)" if pr else "User input", "Data-driven / placeholder"),
            ("Liquid / gas split", f"liquid {p.liquid_yield_dry:.2f}, gas {p.gas_yield_dry:.2f}", "Assumption (slow pyrolysis) or published typical split", "Assumption / typical"),
            ("Feed moisture", f"{p.moisture_wet_basis:.2f}", "Typical value for preset feedstock", "Typical, unsourced"),
            ("Feed carbon fraction (dry)", f"{p.feed_carbon_fraction_dry:.2f}", "Typical value for preset feedstock", "Typical, unsourced"),
            ("Water properties", R["t"]["water_property_source"], "IAPWS-95", "Literature (verified)"),
            ("Solids cp", f"{p.solid_cp_kJ_kgK} kJ/kg/K", "Constant; no temperature dependence", "Typical"),
            ("Heat loss / efficiency", f"{p.heat_loss_fraction:.2f} / {p.dryer_efficiency:.2f}", "User input", "Assumption"),
            ("Reaction heat", f"{p.pyrolysis_enthalpy_kJ_kg_dry} kJ/kg", "Default 0 (neglected)", "Assumption")]
    if S.design["process"] == "htc": rows += [("HTC slurry water / heat recovery", f"{p.htc_water_to_dry_ratio} kg/kg / {p.htc_heat_recovery_fraction:.2f}", "Review range 1:5-1:25; recovery is an assumption", "Assumption"),
                                               ("HTC yield and char lines", "linear in T", "35-65% yield range from reviews mapped to 260-180 C; C and H/C unsourced", "Screening")]
    if S.design["process"] != "htc": rows += [("Particle kinetics", f"E = {pp.E_kJ_mol}, ln A = {pp.ln_A}", "Di Blasi & Branca (2001), beech wood, 573-708 K", "Literature (verified), extrapolated"),
                                              ("Particle properties", f"k {pp.k_virgin}/{pp.k_char}, cp {pp.cp_virgin:.0f}/{pp.cp_char:.0f}, rho {pp.rho_virgin:.0f}", "Typical wood/char values", "Typical, unsourced"),
                                              ("Surface heat-transfer coeff.", f"{pp.h_W_m2K} W/m2/K; d = {pp.diameter_mm} mm", "User input; reactor dependent", "Assumption")]
    rows += [("Prices, CAPEX, labour", f"char {e.char_price_usd_t} USD/t; liquid {e.liquid_price_usd_t} USD/t; CAPEX {e.capex_usd:,.0f} USD", "Placeholders; CAPEX is not process-specific", "Placeholder"),
             ("Carbon credit price", f"{e.carbon_credit_usd_tco2e} USD/tCO2e", "Scenario assumption; removal not verified", "Assumption")]
    return pd.DataFrame(rows, columns=["Item", "Value", "Basis", "Status"])
def process_inputs(prefix="p"):
    p=st.session_state.process
    a,b,c=st.columns(3)
    with a:
        p.wet_feed_t_y=st.number_input("Wet feedstock (t/y)",min_value=1.0,value=float(p.wet_feed_t_y),step=500.0,key=prefix+"_wet")
        p.moisture_wet_basis=st.slider("Feed moisture (wet basis)",0.0,0.85,float(p.moisture_wet_basis),0.01,key=prefix+"_moist")
        p.feed_temp_C=st.number_input("Feed temperature (°C)",value=float(p.feed_temp_C),key=prefix+"_feedtemp")
    with b:
        p.reactor_temp_C=st.number_input("Reactor temperature (°C)",min_value=101.0,max_value=1000.0,value=float(p.reactor_temp_C),key=prefix+"_reacttemp")
        p.char_yield_dry=st.slider("Char yield (dry basis)",0.0,1.0,float(p.char_yield_dry),0.01,key=prefix+"_char")
        p.liquid_yield_dry=st.slider("Liquid yield (dry basis)",0.0,1.0,float(p.liquid_yield_dry),0.01,key=prefix+"_liquid")
    with c:
        p.gas_yield_dry=st.slider("Gas yield (dry basis)",0.0,1.0,float(p.gas_yield_dry),0.01,key=prefix+"_gas")
        p.other_yield_dry=st.slider("Other / unallocated fraction",0.0,1.0,float(p.other_yield_dry),0.01,key=prefix+"_other")
        p.heat_loss_fraction=st.slider("Heat-loss fraction",0.0,0.6,float(p.heat_loss_fraction),0.01,key=prefix+"_loss")
    if abs(p.char_yield_dry+p.liquid_yield_dry+p.gas_yield_dry+p.other_yield_dry-1)>1e-6:
        st.error(f"Dry product fractions sum to {p.char_yield_dry+p.liquid_yield_dry+p.gas_yield_dry+p.other_yield_dry:.3f}, not 1. Adjust them before calculating.")
    p.solid_cp_kJ_kgK=st.number_input("Dry solids Cp (kJ/kg·K)",min_value=0.01,value=float(p.solid_cp_kJ_kgK),key=prefix+"_cps")
    p.dryer_efficiency=st.slider("Dryer / heating efficiency",0.1,1.0,float(p.dryer_efficiency),0.01,key=prefix+"_eff")
    p.gas_lhv_MJ_kg=st.number_input("Gas LHV (MJ/kg)",min_value=0.0,value=float(p.gas_lhv_MJ_kg),key=prefix+"_gaslhv")
    p.liquid_lhv_MJ_kg=st.number_input("Liquid LHV (MJ/kg)",min_value=0.0,value=float(p.liquid_lhv_MJ_kg),key=prefix+"_liqLHV")
    p.recoverable_coproduct_heat_fraction=st.slider("Recoverable coproduct heat fraction",0.0,1.0,float(p.recoverable_coproduct_heat_fraction),0.01,key=prefix+"_recovery")
    p.liquid_to_heat_fraction=st.slider("Liquid product diverted to process heat",0.0,1.0,float(p.liquid_to_heat_fraction),0.05,key=prefix+"_liqheat",help="Diverted liquid is burned for heat and excluded from liquid sales revenue.")
    return p

def econ_inputs(prefix="e"):
    e=st.session_state.economics
    a,b,c=st.columns(3)
    with a:
        e.capex_usd=st.number_input("Installed CAPEX (USD)",min_value=0.0,value=float(e.capex_usd),step=100000.0,key=prefix+"_capex")
        e.project_life_y=st.number_input("Project life (years)",min_value=1,max_value=50,value=int(e.project_life_y),key=prefix+"_life")
        e.discount_rate=st.number_input("Discount rate",min_value=0.0,max_value=0.99,value=float(e.discount_rate),step=0.01,key=prefix+"_rate")
    with b:
        e.feedstock_cost_usd_t_wet=st.number_input("Feedstock cost (USD/wet t)",min_value=0.0,value=float(e.feedstock_cost_usd_t_wet),key=prefix+"_feedcost")
        e.logistics_cost_usd_t_wet=st.number_input("Logistics (USD/wet t)",min_value=0.0,value=float(e.logistics_cost_usd_t_wet),key=prefix+"_log")
        e.char_price_usd_t=st.number_input("Biochar price (USD/t)",min_value=0.0,value=float(e.char_price_usd_t),key=prefix+"_charprice")
    with c:
        e.liquid_price_usd_t=st.number_input("Liquid product price (USD/t)",min_value=0.0,value=float(e.liquid_price_usd_t),key=prefix+"_liqprice")
        e.electricity_price_usd_kwh=st.number_input("Electricity tariff (USD/kWh)",min_value=0.0,value=float(e.electricity_price_usd_kwh),key=prefix+"_elec")
        e.labour_usd_y=st.number_input("Annual labour (USD/y)",min_value=0.0,value=float(e.labour_usd_y),key=prefix+"_labour")
    e.other_opex_usd_y=st.number_input("Other annual OPEX (USD/y)",min_value=0.0,value=float(e.other_opex_usd_y),key=prefix+"_otheropex")
    e.maintenance_fraction_capex_y=st.number_input("Maintenance fraction of CAPEX / y",min_value=0.0,max_value=0.5,value=float(e.maintenance_fraction_capex_y),step=0.005,key=prefix+"_maint")
    e.electricity_use_kwh_t_dry=st.number_input("Electricity use (kWh/dry t)",min_value=0.0,value=float(e.electricity_use_kwh_t_dry),key=prefix+"_elecuse")
    e.purchased_heat_price_usd_GJ=st.number_input("Purchased heat price (USD/GJ)",min_value=0.0,value=float(e.purchased_heat_price_usd_GJ),key=prefix+"_heatprice")
    e.carbon_credit_usd_tco2e=st.number_input("Carbon credit price (USD/tCO2e) - scenario assumption",min_value=0.0,value=float(e.carbon_credit_usd_tco2e),step=5.0,key=prefix+"_cc",help="Only meaningful if removal is verified and creditable. The platform removal figure is a screening proxy.")
    return e

def tech_kpis(R):
    t, ec, p = R["t"], R["ec"], R["p"]; be = breakeven_carbon_price(ec, t)
    kpis([("Biochar / solid", fmt(t["char_t_y"]), "per year", "t"), ("Removal proxy", fmt(t["net_removal_proxy_tco2e_y"]), "screening, not creditable", "tCO\u2082e/y"),
          ("Economic surplus", fmt(ec["annual_economic_surplus_usd_y"]), "after capital recovery", "USD/y"), ("NPV", fmt(ec["npv_usd"]), "placeholder prices", "USD"),
          ("Breakeven carbon price", fmt(be) if be is not None else "n/a", "surplus = 0", "USD/t"), ("Stable carbon", f"{p.stable_carbon_fraction:.2f}", "fraction of char C")])

# ================================================================== EXECUTIVE DASHBOARD
if page == "Executive dashboard":
    header("Executive dashboard", "Research-derived engineering and commercial intelligence: feedstocks, operating conditions, product quality, plant design evidence and economics.")
    chars = pd.read_csv(Path(__file__).parent / "data" / "biochar_production_characteristics_202404.csv")
    bib = pd.read_csv(Path(__file__).parent / "data" / "biochar_production_bibliography_202404.csv")
    numeric = ["HTT", "Pyrolysis_duration", "Heating_rate", "Yield", "Fixed_C", "Ash", "C", "H_C", "O_C", "Volatile_matter"]
    for col in numeric:
        chars[col] = pd.to_numeric(chars[col], errors="coerce")
    chars["Publication year"] = pd.to_numeric(chars["Publication year"], errors="coerce")

    # Filters select evidence, not a simulated plant scenario.
    f1, f2 = st.columns(2)
    process_options = sorted(chars.Pyrolysis_type.dropna().unique().tolist())
    class_options = sorted(chars.Feedstock_class.dropna().unique().tolist())
    with f1:
        selected_process = st.multiselect("Conversion route", process_options, default=["slow"] if "slow" in process_options else process_options)
    with f2:
        selected_classes = st.multiselect("Feedstock families", class_options, default=class_options)
    view = chars[chars.Pyrolysis_type.isin(selected_process) & chars.Feedstock_class.isin(selected_classes)].copy()
    if view.empty:
        st.warning("No experimental records match these filters. Select another route or feedstock family.")
        st.stop()

    section("What the experimental evidence reports")
    a, b, c, d = st.columns(4)
    a.metric("Observed char yield", f"{view.Yield.median():.1f} wt%", f"IQR {view.Yield.quantile(.25):.1f}–{view.Yield.quantile(.75):.1f}%" if view.Yield.notna().any() else None)
    b.metric("Biochar carbon", f"{view.C.median():.1f} wt%", "median of reported values")
    c.metric("Ash content", f"{view.Ash.median():.1f} wt%", "median of reported values")
    d.metric("H/C molar ratio", f"{view.H_C.median():.2f}", "lower values generally indicate greater carbonisation")
    st.caption(f"Filtered evidence: {len(view):,} experimental rows from {view.Title.nunique():,} distinct publications. These are distributions across heterogeneous studies, not guaranteed plant performance or a single pooled design recommendation.")

    tabs = st.tabs(["Feedstock performance", "Process & operating window", "Biochar quality", "Plant design implications", "Economics & commercial evidence", "Sources & evidence"])
    with tabs[0]:
        section("How feedstock families compare")
        agg = view.groupby("Feedstock_class").agg(Records=("Feedstock", "size"), Feedstocks=("Feedstock", "nunique"), Yield_median=("Yield", "median"), Yield_q25=("Yield", lambda x: x.quantile(.25)), Yield_q75=("Yield", lambda x: x.quantile(.75)), Carbon_median=("C", "median"), Ash_median=("Ash", "median"), H_C_median=("H_C", "median")).reset_index()
        agg = agg.rename(columns={"Feedstock_class":"Feedstock family", "Yield_median":"Yield median (wt%)", "Yield_q25":"Yield Q25", "Yield_q75":"Yield Q75", "Carbon_median":"Char C median (wt%)", "Ash_median":"Ash median (wt%)", "H_C_median":"H/C median"})
        st.dataframe(agg.sort_values("Yield median (wt%)", ascending=False), width="stretch", hide_index=True)
        fig = px.box(view.dropna(subset=["Yield"]), x="Feedstock_class", y="Yield", points="outliers", title="Reported char-yield distribution by feedstock family")
        st.plotly_chart(style_fig(fig, 390, legend=False), width="stretch")
        st.markdown("**Interpretation:** compare both yield and quality. A high char yield alone does not establish the best feedstock: ash, carbon content, H/C, contamination, moisture, availability and competing uses also matter. The dataset does not provide a representative Egypt-wide supply census or delivered feedstock costs.")
        st.markdown("**Feedstock-level lookup**")
        feed_summary = view.groupby("Feedstock").agg(Records=("ID", "count"), Yield=("Yield", "median"), Carbon=("C", "median"), Ash=("Ash", "median"), H_C=("H_C", "median"), HTT=("HTT", "median")).reset_index().sort_values("Records", ascending=False).head(40)
        st.dataframe(feed_summary, width="stretch", hide_index=True)
    with tabs[1]:
        section("Reported operating conditions")
        cond = view.groupby("Pyrolysis_type").agg(Records=("ID", "count"), HTT_median_C=("HTT", "median"), HTT_Q25=("HTT", lambda x:x.quantile(.25)), HTT_Q75=("HTT", lambda x:x.quantile(.75)), Residence_median_min=("Pyrolysis_duration", "median"), Residence_Q25=("Pyrolysis_duration", lambda x:x.quantile(.25)), Residence_Q75=("Pyrolysis_duration", lambda x:x.quantile(.75)), Heating_rate_median_C_min=("Heating_rate", "median")).reset_index()
        st.dataframe(cond, width="stretch", hide_index=True)
        x1, x2 = st.columns(2)
        with x1:
            fig = px.scatter(view.dropna(subset=["HTT", "Yield"]), x="HTT", y="Yield", color="Feedstock_class", hover_data=["Feedstock", "Pyrolysis_duration", "Title"], title="Char yield versus treatment temperature")
            st.plotly_chart(style_fig(fig, 360), width="stretch")
        with x2:
            fig = px.scatter(view.dropna(subset=["HTT", "H_C"]), x="HTT", y="H_C", color="Feedstock_class", hover_data=["Feedstock", "Pyrolysis_duration", "Title"], title="H/C ratio versus treatment temperature")
            st.plotly_chart(style_fig(fig, 360), width="stretch")
        st.markdown("**Engineering reading:** temperature is a major product-quality lever: increasing treatment severity generally lowers volatile matter and H/C while changing yield and energy demand. The plots show study-level observations; feedstock, reactor configuration, heating rate and residence-time definitions differ between publications, so correlation is not a universal process law.")
    with tabs[2]:
        section("What product quality can the evidence support?")
        quality = view[["Feedstock_class", "Yield", "Fixed_C", "Ash", "C", "H_C", "O_C", "Volatile_matter"]].groupby("Feedstock_class").agg({"Yield":"median", "Fixed_C":"median", "Ash":"median", "C":"median", "H_C":"median", "O_C":"median", "Volatile_matter":"median"}).reset_index()
        quality = quality.rename(columns={"Feedstock_class":"Feedstock family", "Yield":"Yield wt%", "Fixed_C":"Fixed carbon wt%", "Ash":"Ash wt%", "C":"Elemental carbon wt%", "H_C":"H/C", "O_C":"O/C", "Volatile_matter":"Volatile matter wt%"})
        st.dataframe(quality, width="stretch", hide_index=True)
        fig = px.scatter(view.dropna(subset=["H_C", "O_C"]), x="O_C", y="H_C", color="Feedstock_class", hover_data=["Feedstock", "HTT", "Title"], title="Van Krevelen view of reported biochar elemental ratios")
        st.plotly_chart(style_fig(fig, 390), width="stretch")
        st.info("Product specification must be application-specific. Soil amendment, adsorption, metallurgical use and carbon removal have different quality and safety requirements. These records do not establish contaminant compliance or certification eligibility.")
    with tabs[3]:
        section("Design implications extracted from the operating data")
        st.markdown("**Reactor and process selection**")
        route = view.groupby("Pyrolysis_type").agg(Records=("ID", "count"), Median_temperature_C=("HTT", "median"), Median_residence_min=("Pyrolysis_duration", "median"), Median_heating_rate_C_min=("Heating_rate", "median"), Median_yield_wt_pct=("Yield", "median")).reset_index()
        st.dataframe(route, width="stretch", hide_index=True)
        st.markdown("**What these data can inform**")
        st.markdown("- Preliminary operating envelopes for temperature, residence time and heating rate.\n- Expected product-yield and quality ranges for feedstock families represented in the dataset.\n- Which feedstock/process combinations have enough observations for a defensible comparison.\n- Inputs for preliminary reactor sizing and heat-duty calculations in the Technical module.")
        st.markdown("**What these data cannot size on their own**")
        st.markdown("- Continuous throughput, reactor diameter/length, solids residence-time distribution or scale-up factor.\n- Feed preparation, drying, conveying, emissions control, gas cleaning, quenching, storage and fire protection.\n- Heat-transfer coefficients, pressure drop, equipment turndown and plant availability.")
        st.warning("The literature dataset is predominantly slow pyrolysis. Fast pyrolysis and gasification have very few rows; do not treat their medians as robust design recommendations. Full plant design requires reactor-specific and vendor data.")
    with tabs[4]:
        section("Economics: evidence boundary")
        st.markdown("The bundled structured experimental dataset contains process conditions and biochar properties, **not a comparable plant-cost or market-price dataset**. It therefore cannot support defensible claims about CAPEX, OPEX, biochar selling price, payback or project profitability on this dashboard.")
        st.markdown("**Commercial evidence that must be aggregated separately**")
        st.markdown("- Installed equipment cost by capacity, reactor technology, country of manufacture and quotation date.\n- Feedstock purchase price, collection radius, transport cost, seasonal availability and competing uses.\n- Electricity, fuel, labour, maintenance, water, disposal and emissions-control costs.\n- Biochar offtake prices by application, quality grade, contract volume and delivery basis.\n- Carbon-credit methodology, monitoring/verification cost, issuance risk and realised transaction price.")
        st.info("The Economic module remains a scenario calculator. Its editable prices and cost assumptions must not be presented as literature-verified market facts until source-backed cost records and supplier quotations are added.")
    with tabs[5]:
        section("Trace findings back to the original publications")
        src = view[["Publication year", "Title", "Journal", "DOI", "Feedstock", "Feedstock_class", "Pyrolysis_type", "HTT", "Pyrolysis_duration", "Heating_rate", "Yield", "C", "Ash", "H_C"]].drop_duplicates().sort_values("Publication year", ascending=False).head(250)
        src = src.copy(); src["DOI link"] = src["DOI"].apply(lambda x: f"https://doi.org/{x}" if pd.notna(x) and str(x).strip() else "")
        st.dataframe(src.drop(columns=["DOI"]), width="stretch", hide_index=True, column_config={"DOI link":st.column_config.LinkColumn("Open source DOI")})
        st.caption("The structured records are drawn from the bundled biochar production dataset (April 2024). Values remain attached to their publication and experimental conditions. Missing fields are not imputed for this dashboard.")

# ================================================================== ROUGH ESTIMATES
elif page == "Rough estimates":
    header("Rough estimates", "Fast screening from the trained prediction models: choose a process, feedstock and conditions.")
    pred = get_predictor(); d = scenario_controls("est")
    feed, process, htt, dur, hr = d["feed"], d["process"], d["htt"], d["dur"], d["hr"]; cls = FEEDSTOCKS[feed]["cls"]
    p0, e0, r = design_inputs(pred, feed, htt, dur, hr, replace(S.process, wet_feed_t_y=10000.0), S.economics, d["liquid_share"], process=process)
    t0 = calculate_technical(p0); ec0 = calculate_economics(t0, p0, e0); sf = p0.stable_carbon_fraction
    if process != "slow_pyrolysis": st.warning(f"{PROCESSES[process]['label']}: {PROCESSES[process]['status']}")
    elif r["extrapolating"]: st.warning("Outside the observed temperature range for this feedstock class: treat as extrapolation.")
    tabs = st.tabs(["Estimate", "Trends", "Model validation", "Mathematical model", "Calculation log"])
    with tabs[0]:
        sd = lambda k: f"\u00b1{r[k]['std']:.2g} (tree spread)" if r[k]["std"] else PROCESSES[process]["yield_source"]
        section("Predicted product")
        kpis([("Char / solid yield", f"{r['Yield']['mean']:.1f}", sd("Yield"), "wt% dry"), ("Carbon in char", f"{r['C']['mean']:.1f}", sd("C"), "wt%"), ("H/C molar", f"{r['H_C']['mean']:.2f}", sd("H_C")),
              ("Stable-C fraction", f"{sf:.2f}", "placeholder H/C map")])
        st.caption("H/C below 0.7 is the usual biochar quality limit. Tree spread is not a calibrated interval.")
        section("Rough result per 10,000 t/y wet feed")
        kpis([("Biochar / solid", fmt(t0["char_t_y"]), "", "t/y"), ("Removal proxy", fmt(t0["net_removal_proxy_tco2e_y"]), "screening", "tCO\u2082e/y"),
              ("Carbon retained", f"{t0['carbon_retained_fraction']:.0%}", "feasible" if t0["carbon_balance_ok"] else "INFEASIBLE: more C in char than in feed"), ("Economic surplus", fmt(ec0["annual_economic_surplus_usd_y"]), "placeholder prices", "USD/y")])
        if st.button("Use these conditions as the active scenario", type="primary"): S.yield_source = "Predicted (data-driven)"; st.toast("Scenario set: see Technical, Economic, Optimize.")
    with tabs[1]:
        if process != "slow_pyrolysis": st.info("Trend curves come from the slow-pyrolysis predictor. Select slow pyrolysis to see them.")
        else:
            htts = np.arange(300, 801, 25); df = pred.data; cols = st.columns(2)
            for col, tgt, ttl in [(cols[0], "Yield", "Char yield (wt%)"), (cols[1], "H_C", "H/C (molar)")]:
                mu, sdv = pred.curve(cls, htts, dur, hr, tgt); sub = df[(df.Feedstock_class == cls) & df[tgt].notna()]
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=sub.HTT, y=sub[tgt], mode="markers", name="Literature", marker=dict(size=6, opacity=.35, color=GREY)))
                fig.add_trace(go.Scatter(x=np.r_[htts, htts[::-1]], y=np.r_[mu + sdv, (mu - sdv)[::-1]], fill="toself", line=dict(width=0), fillcolor="rgba(31,122,90,.18)", name="\u00b11 spread", hoverinfo="skip"))
                fig.add_trace(go.Scatter(x=htts, y=mu, name="Prediction", line=dict(color=GREEN, width=3)))
                if tgt == "H_C": fig.add_hline(y=0.7, line_dash="dot", annotation_text="0.7 limit")
                fig.update_layout(title=f"{ttl} ({cls}, n={len(sub)})", xaxis_title="HTT (\u00b0C)")
                with col, st.container(border=True): st.plotly_chart(style_fig(fig, 320), width="stretch")
    with tabs[2]:
        cv = pd.DataFrame([{"Target": TARGETS[k_], "Observations": v["n"], "Papers": v["papers"], "CV R\u00b2 (held-out papers)": round(v["r2"], 2), "Class-mean baseline R\u00b2": round(v["baseline_r2"], 2), "MAE": round(v["mae"], 2)} for k_, v in pred.cv.items()])
        st.dataframe(cv, width="stretch", hide_index=True)
        st.caption("Cross-validation holds out whole publications. Yield and H/C beat the baseline clearly; carbon and ash are about at baseline. Fixed carbon and O/C were tested and dropped (no skill). The dataset contains 1,350 slow, 13 fast and 7 gasification rows, so only slow pyrolysis is modelled from data.")
        source_note(["ML-001", "PERM-001"])
    with tabs[3]: render_math("estimates")
    with tabs[4]: log_view(log_estimates(feed, cls, htt, dur, hr, r, sf, t0, ec0, process), "estimates_log")
    snap = {"process": PROCESSES[process]["label"], "process_status": PROCESSES[process]["status"], "feedstock": feed, "HTT_C": htt, "residence_min": dur, "prediction": r, "stable_fraction": sf,
            "cv": {k_: {"r2": v["r2"], "baseline_r2": v["baseline_r2"]} for k_, v in pred.cv.items()},
            "per_10kt_wet": {"char_t_y": t0["char_t_y"], "removal_proxy": t0["net_removal_proxy_tco2e_y"], "carbon_retained": t0["carbon_retained_fraction"]},
            "assumption_status": "Stable fraction map, feed carbon, HTC lines are placeholders/typical values."}
    ai_panel("Rough estimates", _r(snap), fallback=[f"Predicted char yield {r['Yield']['mean']:.1f}% and H/C {r['H_C']['mean']:.2f}."])

# ================================================================== TECHNICAL
elif page == "Technical":
    header("Technical", "Understand the process step by step: material flows, energy demand, particle conversion and the calculations behind every result.")
    S.yield_source = st.radio("Product yields come from", ["Predicted (data-driven)", "Manual inputs"], horizontal=True, index=0 if PRED() else 1)
    if PRED(): scenario_controls("tech")
    else:
        with st.container(border=True):
            names = list(PROCESSES); sel = st.selectbox("Process", names, index=names.index(S.design["process"]), format_func=lambda n: PROCESSES[n]["label"], key="tech_proc_m")
            if sel != S.design["process"]: set_process(sel); st.rerun()
            S.design["dur"] = float(st.number_input("Residence time (min)", 0.02, 600.0, float(S.design["dur"]), 1.0, key="t_dur_m"))
            S.process = process_inputs("man")
    with st.expander("Edit process, plant and particle inputs", expanded=False):
        if PRED(): S.process = plant_inputs(S.process)
        st.markdown("**Particle model**"); particle_inputs()
    R = pipeline(); t, p, sim, pp, pr = R["t"], R["p"], R["sim"], R["pp"], R["pr"]
    chips(status_checks(R))
    if pr and S.design["process"] == "slow_pyrolysis": st.caption(f"Predicted: yield {pr['Yield']['mean']:.1f}% \u00b1{pr['Yield']['std']:.1f}, carbon {pr['C']['mean']:.0f}%, H/C {pr['H_C']['mean']:.2f}.")
    st.markdown("**How to use this analysis**  \n1. Check how much feed becomes each product.  2. Inspect the heat required to run the process.  3. Check whether particles heat and convert within the available residence time.  4. Open the audit tabs to inspect equations, assumptions and verification.")
    tabs = st.tabs(["1 · Material balance", "2 · Heat & energy", "3 · Particle behaviour", "4 · Calculation log", "5 · Assumptions & models", "6 · Equations", "7 · Verification"])
    with tabs[0]:
        st.caption("Start with the overall dry-feed balance. The Sankey shows where the dry biomass goes; the table gives the exact annual mass flow.")
        c1, c2 = st.columns([3, 2])
        with c1, st.container(border=True): st.plotly_chart(sankey(t), width="stretch")
        with c2:
            rows = [["Wet feed", t["wet_feed_t_y"]], ["Water in feed", t["feed_water_t_y"]], ["Dry feed", t["dry_feed_t_y"]], ["Biochar / solid", t["char_t_y"]], ["Liquid", t["liquid_t_y"]], ["Gas", t["gas_t_y"]], ["Other", t["other_t_y"]], ["Residual", t["mass_balance_residual_t_y"]]]
            if p.process_type == "htc": rows.insert(2, ["Slurry water (circulating)", t["slurry_water_t_y"]])
            st.dataframe(pd.DataFrame(rows, columns=["Stream", "t/y"]).round(3), width="stretch", hide_index=True)
        section("Carbon balance")
        kpis([("Carbon in dry feed", fmt(t["feed_carbon_t_y"]), "typical feed C fraction", "t/y"), ("Carbon in char", fmt(t["char_carbon_t_y"]), "", "t/y"),
              ("Retained in char", f"{t['carbon_retained_fraction']:.0%}", "must be \u2264 100%"), ("Stable carbon \u2192 CO\u2082", fmt(t["gross_stored_co2_t_y"]), "gross", "t/y")])
        if not t["carbon_balance_ok"]: st.error("Infeasible: char holds more carbon than the feed supplies. Check the yield/carbon inputs or the feed carbon fraction.")
    with tabs[1]:
        st.caption("Heat demand is built from separate physical contributions. Compare the bars to identify the dominant duty, then inspect the table for the net process requirement.")
        st.caption(f"Water properties: {t['water_property_source']}. Reaction heat: {p.pyrolysis_enthalpy_kJ_kg_dry:.0f} kJ/kg (user assumption)." + (" HTC: no vaporisation; heat recovery applied." if p.process_type == "htc" else ""))
        terms = pd.DataFrame([["Water sensible", t["water_sensible_GJ_y"]], ["Vaporisation", t["water_vaporisation_GJ_y"]], ["Steam superheat", t["steam_superheat_GJ_y"]], ["Dry solids", t["solids_sensible_GJ_y"]],
                              ["Reaction heat", t["reaction_heat_GJ_y"]], ["Losses", t["gross_heat_duty_GJ_y"] - t["useful_process_heat_GJ_y"]], ["Efficiency penalty", t["purchased_heat_requirement_GJ_y"] - t["gross_heat_duty_GJ_y"]]], columns=["Term", "GJ/y"])
        c1, c2 = st.columns([3, 2])
        with c1, st.container(border=True): st.plotly_chart(style_fig(px.bar(terms, x="Term", y="GJ/y", color_discrete_sequence=[BLUE]), 320, legend=False), width="stretch")
        with c2:
            st.dataframe(pd.DataFrame([["Useful process heat", t["useful_process_heat_GJ_y"]], ["Purchased heat requirement", t["purchased_heat_requirement_GJ_y"]], ["Co-product chemical energy", t["coproduct_chemical_energy_GJ_y"]],
                                       ["Recoverable co-product heat", t["recoverable_coproduct_heat_GJ_y"]], ["Heat deficit", t["heat_deficit_GJ_y"]], ["Heat surplus", t["heat_surplus_GJ_y"]]], columns=["Quantity", "GJ/y"]).round(1), width="stretch", hide_index=True)
        st.caption("Screening balance: sensible heat, phase change, constant solids cp. No reactor heat-transfer area, oxidant demand or gas-phase reactions.")
    with tabs[2]:
        st.caption("The particle model answers two practical questions: how quickly heat reaches the particle centre, and how quickly the model predicts devolatilisation. Compare both with the selected residence time.")
        if sim is None: st.info("The particle model does not apply to hydrothermal carbonisation.")
        else:
            kpis([("Time to 95% conversion", f"{(sim['t_target_s'] or float('nan'))/60:.3g}", "min" + (" (indicative for this process)" if R['proc']['particle'] != 'full' else "")), ("Centre within 5 K of gas", f"{(sim['t_center_within_5K_s'] or float('nan'))/60:.3g}", "min"),
                  ("Biot number", f"{sim['Biot']:.2f}", "hR / k"), ("Regime", sim["regime"].split()[0].capitalize(), f"\u03c4 heat {sim['tau_heat_s']:.3g} s \u00b7 \u03c4 kin {sim['tau_kin_s']:.3g} s")])
            tm = sim["t_s"] / 60; c1, c2 = st.columns(2)
            fig = go.Figure(); fig.add_trace(go.Scatter(x=tm, y=sim["T_surface_C"], name="Surface", line=dict(color=AMBER, width=2.5))); fig.add_trace(go.Scatter(x=tm, y=sim["T_center_C"], name="Centre", line=dict(color=GREEN, width=2.5)))
            fig.add_hline(y=pp.T_inf_C, line_dash="dot", annotation_text="Gas / reactor T"); fig.update_layout(xaxis_title="Time (min)", yaxis_title="Temperature (\u00b0C)", title="Particle temperature")
            with c1, st.container(border=True): st.plotly_chart(style_fig(fig, 320), width="stretch")
            fig = go.Figure(go.Scatter(x=tm, y=sim["X_mean"], line=dict(color=BLUE, width=3), name="Conversion")); fig.add_hline(y=0.95, line_dash="dot", annotation_text="95%")
            if sim["t_target_s"]: fig.add_vline(x=sim["t_target_s"] / 60, line_dash="dot")
            fig.add_vline(x=R["dur_min"], line_color=RED, annotation_text="Residence time"); fig.update_layout(xaxis_title="Time (min)", yaxis_title="Virgin material converted", title="Devolatilisation progress")
            with c2, st.container(border=True): st.plotly_chart(style_fig(fig, 320, legend=False), width="stretch")
            fig = go.Figure()
            for s_ in sim["snapshots"]: fig.add_trace(go.Scatter(x=s_["r_mm"], y=s_["T_C"], name=f"{s_['t_s']/60:.2g} min", mode="lines"))
            fig.update_layout(xaxis_title="Radius (mm)", yaxis_title="Temperature (\u00b0C)", title="Radial temperature profiles")
            with st.container(border=True): st.plotly_chart(style_fig(fig, 320), width="stretch")
            st.info("Reduced-order particle model (1-D spherical conduction + one-step kinetics), verified against the analytical conduction solution. It does not include gas flow, pressure, shrinkage or bed effects; in a packed or rotating bed heat-up is slower than for a single particle in hot gas, so treat conversion time as a lower bound.")
            if sim.get("kinetics_extrapolated"):
                st.warning("Kinetic extrapolation: the cited beech-wood Arrhenius parameters were fitted over 573–708 K (about 300–435 °C). The selected particle gas temperature is outside that range; the predicted conversion time is an extrapolation, not a validated residence-time design value.")
    with tabs[3]: log_view(log_technical(R), "technical_log")
    with tabs[4]:
        st.dataframe(assumptions_table(R), width="stretch", hide_index=True)
        section("Models used"); source_note(["MASS-001", "ENERGY-001", "PYRO-001", "ML-001", "PERM-001", "PART-001", "KIN-001"])
    with tabs[5]: render_math("technical")
    with tabs[6]:
        ver = verification_cached(); st.markdown("**Particle solver vs analytical sphere solution** (constant properties, fixed surface temperature, no reaction)")
        st.dataframe(pd.DataFrame(ver["rows"]).round(3), width="stretch", hide_index=True)
        from engine.thermo import water_enthalpies, liquid_water_heating_kJ_kg
        dry, water = t["dry_feed_t_y"], t["feed_water_t_y"]
        if p.process_type == "htc": wtot = (t["slurry_water_t_y"] * liquid_water_heating_kJ_kg(p.feed_temp_C, p.reactor_temp_C)["kJ_kg"]); hand = ((wtot + dry * p.solid_cp_kJ_kgK * (p.reactor_temp_C - p.feed_temp_C) + dry * p.pyrolysis_enthalpy_kJ_kg_dry) / 1000) * (1 - p.htc_heat_recovery_fraction)
        else:
            w = water_enthalpies(p.feed_temp_C, p.reactor_temp_C, cp_w=p.water_cp_kJ_kgK, cp_v=p.steam_cp_kJ_kgK, hfg=p.water_latent_kJ_kg) if p.use_steam_tables else {"sensible": p.water_cp_kJ_kgK * (100 - p.feed_temp_C), "latent": p.water_latent_kJ_kg, "superheat": p.steam_cp_kJ_kgK * max(0, p.reactor_temp_C - 100)}
            hand = (water * (w["sensible"] + w["latent"] + w["superheat"]) + dry * p.solid_cp_kJ_kgK * (p.reactor_temp_C - p.feed_temp_C) + dry * p.pyrolysis_enthalpy_kJ_kg_dry) / 1000
        kpis([("Max particle-solver error", f"{ver['max_error_pct']:.3f}", "% of temperature rise"), ("Useful heat: platform", fmt(t["useful_process_heat_GJ_y"]), "", "GJ/y"), ("Useful heat: independent recalculation", fmt(hand), "", "GJ/y"),
              ("Difference", f"{abs(hand - t['useful_process_heat_GJ_y']):.1e}", "GJ/y"), ("Mass-balance residual", f"{t['mass_balance_residual_t_y']:.1e}", "t/y")])
        st.caption("Checks run live. Verification shows the equations are solved correctly; it does not validate them against a real reactor (see docs/VALIDATION_ROADMAP.md).")
    technical_ai_snapshot = snapshot(R, ["prediction", "technical"])
    technical_ai_snapshot["calculation_log"] = log_technical(R).to_dict(orient="records")
    ai_panel("Technical", technical_ai_snapshot, fallback=[f"Purchased heat {fmt(t['purchased_heat_requirement_GJ_y'])} GJ/y. The Technical tabs show equations, numerical inputs, calculation log and verification checks."])

# ================================================================== ECONOMIC
elif page == "Economic":
    header("Economic", "See where the money goes, where revenue comes from, and which assumptions control project viability.")
    with st.expander("Edit financial assumptions · placeholder values until verified", expanded=False): S.economics = econ_inputs("econ")
    R = pipeline(); t, ec, p, e = R["t"], R["ec"], R["p"], R["e"]
    st.markdown(f"**Technical basis:** {R['proc']['label']} \u00b7 {S.design['feed'] if PRED() else 'manual inputs'} \u00b7 {p.reactor_temp_C:.0f} \u00b0C \u00b7 {fmt(t['char_t_y'])} t/y solid \u00b7 removal proxy {fmt(t['net_removal_proxy_tco2e_y'])} tCO\u2082e/y")
    be = breakeven_carbon_price(ec, t)
    kpis([("Revenue", fmt(ec["total_revenue_usd_y"]), "", "USD/y"), ("Operating cost", fmt(ec["operating_cost_usd_y"]), "", "USD/y"), ("Economic surplus", fmt(ec["annual_economic_surplus_usd_y"]), "after capital recovery", "USD/y"),
          ("NPV", fmt(ec["npv_usd"]), "", "USD"), ("IRR", f"{ec['irr']:.1%}" if ec["irr"] is not None else "n/a", f"payback {fmt(ec['simple_payback_y'])} y" if ec["simple_payback_y"] else ""), ("Breakeven carbon price", fmt(be) if be is not None else "n/a", "surplus = 0", "USD/t")])
    st.info("Follow the financial story from left to right: project cash flow → cost and revenue drivers → unit economics → sensitivity → calculation audit. Edit the assumptions above to test a scenario; replace placeholder values with quotations before treating results as investment estimates.")
    tabs = st.tabs(["1 · Cash flow", "2 · Cost & revenue drivers", "3 · Unit economics", "4 · Sensitivity", "5 · Calculation log", "6 · Model equations"])
    with tabs[0]:
        st.caption("This is the project-level cash-flow picture: initial capital outlay followed by the modelled annual operating cash flow. It is undiscounted in this chart; NPV is shown above.")
        yrs = np.arange(0, int(e.project_life_y) + 1); cum = -e.capex_usd + ec["ebitda_like_usd_y"] * yrs
        fig = go.Figure(go.Scatter(x=yrs, y=cum, fill="tozeroy", line=dict(color=GREEN, width=3), fillcolor="rgba(31,122,90,.15)")); fig.add_hline(y=0, line_color=GREY)
        fig.update_layout(xaxis_title="Year", yaxis_title="USD", title="Cumulative cash flow (undiscounted)")
        with st.container(border=True): st.plotly_chart(style_fig(fig, 340, legend=False), width="stretch")
        st.caption("Constant annual EBITDA-like cash flow; no taxes, debt, working capital, escalation or replacement CAPEX.")
    with tabs[1]:
        st.caption("Positive bars are revenue; negative bars are costs. This view identifies the largest contributors to annual operating performance.")
        rows = [["Feedstock + logistics", -ec["feedstock_logistics_cost_usd_y"]], ["Electricity", -ec["electricity_cost_usd_y"]], ["Purchased heat", -ec["purchased_heat_cost_usd_y"]], ["Labour", -ec["labour_usd_y"]], ["Maintenance", -ec["maintenance_usd_y"]],
                ["Other OPEX", -ec["other_opex_usd_y"]], ["Biochar sales", ec["char_revenue_usd_y"]], ["Liquid sales", ec["liquid_revenue_usd_y"]], ["Electricity export", ec["electricity_revenue_usd_y"]], ["Carbon credits", ec["carbon_revenue_usd_y"]]]
        df = pd.DataFrame(rows, columns=["Item", "USD/y"]); df["Type"] = np.where(df["USD/y"] >= 0, "Revenue", "Cost")
        with st.container(border=True): st.plotly_chart(style_fig(px.bar(df, x="Item", y="USD/y", color="Type", color_discrete_map={"Revenue": GREEN, "Cost": RED}), 340), width="stretch")
        if e.carbon_credit_usd_tco2e > 0: st.warning("Carbon revenue assumes the removal proxy is verified and creditable. It is a screening proxy today.")
    with tabs[2]:
        st.caption("Unit economics normalise the project totals by tonnes of product or tonnes of removal proxy. These are scenario-derived costs, not market quotations.")
        char = max(t["char_t_y"], 1e-9); rem = t["net_removal_proxy_tco2e_y"]; tc = ec["operating_cost_usd_y"] + ec["annualised_capex_usd_y"]; nan = float("nan")
        u = pd.DataFrame([["Full cost per tonne solid product", tc / char, "USD/t"], ["Cost per tCO2e removed (full cost)", tc / rem if rem > 0 else nan, "USD/tCO2e"],
                          ["Cost per tCO2e net of non-carbon revenue", max(0, tc - (ec["total_revenue_usd_y"] - ec["carbon_revenue_usd_y"])) / rem if rem > 0 else nan, "USD/tCO2e"], ["Breakeven carbon price", be if be is not None else nan, "USD/tCO2e"],
                          ["Assumed carbon price", e.carbon_credit_usd_tco2e, "USD/tCO2e"]], columns=["Metric", "Value", "Unit"])
        st.dataframe(u.round(2), width="stretch", hide_index=True); st.caption("Compare with the indicative biochar range on the dashboard (IPCC AR6, roughly 10-345 USD/tCO2; still to be re-verified).")
    with tabs[3]:
        st.caption("Change one input at a time and see how much annual economic surplus moves. This is a local sensitivity screen; it does not capture interactions between variables.")
        swing = st.slider("Swing on each input (\u00b1%)", 5, 50, 20, 5) / 100; base, rows = tornado(p, e, swing); fig = go.Figure()
        fig.add_trace(go.Bar(y=[r["input"] for r in rows], x=[r["low"] for r in rows], orientation="h", name=f"-{swing:.0%}", marker_color=RED)); fig.add_trace(go.Bar(y=[r["input"] for r in rows], x=[r["high"] for r in rows], orientation="h", name=f"+{swing:.0%}", marker_color=GREEN))
        fig.update_layout(barmode="overlay", yaxis=dict(autorange="reversed"), xaxis_title="Change in annual economic surplus (USD/y)")
        with st.container(border=True): st.plotly_chart(style_fig(fig, 420), width="stretch")
        st.caption(f"Base surplus {base:,.0f} USD/y. One-at-a-time swings; interactions not shown.")
    with tabs[4]:
        st.caption("Every row shows the equation, numerical inputs, calculated result, units and model/source identifier. Download the table to audit or reuse the scenario calculations.")
        log_view(log_economic(R), "economic_log")
        source_note(["ECON-001"])
    with tabs[5]:
        st.caption("Definitions of the financial equations used by the screening model.")
        render_math("economic")
    ai_panel("Economic", snapshot(R, ["technical", "economics"]), fallback=[f"Economic surplus {fmt(ec['annual_economic_surplus_usd_y'])} USD/y; breakeven carbon price {fmt(be) if be is not None else 'n/a'}."])

# ================================================================== OPTIMIZE
else:
    header("Design optimiser", "Compare feasible slow-pyrolysis designs using the same feedstock, plant basis and technical/economic models.")
    pred = get_predictor()
    st.info("Scope: this optimiser currently searches slow pyrolysis only. Fast pyrolysis, torrefaction, gasification and HTC use screening-level or cross-process assumptions and are not comparable enough for a defensible combined optimum.")
    with st.container(border=True):
        st.subheader("1 · Define the design problem")
        st.caption("Fixed plant basis is inherited from the Technical and Economic pages. Choose which feedstocks and operating conditions the optimiser may vary.")
        feeds = st.multiselect("Feedstocks to compare", list(FEEDSTOCKS), default=[S.design.get("feed", "Rice straw")] if S.design.get("feed", "Rice straw") in FEEDSTOCKS else ["Rice straw"])
        a, b = st.columns(2)
        temp_range = a.slider("Reactor temperature search range (°C)", 300, 800, (400, 600), 10)
        duration_choices = b.multiselect("Residence times to test (min)", [15, 30, 60, 120, 240], default=[30, 60, 120])
        a, b = st.columns(2)
        cc = a.number_input("Carbon-credit scenario price (USD/tCO₂e)", min_value=0.0, max_value=1000.0, value=float(S.economics.carbon_credit_usd_tco2e), step=5.0, help="Scenario assumption only; zero excludes carbon revenue.")
        ls = b.slider("Liquid fraction of non-char products", 0.0, 1.0, float(S.design["liquid_share"]), 0.05)
        st.subheader("2 · Define the objective and feasibility rules")
        a, b = st.columns(2)
        objective = a.selectbox("Primary objective", ["Maximize NPV", "Maximize annual economic surplus", "Maximize net removal proxy", "Minimize break-even carbon price"])
        max_hc = b.number_input("Maximum biochar H/C ratio", min_value=0.1, max_value=2.0, value=0.7, step=0.05)
        a, b = st.columns(2)
        use_particle = a.checkbox("Require particle conversion within residence time", value=True)
        safety = b.slider("Conversion-time safety factor", 1.0, 3.0, 1.5, 0.1, disabled=not use_particle)
        st.caption("The H/C limit and particle conversion rule are engineering screening constraints. Particle properties (diameter, heat transfer and kinetics) are taken from the Technical page. The optimizer uses a nominal 0.30 char fraction and 5 s time steps for the particle screening calculation to keep the grid search responsive.")
        run = st.button("Evaluate design grid", type="primary", disabled=not feeds or not duration_choices)
    st.caption("Feedstock moisture, carbon content, feedstock cost and logistics are preset screening assumptions in engine/design.py. Verify them against local measurements and supplier data before treating rankings as investment recommendations.")
    if run and feeds and duration_choices:
        be_ = replace(S.economics, carbon_credit_usd_tco2e=float(cc))
        with st.spinner("Evaluating candidate operating points..."):
            pp = make_pp(float(sum(temp_range)/2), 0.3, "slow_pyrolysis") if use_particle else None
            rows, front, stats = search_designs(
                pred, S.process, be_, feeds=feeds, htt_range=temp_range, step=20,
                durations=tuple(duration_choices), rates=(5, 10, 20), max_hc=float(max_hc),
                liquid_share=ls, processes=("slow_pyrolysis",),
                particle={"slow_pyrolysis": pp} if pp else None, safety=safety
            )
        for r_ in rows:
            gap = r_["annualised_capex_usd_y"] + r_["operating_cost_usd_y"] - (r_["total_revenue_usd_y"] - r_["carbon_revenue_usd_y"])
            r_["breakeven_cc"] = max(0.0, gap / r_["net_removal_proxy_tco2e_y"]) if r_["net_removal_proxy_tco2e_y"] > 0 else float("inf")
        objective_keys = {
            "Maximize NPV": lambda r_: -r_["npv_usd"],
            "Maximize annual economic surplus": lambda r_: -r_["annual_economic_surplus_usd_y"],
            "Maximize net removal proxy": lambda r_: -r_["net_removal_proxy_tco2e_y"],
            "Minimize break-even carbon price": lambda r_: r_["breakeven_cc"],
        }
        S.opt = {"rows": rows, "front": front, "stats": stats, "objective": objective, "cc": cc, "ls": ls,
                 "processes": ["slow_pyrolysis"], "constrain": True, "max_hc": max_hc,
                 "use_particle": use_particle, "safety": safety, "temp_range": temp_range,
                 "durations": duration_choices, "best": min(rows, key=objective_keys[objective]) if rows else None}
    o = S.get("opt")
    tabs = st.tabs(["Recommended design", "Compare candidates", "Calculation & constraints", "Model scope"])
    with tabs[0]:
        if o:
            st.caption(f"Objective: {o['objective']} · Slow pyrolysis · {o['temp_range'][0]}–{o['temp_range'][1]} °C · residence times {', '.join(map(str, o['durations']))} min")
            st.metric("Candidate operating points evaluated", f"{o['stats']['evaluated']:,}")
            if o["best"]:
                best = o["best"]
                st.success("Best feasible candidate within the tested grid — not a globally proven optimum.")
                kpis([("Feedstock", best["feedstock"], "screening preset"), ("Temperature", f"{best['HTT']:.0f} °C", "reactor set point"),
                      ("Residence time", f"{best['duration_min']:.0f} min", "tested grid"), ("Heating rate", f"{best['heating_rate']:.0f} °C/min", "tested grid"),
                      ("Biochar", fmt(best["char_t_y"]), "t/y"), ("Predicted H/C", f"{best['pred_H_C']:.2f}", "model prediction"),
                      ("Annual surplus", fmt(best["annual_economic_surplus_usd_y"]), "USD/y"),
                      ("NPV", fmt(best["npv_usd"]), "USD"),
                      ("Net removal proxy", fmt(best["net_removal_proxy_tco2e_y"]), "tCO₂e/y")])
                if best["extrapolating"]: st.warning("This candidate uses extrapolated ML property predictions; do not treat its ranking as reliable.")
                if best.get("particle_kinetics_extrapolated", False): st.warning("Particle kinetics are extrapolated: the cited beech-wood kinetic fit covers approximately 300–435 °C, while this candidate is outside that range.")
                st.markdown("**Why this candidate was selected**")
                st.write(f"It has the best value of **{o['objective']}** among {len(o['rows']):,} candidates that passed the enabled constraints. Its ranking is conditional on the selected feedstock presets, prices, carbon-credit scenario, particle assumptions and tested grid.")
                st.write(f"Predicted char yield is {best['pred_yield_pct']:.1f}% and predicted H/C is {best['pred_H_C']:.2f}. The calculated heat deficit is {fmt(best['heat_deficit_GJ_y'])} GJ/y; estimated annual operating cost is {fmt(best['operating_cost_usd_y'])} USD/y.")
                if st.button("Apply selected conditions to Technical and Economic", type="primary"):
                    S.design = {"process": "slow_pyrolysis", "feed": best["feedstock"], "htt": float(best["HTT"]),
                                "dur": float(best["duration_min"]), "hr": float(best["heating_rate"]), "liquid_share": o["ls"]}
                    pr_ = PROCESSES["slow_pyrolysis"]
                    S.particle["d"], S.particle["h"] = pr_["particle_defaults"]["d"], pr_["particle_defaults"]["h"]
                    S.economics = replace(S.economics, carbon_credit_usd_tco2e=float(o["cc"]))
                    S.yield_source = "Predicted (data-driven)"
                    st.toast("Selected conditions applied to the active scenario.")
            else:
                st.warning("No candidate passed the enabled constraints. Review the H/C threshold, particle size and conversion-time assumptions, or expand the tested temperature/residence-time grid.")
        else:
            st.info("Define the design problem and select **Evaluate design grid**.")
    with tabs[1]:
        if o and o["rows"]:
            df = pd.DataFrame(o["rows"])
            show_cols = ["feedstock", "HTT", "duration_min", "heating_rate", "pred_yield_pct", "pred_H_C",
                         "char_t_y", "heat_deficit_GJ_y", "operating_cost_usd_y", "annual_economic_surplus_usd_y",
                         "npv_usd", "net_removal_proxy_tco2e_y", "breakeven_cc"]
            st.dataframe(df[show_cols].rename(columns={"HTT":"Temperature °C", "duration_min":"Residence min",
                "heating_rate":"Heating rate °C/min", "pred_yield_pct":"Predicted yield %", "pred_H_C":"H/C",
                "char_t_y":"Biochar t/y", "heat_deficit_GJ_y":"Heat deficit GJ/y",
                "operating_cost_usd_y":"OPEX USD/y", "annual_economic_surplus_usd_y":"Annual surplus USD/y",
                "npv_usd":"NPV USD", "net_removal_proxy_tco2e_y":"Removal proxy tCO₂e/y",
                "breakeven_cc":"Break-even carbon price USD/tCO₂e"}).round(2), width="stretch", hide_index=True)
            st.caption("All monetary results are USD scenario estimates. Feedstock costs, product prices and CAPEX are assumptions, not supplier quotations.")
            fr = pd.DataFrame(o["front"])
            fig = px.scatter(df, x="net_removal_proxy_tco2e_y", y="npv_usd", color="feedstock",
                             hover_data=["HTT", "duration_min", "heating_rate", "pred_yield_pct", "pred_H_C"])
            if not fr.empty:
                fig.add_trace(go.Scatter(x=fr.net_removal_proxy_tco2e_y, y=fr.npv_usd, mode="markers",
                                         name="Pareto set (surplus vs removal)", marker=dict(size=13, symbol="star")))
            fig.update_layout(xaxis_title="Net removal proxy (tCO₂e/y)", yaxis_title="NPV (USD)",
                              title="Financial return versus carbon-removal proxy")
            with st.container(border=True): st.plotly_chart(style_fig(fig, 430), width="stretch")
        elif o:
            st.warning("No feasible candidates to compare.")
        else:
            st.info("Run the design grid to compare candidate configurations.")
    with tabs[2]:
        if o:
            st.subheader("Candidate accounting")
            kpis([("Evaluated", f"{o['stats']['evaluated']:,}", "grid points"),
                  ("Rejected: H/C", f"{o['stats']['rejected_hc']:,}", "above selected limit"),
                  ("Rejected: conversion", f"{o['stats']['rejected_conversion']:,}", "residence time too short"),
                  ("Rejected: carbon balance", f"{o['stats']['rejected_carbon']:,}", "carbon conservation check"),
                  ("Feasible", f"{len(o['rows']):,}", "remaining candidates")])
            st.markdown("**Selection rule**")
            st.code({"Maximize NPV": "arg max NPV", "Maximize annual economic surplus": "arg max annual surplus",
                     "Maximize net removal proxy": "arg max net removal proxy",
                     "Minimize break-even carbon price": "arg min break-even carbon price"}[o["objective"]], language="text")
            st.markdown("**Constraints applied**")
            st.write(f"- Biochar H/C ≤ {o['max_hc']:.2f}")
            st.write(f"- Particle conversion: {'required, with safety factor ' + str(o['safety']) if o['use_particle'] else 'not enforced'}")
            st.write("- Carbon balance: char carbon cannot exceed feedstock carbon.")
            st.write("**Important:** the search is exhaustive only over the discrete grid shown above. It does not optimize reactor geometry, pressure, heat-transfer equipment, scale, or supply-chain logistics.")
            log_view(log_optimize(o, o["constrain"], o["use_particle"], o["safety"]), "optimize_log")
        else:
            st.info("Run the design grid to generate the calculation and rejection log.")
    with tabs[3]:
        st.markdown("### What this optimiser can and cannot establish")
        st.markdown("- **Can:** rank discrete slow-pyrolysis temperature, residence-time, heating-rate and feedstock combinations using the current prediction, heat-balance and economic models.")
        st.markdown("- **Cannot:** establish a plant-wide optimum, size a reactor, optimize process equipment, or validate local feedstock supply and prices.")
        st.markdown("- **Model dependency:** yield and quality predictions are based on publication-grouped ML validation; per-target performance differs. Review Rough Estimates before relying on a prediction.")
        st.markdown("- **Economic dependency:** CAPEX, biochar price, utility prices and feedstock logistics are scenario inputs. Results are not a bankable feasibility study.")
        st.markdown("- **Carbon dependency:** removal is a screening proxy, not verified carbon removal or automatically creditable tonnes.")
    R = pipeline()
    ai_panel("Optimize", snapshot(R, ["prediction", "technical", "economics", "optimizer"]),
             fallback=["Interpret the selected candidate against the tested alternatives, identify the binding constraints, and explain which assumptions most affect its ranking."])
