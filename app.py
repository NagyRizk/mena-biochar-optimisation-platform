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
from engine.structure import descriptors, build_nano, build_micro
from ai.llm import ask, list_models, LLMError, DEFAULT_MODEL
import viz3d
import streamlit.components.v1 as components
from flowdiagram import pfd_html
from engine.flows import energy_flows
from engine.carbon import credit_calc, effective_price_on_gross

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
S.setdefault("chat", {}); S.setdefault("nav", "Overview")
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

@st.cache_data(show_spinner=False)
def structure_cached(htt, hc, ash, cls):
    d = descriptors(float(htt), float(hc), float(ash), cls)
    return d, build_nano(d), build_micro(d)

# ------------------------------------------------------------------ navigation, presets, callbacks
NAV = {"Overview": ("Overview", "Start here"),
       "Evidence": ("1 · Evidence", "What the literature reports"),
       "Case Studies": ("2 · Case studies", "Compare model outputs with published experiments"),
       "Biochar": ("3 · Biochar", "Properties and 3D structure"),
       "Process": ("4 · Process", "Mass, heat, particle behaviour"),
       "Economics": ("5 · Economics", "Cash flow and sensitivity"),
       "Optimize": ("6 · Optimize", "Find the best design")}
NAV_IDS = list(NAV)
PRESETS = {
    "Date palm \u00b7 540 \u00b0C": {"process": "slow_pyrolysis", "feed": "Date palm residues", "htt": 540, "dur": 120, "hr": 10, "liquid_share": 0.55},
    "Rice straw \u00b7 450 \u00b0C": {"process": "slow_pyrolysis", "feed": "Rice straw", "htt": 450, "dur": 60, "hr": 10, "liquid_share": 0.55},
    "Corn stover \u00b7 600 \u00b0C": {"process": "slow_pyrolysis", "feed": "Corn stover / cobs", "htt": 600, "dur": 60, "hr": 10, "liquid_share": 0.55},
    "Olive stones \u00b7 650 \u00b0C": {"process": "slow_pyrolysis", "feed": "Olive stones / pits", "htt": 650, "dur": 120, "hr": 10, "liquid_share": 0.55},
    "Sludge HTC \u00b7 220 \u00b0C": {"process": "htc", "feed": "Dewatered sewage sludge", "htt": 220, "dur": 60, "hr": 10, "liquid_share": 0.55},
}

def goto(page_id): S.nav = page_id

def _dur_value(name, dur):
    pr = PROCESSES[name]
    if pr["dur_options"]:
        return int(dur) if int(dur) in pr["dur_options"] else int(pr["dur_options"][3])
    return float(dur)

def apply_design(des):
    """Callback: push a full design into the sidebar widgets (widget state can only be set from callbacks)."""
    name = des["process"]; pr = PROCESSES[name]
    S.sb_proc = name; S.sb_feed = des["feed"]
    S[f"sb_htt_{name}"] = int(round(des["htt"])); S[f"sb_dur_{name}"] = _dur_value(name, des["dur"])
    S.sb_hr = int(round(des.get("hr", 10))); S.sb_ls = float(des.get("liquid_share", 0.55))
    S.design = {"process": name, "feed": des["feed"], "htt": float(des["htt"]), "dur": float(des["dur"]), "hr": float(des.get("hr", 10)), "liquid_share": float(des.get("liquid_share", 0.55))}
    S.particle["d"], S.particle["h"] = pr["particle_defaults"]["d"], pr["particle_defaults"]["h"]
    S.yield_source = "Predicted (data-driven)"

def apply_cc_price(price):
    S.economics = replace(S.economics, carbon_credit_usd_tco2e=float(price))
    st.toast(f"Economic model now uses {price:,.1f} USD per tonne of gross stored CO\u2082 (after deductions and fees).")

def apply_best(best, ls, cc):
    apply_design({"process": "slow_pyrolysis", "feed": best["feedstock"], "htt": best["HTT"], "dur": best["duration_min"], "hr": best["heating_rate"], "liquid_share": ls})
    S.economics = replace(S.economics, carbon_credit_usd_tco2e=float(cc))
    st.toast("Design applied to the scenario. Review it in Process and Economics.")

def on_proc_change():
    name = S.sb_proc; pr = PROCESSES[name]; set_process(name)
    S[f"sb_htt_{name}"] = int(pr["T_default"]); S[f"sb_dur_{name}"] = _dur_value(name, pr["dur_default"])

def stepper(cur):
    st.markdown('<div class="flowbar"></div>', unsafe_allow_html=True)
    ids = NAV_IDS
    cols = st.columns(len(ids))
    for c, sid in zip(cols, ids):
        c.button("\u2302 Home" if sid == "Overview" else NAV[sid][0], key=f"fl_{sid}", type="primary" if sid == cur else "secondary", width="stretch", on_click=goto, args=(sid,))

def nav_footer(cur):
    i = NAV_IDS.index(cur)
    st.markdown('<div class="foot"></div>', unsafe_allow_html=True)
    a, _, b = st.columns([2, 3, 2])
    if i > 0: a.button(f"\u2190 {NAV[NAV_IDS[i-1]][0]}", key="ft_prev", width="stretch", on_click=goto, args=(NAV_IDS[i-1],))
    if i < len(NAV_IDS) - 1: b.button(f"{NAV[NAV_IDS[i+1]][0]} \u2192", key="ft_next", type="primary", width="stretch", on_click=goto, args=(NAV_IDS[i+1],))

def scenario_strip():
    d = S.design; pr = PROCESSES[d["process"]]
    items = [pr["label"]] + ([d["feed"], f"{d['htt']:.0f} \u00b0C", f"{d['dur']:g} min"] + ([f"{d['hr']:.0f} \u00b0C/min"] if d["process"] == "slow_pyrolysis" else []) if PRED() else ["manual product yields"])
    st.markdown('<div class="strip"><span class="lbl">Scenario</span>' + "".join(f'<span class="it">{x}</span>' for x in items) + '<span class="hint">change it in the sidebar</span></div>', unsafe_allow_html=True)

# ------------------------------------------------------------------ sidebar
def _init_widgets():
    d = S.design
    S.setdefault("sb_proc", d["process"]); S.setdefault("sb_feed", d["feed"]); S.setdefault("sb_hr", int(d["hr"])); S.setdefault("sb_ls", float(d["liquid_share"]))
    for n, pr in PROCESSES.items():
        S.setdefault(f"sb_htt_{n}", int(d["htt"]) if n == d["process"] else int(pr["T_default"]))
        S.setdefault(f"sb_dur_{n}", _dur_value(n, d["dur"] if n == d["process"] else pr["dur_default"]))
_init_widgets()
S.setdefault("yield_source", "Predicted (data-driven)")

with st.sidebar:
    st.markdown('<div class="brand">MENA Biochar<span>Engineering platform</span></div>', unsafe_allow_html=True)
    st.write("")
    st.radio("Navigation", NAV_IDS, key="nav", format_func=lambda i: NAV[i][0], captions=[NAV[i][1] for i in NAV_IDS], label_visibility="collapsed")
    page = S.nav
    if page in ("Evidence", "Case Studies"):
        st.markdown('<div class="side-h">Scenario</div>', unsafe_allow_html=True)
        st.caption("The literature evidence is independent of your scenario. Your scenario controls appear again from step 2.")
    else:
        st.markdown('<div class="side-h">Scenario</div>', unsafe_allow_html=True)
        st.selectbox("Process", list(PROCESSES), key="sb_proc", format_func=lambda n: PROCESSES[n]["label"], on_change=on_proc_change)
        _proc = S.sb_proc; _pr = PROCESSES[_proc]
        if PRED():
            st.selectbox("Feedstock", list(FEEDSTOCKS), key="sb_feed")
            _lo, _hi = _pr["T"]
            st.slider("Temperature (\u00b0C)", _lo, _hi, step=10 if _hi - _lo >= 100 else 5, key=f"sb_htt_{_proc}")
            if _pr["dur_options"]: st.select_slider("Residence time (min)", list(_pr["dur_options"]), key=f"sb_dur_{_proc}")
            else: st.number_input("Residence time (min)", 0.02, 600.0, step=0.5 if _pr["dur_default"] >= 1 else 0.01, key=f"sb_dur_{_proc}")
            if _proc == "slow_pyrolysis":
                st.slider("Heating rate (\u00b0C/min)", 5, 30, key="sb_hr")
                with st.expander("More assumptions"):
                    st.slider("Liquid share of non-char products", 0.0, 1.0, step=0.05, key="sb_ls", help="Assumption, not predicted: how the non-char remainder splits between liquid and gas.")
        else:
            st.info("Manual product yields are active. Enter them on the Process page, or switch back under Advanced.")
    with st.expander("Advanced"):
        st.radio("Product yields come from", ["Predicted (data-driven)", "Manual inputs"], key="yield_source", help="Manual inputs let you type your own char/liquid/gas fractions on the Process page.")
    with st.expander("AI analyst settings", expanded=not bool(get_key())):
        st.text_input("Groq API key", type="password", key="groq_key", help="Kept only in this browser session. Or set GROQ_API_KEY / st.secrets.")
        st.text_input("Model", value=DEFAULT_MODEL, key="groq_model")
        if st.button("List available models") and get_key():
            try: S.groq_models = list_models(get_key())
            except LLMError as ex: st.error(str(ex))
        if S.get("groq_models"): st.caption("Available: " + ", ".join(S.groq_models[:12]))
    st.caption("Screening-level tool. Costs and several process inputs are placeholders; see the assumptions on each page.")

# keep the shared scenario dict in sync with the sidebar widgets
_d = S.design; _d["process"] = S.sb_proc; _d["feed"] = S.sb_feed; _d["htt"] = float(S[f"sb_htt_{S.sb_proc}"]); _d["dur"] = float(S[f"sb_dur_{S.sb_proc}"]); _d["hr"] = float(S.sb_hr); _d["liquid_share"] = float(S.sb_ls)

# ------------------------------------------------------------------ input helpers
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

def show_html(html, height):
    if hasattr(st, "iframe"): st.iframe(html, height=height)
    else: components.html(html, height=height)

def energy_sankey(e):
    names = []
    for a, b, v in e["links"]:
        for n in (a, b):
            if n not in names: names.append(n)
    col = {"Syngas energy": "#b0a8d8", "Bio-oil energy (diverted)": AMBER, "Recovered heat": "#ff7a66", "External heat": BLUE, "Surplus heat": GREEN, "Unrecovered": GREY, "Process requirement": "#33434d"}
    fig = go.Figure(go.Sankey(node=dict(label=names, pad=16, thickness=14, color=[col.get(n, "#7a8b99") for n in names]),
                    link=dict(source=[names.index(a) for a, b, v in e["links"]], target=[names.index(b) for a, b, v in e["links"]], value=[v for a, b, v in e["links"]], color="rgba(127,140,150,.28)")))
    return style_fig(fig, 340, legend=False)

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

# ================================================================== OVERVIEW
if page == "Overview":
    st.markdown("""<div class="hero"><div class="eyebrow">MENA \u00b7 carbon removal engineering</div><h1>Biochar Engineering Platform</h1>
<p>From feedstock to carbon-removal economics in five steps: read the evidence, predict what the biochar looks like, engineer the process, test the business case and search for the best design.</p>
<div class="tagrow"><span class="tag">Literature-trained predictor</span><span class="tag">3D structure viewer</span><span class="tag">Mass &amp; energy balances</span><span class="tag">Techno-economics</span><span class="tag">Design optimiser</span></div></div>""", unsafe_allow_html=True)
    section("Quick start \u00b7 choose a scenario")
    cols = st.columns(len(PRESETS))
    for c, (lab, des) in zip(cols, PRESETS.items()): c.button(lab, key=f"pre_{lab}", width="stretch", on_click=apply_design, args=(des,))
    st.caption("Or build your own in the sidebar. Every step below uses this one scenario.")
    section("Your scenario at a glance")
    try:
        p_, e_, pr_ = current_scenario(); t_ = calculate_technical(p_); ec_ = calculate_economics(t_, p_, e_)
        kpis([("Char yield", f"{p_.char_yield_dry * 100:.1f}", "of dry feed", "wt%"), ("Stable carbon", f"{p_.stable_carbon_fraction:.2f}", "fraction of char C"), ("Biochar", fmt(t_["char_t_y"]), f"per {fmt(t_['wet_feed_t_y'])} t/y wet feed", "t/y"),
              ("CO\u2082 credits", fmt(credit_calc(t_["gross_stored_co2_t_y"], 135, .15, .10, 8)["credits_t_y"]), "after 15% + 10% deductions", "t/y"), ("Credit revenue", fmt(credit_calc(t_["gross_stored_co2_t_y"], 135, .15, .10, 8)["revenue_usd_y"]), "at 135 USD/t (edit in Economics)", "USD/y"), ("Economic surplus", fmt(ec_["annual_economic_surplus_usd_y"]), "placeholder prices", "USD/y"), ("NPV", fmt(ec_["npv_usd"]), "placeholder prices", "USD")])
        scenario_strip()
    except Exception as ex:
        st.info(f"Complete the manual product yields on the Process page to see a summary. ({ex})")
    section("The workflow")
    steps = [("Evidence", "What do published experiments say about yield, quality and operating windows? The data behind the predictor."),
             ("Biochar", "Predict yield, carbon, ash and H/C for your scenario, then see the 3D carbon structure those properties imply."),
             ("Process", "Mass and carbon balance, heat duty and particle conversion time on a plant basis."),
             ("Economics", "Cash flow, cost drivers, unit costs and a sensitivity tornado."),
             ("Optimize", "Search feedstock, temperature and residence time for the best feasible design, then apply it back.")]
    cols = st.columns(5)
    for i, (c, (sid, desc_)) in enumerate(zip(cols, steps), 1):
        with c, st.container(border=True):
            st.markdown(f'<div class="stepnum">{i}</div><p class="stepcard-t">{NAV[sid][0].split(" \u00b7 ")[1]}</p><p class="stepcard-d">{desc_}</p>', unsafe_allow_html=True)
            st.button("Open", key=f"ov_{sid}", width="stretch", on_click=goto, args=(sid,))
    section("Read this first")
    st.info("This is a screening tool. Only slow pyrolysis is predicted from data. Prices, CAPEX, feed carbon, the liquid/gas split, particle properties and the carbon-permanence map are placeholders or typical values, labelled as such on every page. The 3D structure is a stylised visual driven by the predicted properties, not a molecular simulation.")
    nav_footer("Overview")

# ================================================================== EVIDENCE
elif page == "Evidence":
    stepper("Evidence")
    header("Literature evidence", "What published experiments report about yield, quality and operating windows. This is the dataset that trains the predictors in step 2.")
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
    nav_footer("Evidence")

# ================================================================== CASE STUDIES
elif page == "Case Studies":
    stepper("Case Studies")
    header("Ground cases & model comparison", "Published laboratory and pilot-plant results placed beside the platform's estimates. These are benchmarks, not proof of plant-scale validation.")
    cases = pd.read_csv(Path(__file__).parent / "data" / "case_studies.csv")
    st.warning("A literature comparison is not automatically an independent validation: the predictor is trained on a bundled literature dataset. The cited Mohan et al. paper title and DOI were not found as exact strings in the bundled training CSV, but record-level overlap must still be checked before treating this as a formal holdout test.")
    case_labels = {r.case_id: f"{r.case_id} · {r.feedstock} · {r.study}" for r in cases.itertuples()}
    chosen_id = st.selectbox("Select a published case", list(case_labels), format_func=lambda k: case_labels[k])
    c = cases[cases.case_id == chosen_id].iloc[0]
    section("Reported experimental / pilot conditions")
    st.markdown(f"**{c['study']}**  ")
    st.markdown(f"Feedstock: **{c['feedstock']}** · Route: **{c['process']}** · Evidence type: **{c['evidence_type']}**")
    st.caption(str(c['reported_basis']))
    metrics = []
    for label, col, unit in [("Temperature", "temperature_C", "°C"), ("Residence time", "residence_min", "min"), ("Heating rate", "heating_rate_C_min", "°C/min"), ("Char yield", "char_yield_wt_dry", "wt% dry feed"), ("Char carbon", "char_carbon_wt", "wt%"), ("H/C", "H_C_molar", "molar"), ("Heat demand", "energy_demand_MJ_kg_dry", "MJ/kg"), ("Energy efficiency", "energy_efficiency_pct", "%")]:
        v = c[col]
        if pd.notna(v) and str(v).strip(): metrics.append((label, f"{float(v):g} {unit}"))
    cols = st.columns(min(4, max(1, len(metrics))))
    for i, (lab, val) in enumerate(metrics): cols[i % len(cols)].metric(lab, val)
    st.markdown(f"**Primary source:** [{c['doi']}]({c['url']})")
    st.caption(str(c['notes']))

    if c['case_id'] in ("CS-01", "CS-02"):
        section("Run the platform at the published conditions")
        pred = get_predictor().predict(str(c['feedstock_class']), float(c['temperature_C']), float(c['residence_min']), float(c['heating_rate_C_min']))
        a, b, d = st.columns(3)
        observed = float(c['char_yield_wt_dry']); estimated = float(pred['Yield']['mean'])
        a.metric("Reported char yield", f"{observed:.1f} wt%")
        b.metric("Platform estimate", f"{estimated:.1f} wt%", help="Current literature-trained predictor evaluated at the study's nominal conditions.")
        delta = estimated - observed
        d.metric("Estimate − reported", f"{delta:+.1f} percentage points")
        st.markdown("**Other property comparison**")
        prop_rows = []
        for key, label, unit in [("C", "Char carbon", "wt%"), ("H_C", "Molar H/C", "")]:
            obs = c['char_carbon_wt'] if key == 'C' else c['H_C_molar']
            if pd.notna(obs): prop_rows.append({"Metric":label,"Study result":float(obs),"Platform estimate":float(pred[key]['mean']),"Difference":float(pred[key]['mean'])-float(obs),"Unit":unit})
        st.dataframe(pd.DataFrame(prop_rows), hide_index=True, width="stretch")
        st.caption("Interpretation: this is a same-condition literature comparison, not a blind holdout test. Rice husk is mapped to the herbaceous class because the current model has no rice-husk-specific class; this adds feedstock-class mismatch. Model tree spread is not a calibrated confidence interval.")
        if pred.get('extrapolating'): st.warning("The selected temperature is outside the predictor's observed temperature range for this feedstock class.")
    else:
        st.info("This case is retained as a context benchmark, but the publication reports a range/approximate value rather than a directly matched point. The app deliberately does not compute a misleading pointwise prediction error.")

    section("Cross-case benchmark register")
    display = cases[["case_id","feedstock","process","temperature_C","residence_min","heating_rate_C_min","char_yield_wt_dry","char_carbon_wt","H_C_molar","energy_demand_MJ_kg_dry","energy_efficiency_pct","evidence_type","doi"]].copy()
    st.dataframe(display, width="stretch", hide_index=True)
    st.markdown("**Pilot-plant energy benchmark:** the 2026 pilot-plant study reports a Case A bottom-outlet average process heat demand of 1.37 ± 0.20 MJ/kg and energy efficiency of 80.35 ± 2.86%. This is a separate system-boundary check; reconcile feed moisture, heating value basis, reactor boundary and recovered heat before treating it as directly comparable to this platform's purchased-heat result. [Source: Energy, exergy and mass balances of a biomass pyrolysis pilot plant](https://doi.org/10.1016/j.enconman.2026.121154).")
    section("Numerical provenance register")
    prov = pd.read_csv(Path(__file__).parent / "references" / "numerical_assumptions.csv")
    prov["Source link"] = prov["url"].fillna("")
    st.dataframe(prov.drop(columns=["url"]), width="stretch", hide_index=True, column_config={"Source link":st.column_config.LinkColumn("Source link")})
    st.caption("Calculated outputs inherit the sources and assumptions of their input terms and equations. The Technical and Economics calculation logs identify the equation/model ID per output. Empty source links mean the value is intentionally marked as an assumption or exact identity, not that a citation has been fabricated.")
    nav_footer("Case Studies")

# ================================================================== BIOCHAR
elif page == "Biochar":
    stepper("Biochar")
    header("Biochar: what does this scenario produce?", "Predicted yield and quality from the literature-trained model, and the carbon structure those properties imply.")
    scenario_strip()
    pred = get_predictor(); d = S.design
    feed, process, htt, dur, hr = d["feed"], d["process"], d["htt"], d["dur"], d["hr"]; cls = FEEDSTOCKS[feed]["cls"]
    p0, e0, r = design_inputs(pred, feed, htt, dur, hr, replace(S.process, wet_feed_t_y=10000.0), S.economics, d["liquid_share"], process=process)
    t0 = calculate_technical(p0); ec0 = calculate_economics(t0, p0, e0); sf = p0.stable_carbon_fraction
    if process != "slow_pyrolysis": st.warning(f"{PROCESSES[process]['label']}: {PROCESSES[process]['status']}")
    elif r["extrapolating"]: st.warning("Outside the observed temperature range for this feedstock class: treat as extrapolation.")
    sd = lambda k: f"\u00b1{r[k]['std']:.2g} (tree spread)" if r[k]["std"] else PROCESSES[process]["yield_source"]
    hc_used = r["H_C_used"]; ash_val = r["Ash"]["mean"]
    if ash_val != ash_val: ash_val = pred.class_means["Ash"].get(cls, 8.0)
    kpis([("Char / solid yield", f"{r['Yield']['mean']:.1f}", sd("Yield"), "wt% dry"), ("Carbon in char", f"{r['C']['mean']:.1f}", sd("C"), "wt%"), ("Ash", f"{ash_val:.1f}", "predicted" if r["Ash"]["mean"] == r["Ash"]["mean"] else "class mean", "wt%"),
          ("H/C molar", f"{hc_used:.2f}", sd("H_C")), ("Stable-C fraction", f"{sf:.2f}", "placeholder H/C map")])
    chips([(f"H/C {hc_used:.2f}: {'high' if hc_used < 0.4 else 'medium' if hc_used < 0.7 else 'low'} stability class" + ("" if hc_used < 0.7 else " (above the 0.7 limit)"), "ok" if hc_used < 0.4 else "warn" if hc_used < 0.7 else "bad")])
    tabs = st.tabs(["3D structure", "Property trends", "Model validation", "Scale-up preview", "Audit"])
    with tabs[0]:
        desc, nano, micro = structure_cached(int(round(htt)), round(float(hc_used), 2), round(float(ash_val), 1), cls)
        ns = nano["stats"]
        caps = {"lattice": f"Box {ns['box_nm']:.1f} nm \u00b7 {ns['n_atoms']:,} atoms \u00b7 {ns['n_crystallites']} aromatic stacks", "particle": f"Stylised particle section \u00b7 {micro['stats']['n_channels']} channels \u00b7 {micro['stats']['n_ash_grains']} ash grains"}
        c1, c2 = st.columns([5, 3], gap="large")
        with c1:
            viz3d.viewer(nano, micro, caps, height=560, mode="lattice", key="viewer_main")
            st.markdown('<div class="viewer-note">Drag to rotate, scroll to zoom. Switch between the <b>atomic lattice</b> (nanometres) and the <b>particle and pore network</b> (stylised, not to scale) with the buttons in the viewer.</div>', unsafe_allow_html=True)
        with c2:
            section("What the model draws, and why")
            lum = "Honeycomb channels (lumen/pitch " + f"{desc['lumen_ratio']:.2f})" if desc["n_channels_axis"] else "Foam-like pores, no channel network"
            rows = [("Aromatic clusters", f"{desc['n_rings']} fused rings, about {desc['La_nm']:.1f} nm", "Closest compact PAH to the predicted H/C (H/C = 1/k series)"),
                    ("Stacking", f"{desc['n_layers']} layer(s), d002 about {desc['d002_nm']:.2f} nm", "Typical trend with temperature (placeholder)"),
                    ("Aromatic carbon", f"{desc['arom_frac']:.0%}; rest as aliphatic chains", "Linear trend in H/C (placeholder)"),
                    ("Oxygen groups", f"O/C about {desc['oc']:.2f}", "Dataset median at this H/C (not predicted)"),
                    ("Mineral (ash) grains", f"{desc['ash_pct']:.1f} wt%", "Predicted ash (ML-001) or class mean"),
                    ("Pore network", lum, "Stylised, depends on feedstock class"),
                    ("Visual porosity", f"{desc['porosity_visual']:.0%}", "Stylised trend, not a BET measurement")]
            st.dataframe(pd.DataFrame(rows, columns=["Feature", "Value", "Basis"]), width="stretch", hide_index=True, height=300)
            st.caption("This is the layer-1 link: predicted properties in, structural descriptors out. The descriptor table is what a layer-2 model could consume.")
            with st.expander("How is this built, and what is it not?"):
                st.markdown("- Cluster size comes from H/C: a compact polycyclic aromatic with k rings along its edge has H/C = 1/k (benzene 1.0, coronene 0.5, circumcoronene 0.33).\n- Layers are stacked at the d002 spacing with random rotation (turbostratic), and bent more at low temperature.\n- Edge sites carry H, O groups or aliphatic chains in proportion to H/C, O/C and the aromatic share.\n- The particle view meshes a channel and pore field built from feedstock class, temperature and ash.\n- **Not** a molecular dynamics, DFT or tomography result. Use it to communicate trends, not to read off surface area or pore volume.")
        section("How temperature reshapes the structure")
        if st.toggle("Compare 400, 600 and 800 \u00b0C side by side", key="cmp_on"):
            if process != "slow_pyrolysis": st.caption("Comparison uses the slow-pyrolysis predictor; select slow pyrolysis for a like-for-like view.")
            vm = st.radio("View", ["Atomic lattice", "Particle & pores"], horizontal=True, key="cmp_view")
            cols = st.columns(3)
            for col, T in zip(cols, (400, 600, 800)):
                rr = pred.predict(cls, float(T), dur, hr); aa = rr["Ash"]["mean"]
                dd, nn, mm = structure_cached(T, round(float(max(rr["H_C"]["mean"], 0.05)), 2), round(float(aa), 1), cls)
                with col:
                    st.markdown(f"**{T} \u00b0C** \u00b7 H/C {rr['H_C']['mean']:.2f} \u00b7 {dd['n_layers']} layer(s)")
                    viz3d.viewer(nn, mm, {"lattice": f"{nn['stats']['n_atoms']:,} atoms", "particle": f"{mm['stats']['n_channels']} channels"}, height=320, mode="lattice" if vm.startswith("Atomic") else "particle", compact=True, key=f"cmp_{T}")
        else:
            st.caption("Turn this on to see low, medium and high temperature structures next to each other.")
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
    with tabs[3]:
        st.caption("A quick look at what this chemistry means at plant scale. Detailed balances are in step 3, the business case in step 4.")
        section("Rough result per 10,000 t/y wet feed")
        kpis([("Biochar / solid", fmt(t0["char_t_y"]), "", "t/y"), ("Removal proxy", fmt(t0["net_removal_proxy_tco2e_y"]), "screening", "tCO\u2082e/y"),
              ("Carbon retained", f"{t0['carbon_retained_fraction']:.0%}", "feasible" if t0["carbon_balance_ok"] else "INFEASIBLE: more C in char than in feed"), ("Economic surplus", fmt(ec0["annual_economic_surplus_usd_y"]), "placeholder prices", "USD/y")])
    with tabs[4]:
        sub = st.tabs(["Mathematical model", "Calculation log"])
        with sub[0]: render_math("estimates")
        with sub[1]: log_view(log_estimates(feed, cls, htt, dur, hr, r, sf, t0, ec0, process), "estimates_log")
    snap = {"process": PROCESSES[process]["label"], "process_status": PROCESSES[process]["status"], "feedstock": feed, "HTT_C": htt, "residence_min": dur, "prediction": r, "stable_fraction": sf,
            "cv": {k_: {"r2": v["r2"], "baseline_r2": v["baseline_r2"]} for k_, v in pred.cv.items()},
            "per_10kt_wet": {"char_t_y": t0["char_t_y"], "removal_proxy": t0["net_removal_proxy_tco2e_y"], "carbon_retained": t0["carbon_retained_fraction"]},
            "structure_model": {k_: desc[k_] for k_ in ("n_rings", "n_layers", "d002_nm", "arom_frac", "oc", "porosity_visual")},
            "assumption_status": "Stable fraction map, feed carbon, HTC lines are placeholders/typical values. The 3D structure is a stylised visual, not a simulation."}
    ai_panel("Rough estimates", _r(snap), fallback=[f"Predicted char yield {r['Yield']['mean']:.1f}% and H/C {r['H_C']['mean']:.2f}."])
    nav_footer("Biochar")

# ================================================================== PROCESS
elif page == "Process":
    stepper("Process")
    header("Process engineering", "Where the material and heat go, and whether the particles convert within the residence time.")
    scenario_strip()
    if not PRED():
        with st.container(border=True):
            st.markdown("**Manual product yields.** Switch back to predicted yields under Advanced in the sidebar.")
            S.design["dur"] = float(st.number_input("Residence time (min)", 0.02, 600.0, float(S.design["dur"]), 1.0, key="t_dur_m"))
            S.process = process_inputs("man")
    with st.expander("Plant and particle inputs (advanced)", expanded=False):
        if PRED(): S.process = plant_inputs(S.process)
        st.markdown("**Particle model**"); particle_inputs()
    R = pipeline(); t, p, sim, pp, pr = R["t"], R["p"], R["sim"], R["pp"], R["pr"]
    chips(status_checks(R))
    if pr and S.design["process"] == "slow_pyrolysis": st.caption(f"Predicted: yield {pr['Yield']['mean']:.1f}% \u00b1{pr['Yield']['std']:.1f}, carbon {pr['C']['mean']:.0f}%, H/C {pr['H_C']['mean']:.2f}.")
    st.caption("Work through the tabs left to right: material balance, heat demand, particle behaviour. The audit tab holds the equations, assumptions and verification.")
    tabs = st.tabs(["Flow diagram", "Material balance", "Heat & energy", "Particle behaviour", "Audit & verification"])
    with tabs[0]:
        st.caption("Streams animate and resize with your inputs. Mass is in t/y; the red loop is recovered co-product heat. Below: the same balances as Sankey diagrams.")
        show_html(pfd_html(t, p, R["proc"]["label"]), 520)
        ef = energy_flows(t, p)
        kpis([("Heat self-sufficiency", f"{ef['self_sufficiency']:.0%}", "recovered / required"), ("Heat required", fmt(ef["requirement"]), "fuel basis", "GJ/y"), ("Recovered from co-products", fmt(ef["recovered"]), "syngas + diverted oil", "GJ/y"),
              ("External heat needed" if ef["external"] > 0 else "Surplus heat", fmt(ef["external"] if ef["external"] > 0 else ef["surplus"]), "", "GJ/y")])
        c1, c2 = st.columns(2)
        with c1, st.container(border=True): st.markdown("**Mass balance (t/y)**"); st.plotly_chart(sankey(t), width="stretch", key="sk_mass_pfd")
        with c2, st.container(border=True): st.markdown("**Process-heat balance (GJ/y)**"); st.plotly_chart(energy_sankey(ef), width="stretch")
        st.caption("Heat required is on a fuel basis (duty / losses / burner efficiency). Recovered heat applies the co-product recovery fraction to gas and diverted-oil energy. These are the engine's own definitions, so the comparison is conservative: the burner efficiency and recovery fraction are both applied.")
    with tabs[1]:
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
    with tabs[2]:
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
    with tabs[3]:
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
    with tabs[4]: sub = st.tabs(["Calculation log", "Assumptions & models", "Equations", "Verification"])
    with sub[0]: log_view(log_technical(R), "technical_log")
    with sub[1]:
        st.dataframe(assumptions_table(R), width="stretch", hide_index=True)
        section("Models used"); source_note(["MASS-001", "ENERGY-001", "PYRO-001", "ML-001", "PERM-001", "PART-001", "KIN-001"])
    with sub[2]: render_math("technical")
    with sub[3]:
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
    nav_footer("Process")

# ================================================================== ECONOMICS
elif page == "Economics":
    stepper("Economics")
    header("Economics", "Where the money goes, where revenue comes from, and which assumptions control project viability.")
    scenario_strip()
    with st.expander("Edit financial assumptions · placeholder values until verified", expanded=False): S.economics = econ_inputs("econ")
    R = pipeline(); t, ec, p, e = R["t"], R["ec"], R["p"], R["e"]
    st.markdown(f"**Technical basis:** {R['proc']['label']} \u00b7 {S.design['feed'] if PRED() else 'manual inputs'} \u00b7 {p.reactor_temp_C:.0f} \u00b0C \u00b7 {fmt(t['char_t_y'])} t/y solid \u00b7 removal proxy {fmt(t['net_removal_proxy_tco2e_y'])} tCO\u2082e/y")
    be = breakeven_carbon_price(ec, t)
    kpis([("Revenue", fmt(ec["total_revenue_usd_y"]), "", "USD/y"), ("Operating cost", fmt(ec["operating_cost_usd_y"]), "", "USD/y"), ("Economic surplus", fmt(ec["annual_economic_surplus_usd_y"]), "after capital recovery", "USD/y"),
          ("NPV", fmt(ec["npv_usd"]), "", "USD"), ("IRR", f"{ec['irr']:.1%}" if ec["irr"] is not None else "n/a", f"payback {fmt(ec['simple_payback_y'])} y" if ec["simple_payback_y"] else ""), ("Breakeven carbon price", fmt(be) if be is not None else "n/a", "surplus = 0", "USD/t")])
    st.info("Read the tabs left to right: cash flow, cost and revenue drivers, unit economics, sensitivity, audit. Edit the assumptions above to test a scenario; replace placeholder values with quotations before treating results as investment estimates.")
    tabs = st.tabs(["Carbon credits", "Cash flow", "Costs & revenue", "Unit economics", "Sensitivity", "Audit"])
    with tabs[0]:
        st.caption("Tonnes of CO\u2082 stored per year and what they earn on the voluntary removal market. Deductions and fees are scenario assumptions, not registry rules.")
        a, b, c, d_ = st.columns(4)
        price = a.number_input("Credit price (USD/tCO\u2082)", 0.0, 1000.0, 135.0, 5.0, key="cc_price", help="Reference: about USD 136 CDR.fyi weighted average and EUR 135 Puro.earth biochar index (2026). Sellers report breakevens of roughly USD 143-187.")
        life = d_.slider("Lifecycle emissions (% of gross)", 0, 50, 15, key="cc_life") / 100
        buf = b.slider("Buffer / permanence deduction (%)", 0, 30, 10, key="cc_buf") / 100
        fee = c.number_input("Registry + MRV cost (USD/credit)", 0.0, 100.0, 8.0, 1.0, key="cc_fee")
        cc = credit_calc(t["gross_stored_co2_t_y"], price, life, buf, fee)
        kpis([("CO\u2082 removed (credits)", fmt(cc["credits_t_y"]), "after deductions", "t/y"), ("Credit revenue", fmt(cc["revenue_usd_y"]), f"at {price:,.0f} USD/t", "USD/y"), ("Net of registry + MRV", fmt(cc["net_revenue_usd_y"]), "", "USD/y"),
              ("Per tonne biochar", fmt(cc["revenue_usd_y"] / max(t["char_t_y"], 1e-9)), "credit revenue", "USD/t"), ("Equivalent to", fmt(cc["cars_equivalent"]), "cars off the road (4.6 t/y each)", "cars")])
        c1, c2 = st.columns(2)
        wf = go.Figure(go.Waterfall(x=["Gross stored CO\u2082", "Lifecycle emissions", "Buffer pool", "Credits issued"], measure=["absolute", "relative", "relative", "total"], y=[cc["gross_t_y"], -cc["lifecycle_t_y"], -cc["buffer_t_y"], 0],
                                    increasing=dict(marker=dict(color=GREEN)), decreasing=dict(marker=dict(color=RED)), totals=dict(marker=dict(color=BLUE))))
        wf.update_layout(title="From stored carbon to credits (t CO\u2082/y)")
        with c1, st.container(border=True): st.plotly_chart(style_fig(wf, 340, legend=False), width="stretch")
        base = ec["annual_economic_surplus_usd_y"] - ec["carbon_revenue_usd_y"]; prices = np.linspace(0, 400, 81)
        sur = base + cc["credits_t_y"] * (prices - fee); be_p = (max(0.0, -base) / cc["credits_t_y"] + fee) if cc["credits_t_y"] > 0 else None
        fg = go.Figure(go.Scatter(x=prices, y=sur, line=dict(color=GREEN, width=3), name="Annual surplus")); fg.add_hline(y=0, line_color=GREY)
        if be_p is not None and be_p <= 400: fg.add_vline(x=be_p, line_dash="dot", annotation_text=f"break-even {be_p:,.0f}")
        fg.add_vline(x=price, line_color=AMBER, annotation_text="your price"); fg.update_layout(xaxis_title="Credit price (USD/tCO\u2082)", yaxis_title="USD/y", title="Annual economic surplus vs credit price")
        with c2, st.container(border=True): st.plotly_chart(style_fig(fg, 340, legend=False), width="stretch")
        eff = effective_price_on_gross(price, life, buf, fee)
        st.button(f"Use in the economic model ({eff:,.1f} USD per tonne of gross stored CO\u2082)", key="cc_apply", on_click=apply_cc_price, args=(eff,), help="The model multiplies this by its gross removal proxy, so deductions and fees are folded into one effective price.")
        st.caption(f"Break-even credit price for this scenario: {be_p:,.0f} USD/tCO\u2082." if be_p is not None else "No credits are produced in this scenario.")
        st.warning("Credits require a registry methodology, third-party verification and proof of persistence. The stable-carbon fraction here comes from a placeholder H/C map, so treat these numbers as an upper-bound screen, not an issuance forecast.")
    with tabs[1]:
        st.caption("This is the project-level cash-flow picture: initial capital outlay followed by the modelled annual operating cash flow. It is undiscounted in this chart; NPV is shown above.")
        yrs = np.arange(0, int(e.project_life_y) + 1); cum = -e.capex_usd + ec["ebitda_like_usd_y"] * yrs
        fig = go.Figure(go.Scatter(x=yrs, y=cum, fill="tozeroy", line=dict(color=GREEN, width=3), fillcolor="rgba(31,122,90,.15)")); fig.add_hline(y=0, line_color=GREY)
        fig.update_layout(xaxis_title="Year", yaxis_title="USD", title="Cumulative cash flow (undiscounted)")
        with st.container(border=True): st.plotly_chart(style_fig(fig, 340, legend=False), width="stretch")
        st.caption("Constant annual EBITDA-like cash flow; no taxes, debt, working capital, escalation or replacement CAPEX.")
    with tabs[2]:
        st.caption("Positive bars are revenue; negative bars are costs. This view identifies the largest contributors to annual operating performance.")
        rows = [["Feedstock + logistics", -ec["feedstock_logistics_cost_usd_y"]], ["Electricity", -ec["electricity_cost_usd_y"]], ["Purchased heat", -ec["purchased_heat_cost_usd_y"]], ["Labour", -ec["labour_usd_y"]], ["Maintenance", -ec["maintenance_usd_y"]],
                ["Other OPEX", -ec["other_opex_usd_y"]], ["Biochar sales", ec["char_revenue_usd_y"]], ["Liquid sales", ec["liquid_revenue_usd_y"]], ["Electricity export", ec["electricity_revenue_usd_y"]], ["Carbon credits", ec["carbon_revenue_usd_y"]]]
        df = pd.DataFrame(rows, columns=["Item", "USD/y"]); df["Type"] = np.where(df["USD/y"] >= 0, "Revenue", "Cost")
        with st.container(border=True): st.plotly_chart(style_fig(px.bar(df, x="Item", y="USD/y", color="Type", color_discrete_map={"Revenue": GREEN, "Cost": RED}), 340), width="stretch")
        if e.carbon_credit_usd_tco2e > 0: st.warning("Carbon revenue assumes the removal proxy is verified and creditable. It is a screening proxy today.")
    with tabs[3]:
        st.caption("Unit economics normalise the project totals by tonnes of product or tonnes of removal proxy. These are scenario-derived costs, not market quotations.")
        char = max(t["char_t_y"], 1e-9); rem = t["net_removal_proxy_tco2e_y"]; tc = ec["operating_cost_usd_y"] + ec["annualised_capex_usd_y"]; nan = float("nan")
        u = pd.DataFrame([["Full cost per tonne solid product", tc / char, "USD/t"], ["Cost per tCO2e removed (full cost)", tc / rem if rem > 0 else nan, "USD/tCO2e"],
                          ["Cost per tCO2e net of non-carbon revenue", max(0, tc - (ec["total_revenue_usd_y"] - ec["carbon_revenue_usd_y"])) / rem if rem > 0 else nan, "USD/tCO2e"], ["Breakeven carbon price", be if be is not None else nan, "USD/tCO2e"],
                          ["Assumed carbon price", e.carbon_credit_usd_tco2e, "USD/tCO2e"]], columns=["Metric", "Value", "Unit"])
        st.dataframe(u.round(2), width="stretch", hide_index=True); st.caption("Compare with the indicative biochar range on the dashboard (IPCC AR6, roughly 10-345 USD/tCO2; still to be re-verified).")
    with tabs[4]:
        st.caption("Change one input at a time and see how much annual economic surplus moves. This is a local sensitivity screen; it does not capture interactions between variables.")
        swing = st.slider("Swing on each input (\u00b1%)", 5, 50, 20, 5) / 100; base, rows = tornado(p, e, swing); fig = go.Figure()
        fig.add_trace(go.Bar(y=[r["input"] for r in rows], x=[r["low"] for r in rows], orientation="h", name=f"-{swing:.0%}", marker_color=RED)); fig.add_trace(go.Bar(y=[r["input"] for r in rows], x=[r["high"] for r in rows], orientation="h", name=f"+{swing:.0%}", marker_color=GREEN))
        fig.update_layout(barmode="overlay", yaxis=dict(autorange="reversed"), xaxis_title="Change in annual economic surplus (USD/y)")
        with st.container(border=True): st.plotly_chart(style_fig(fig, 420), width="stretch")
        st.caption(f"Base surplus {base:,.0f} USD/y. One-at-a-time swings; interactions not shown.")
    with tabs[5]: sub = st.tabs(["Calculation log", "Model equations"])
    with sub[0]:
        st.caption("Every row shows the equation, numerical inputs, calculated result, units and model/source identifier. Download the table to audit or reuse the scenario calculations.")
        log_view(log_economic(R), "economic_log")
        source_note(["ECON-001"])
    with sub[1]:
        st.caption("Definitions of the financial equations used by the screening model.")
        render_math("economic")
    ai_panel("Economic", snapshot(R, ["technical", "economics"]), fallback=[f"Economic surplus {fmt(ec['annual_economic_surplus_usd_y'])} USD/y; breakeven carbon price {fmt(be) if be is not None else 'n/a'}."])
    nav_footer("Economics")

# ================================================================== OPTIMIZE
elif page == "Optimize":
    stepper("Optimize")
    header("Design optimiser", "Compare feasible slow-pyrolysis designs using the same feedstock, plant basis and technical/economic models.")
    pred = get_predictor()
    st.info("Scope: this optimiser currently searches slow pyrolysis only. Fast pyrolysis, torrefaction, gasification and HTC use screening-level or cross-process assumptions and are not comparable enough for a defensible combined optimum.")
    with st.expander("Design problem, objective and constraints", expanded=not bool(S.get("opt"))):
        st.subheader("A \u00b7 Design problem")
        st.caption("Fixed plant basis is inherited from the Technical and Economic pages. Choose which feedstocks and operating conditions the optimiser may vary.")
        feeds = st.multiselect("Feedstocks to compare", list(FEEDSTOCKS), default=[S.design.get("feed", "Rice straw")] if S.design.get("feed", "Rice straw") in FEEDSTOCKS else ["Rice straw"])
        a, b = st.columns(2)
        temp_range = a.slider("Reactor temperature search range (°C)", 300, 800, (400, 600), 10)
        duration_choices = b.multiselect("Residence times to test (min)", [15, 30, 60, 120, 240], default=[30, 60, 120])
        a, b = st.columns(2)
        cc = a.number_input("Carbon-credit scenario price (USD/tCO₂e)", min_value=0.0, max_value=1000.0, value=float(S.economics.carbon_credit_usd_tco2e), step=5.0, help="Scenario assumption only; zero excludes carbon revenue.")
        ls = b.slider("Liquid fraction of non-char products", 0.0, 1.0, float(S.design["liquid_share"]), 0.05)
        st.subheader("B \u00b7 Objective and feasibility rules")
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
                b1, b2, _ = st.columns([2, 2, 3])
                b1.button("Apply this design to the scenario", type="primary", key="opt_apply", width="stretch", on_click=apply_best, args=(best, o["ls"], o["cc"]))
                b2.button("Review in Process \u2192", key="opt_go", width="stretch", on_click=goto, args=("Process",))
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
    nav_footer("Optimize")
