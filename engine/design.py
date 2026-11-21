"""Bridge: predicted char properties -> mass/energy/economics -> optimisation."""
from __future__ import annotations
from dataclasses import replace
import numpy as np
from .models import ProcessInputs, EconomicInputs, calculate_technical, calculate_economics, pareto_front
from .predict import BiocharPredictor, stable_fraction_from_hc
from .processes import PROCESSES, htc_properties

# Moisture / class mapping are screening presets. Costs are PLACEHOLDERS, not sourced quotations.
FEEDSTOCKS = {
    "Rice straw":            {"cls": "herbaceous", "moisture": 0.15, "cost": 5.0,  "logistics": 10.0, "c": 0.38},
    "Sugarcane bagasse":     {"cls": "herbaceous", "moisture": 0.50, "cost": 3.0,  "logistics": 6.0, "c": 0.47},
    "Corn stover / cobs":    {"cls": "herbaceous", "moisture": 0.15, "cost": 5.0,  "logistics": 10.0, "c": 0.45},
    "Cotton stalks":         {"cls": "woody",      "moisture": 0.15, "cost": 4.0,  "logistics": 10.0, "c": 0.47},
    "Date palm residues":    {"cls": "woody",      "moisture": 0.15, "cost": 4.0,  "logistics": 8.0, "c": 0.45},
    "Olive stones / pits":   {"cls": "shells and kernels", "moisture": 0.10, "cost": 20.0, "logistics": 8.0, "c": 0.5},
    "Poultry / cattle manure": {"cls": "manure",   "moisture": 0.30, "cost": 2.0,  "logistics": 8.0, "c": 0.35},
    "Dewatered sewage sludge": {"cls": "sewage sludge", "moisture": 0.75, "cost": 0.0, "logistics": 6.0, "c": 0.33},
}

def design_inputs(pred: BiocharPredictor, feed: str, htt: float, duration: float, heating_rate: float,
                  base_p: ProcessInputs, base_e: EconomicInputs, liquid_share: float = 0.55, r: dict | None = None,
                  process: str = "slow_pyrolysis"):
    """Return (ProcessInputs, EconomicInputs, prediction) for one candidate design of a given process type."""
    f, proc = FEEDSTOCKS[feed], PROCESSES[process]
    if process == "slow_pyrolysis":
        r = r or pred.predict(f["cls"], htt, duration, heating_rate)
        char = float(np.clip(r["Yield"]["mean"] / 100.0, 0.05, 0.95)); rest = 1.0 - char
        liq, gas = rest * liquid_share, rest * (1 - liquid_share)
    elif process == "htc":
        h = htc_properties(htt); char, gas = h["char"], h["gas"]; liq = max(0.0, 1.0 - char - gas)
        r = {"Yield": {"mean": char * 100, "std": 0.0}, "C": {"mean": h["C"] * 100, "std": 0.0}, "H_C": {"mean": h["H_C"], "std": 0.0},
             "Ash": {"mean": float("nan"), "std": 0.0}, "extrapolating": False}
    else:
        r = r or pred.predict(f["cls"], htt, 15.0, 30.0)
        a = proc["anchors"]; char, gas, liq = a["char"], a["gas"], a["liquid"]
        r = {**r, "Yield": {"mean": char * 100, "std": 0.0}, "extrapolating": True}   # char quality is a cross-mode extrapolation
    cfrac = float(np.clip(r["C"]["mean"] / 100.0, 0.2, 0.95)); hc = float(max(r["H_C"]["mean"], 0.05))
    p = replace(base_p, process_type=process, moisture_wet_basis=f["moisture"], reactor_temp_C=float(htt),
                char_yield_dry=char, liquid_yield_dry=liq, gas_yield_dry=gas, other_yield_dry=0.0,
                char_carbon_fraction=cfrac, stable_carbon_fraction=stable_fraction_from_hc(hc), feed_carbon_fraction_dry=f["c"])
    e = replace(base_e, feedstock_cost_usd_t_wet=f["cost"], logistics_cost_usd_t_wet=f["logistics"])
    if proc.get("liquid_price_usd_t") is not None: e = replace(e, liquid_price_usd_t=proc["liquid_price_usd_t"])
    return p, e, {**r, "H_C_used": hc}

def evaluate_design(pred, feed, htt, duration, heating_rate, base_p, base_e, liquid_share=0.55, r=None, process="slow_pyrolysis"):
    p, e, r = design_inputs(pred, feed, htt, duration, heating_rate, base_p, base_e, liquid_share, r, process)
    t = calculate_technical(p); ec = calculate_economics(t, p, e)
    return {"process": process, "feedstock": feed, "HTT": float(htt), "duration_min": float(duration), "heating_rate": float(heating_rate),
            "pred_yield_pct": r["Yield"]["mean"], "pred_H_C": r["H_C_used"], "pred_C_pct": r["C"]["mean"],
            "stable_fraction": p.stable_carbon_fraction, "extrapolating": r["extrapolating"], **t, **ec}

def search_designs(pred, base_p, base_e, feeds=None, htt_range=(300, 800), step=20,
                   durations=(15, 30, 60, 120, 240), rates=(5, 10, 20), max_hc=None, liquid_share=0.55,
                   particle=None, safety=1.0, require_carbon_ok=True, processes=("slow_pyrolysis",)):
    """Grid search over process x feedstock x HTT (x residence time x heating rate for slow pyrolysis).
    `particle` maps process name -> ParticleParams (or a single ParticleParams used for all).
    Technical constraints: (a) particle reaches target conversion within the residence time (processes with a
    full particle model), (b) carbon balance closes, (c) optional H/C limit. Returns (rows, Pareto front, stats)."""
    from .particle import conversion_time_s
    feeds = feeds or list(FEEDSTOCKS)
    rows, cache, t95 = [], {}, {}
    stats = {"evaluated": 0, "rejected_hc": 0, "rejected_conversion": 0, "rejected_carbon": 0}
    for process in processes:
        proc = PROCESSES[process]
        lo, hi = (htt_range if process == "slow_pyrolysis" else proc["T"]); stp = step if process == "slow_pyrolysis" else proc["T_step"]
        htts = list(range(int(lo), int(hi) + 1, int(stp)))
        durs = list(durations) if process == "slow_pyrolysis" else [proc["dur_default"]]
        hrs = list(rates) if process == "slow_pyrolysis" else [30]
        pp = particle.get(process) if isinstance(particle, dict) else particle
        for feed in feeds:
            cls = FEEDSTOCKS[feed]["cls"]
            if process == "htc": grid = [(h, durs[0], hrs[0], None) for h in htts]
            else:
                key = (cls, process)
                if key not in cache: cache[key] = pred.predict_grid(cls, htts, [15.0] if process != "slow_pyrolysis" else durs, hrs)
                grid = [(g.HTT, (g.Pyrolysis_duration if process == "slow_pyrolysis" else durs[0]), g.Heating_rate,
                         {"Yield": {"mean": g.Yield}, "C": {"mean": g.C}, "Ash": {"mean": g.Ash}, "H_C": {"mean": g.H_C}, "extrapolating": bool(g.extrapolating)})
                        for g in cache[key].itertuples(index=False)]
            for htt, dur, hr, r in grid:
                stats["evaluated"] += 1
                if r is not None and max_hc is not None and r["H_C"]["mean"] > max_hc: stats["rejected_hc"] += 1; continue
                tt = None
                if pp is not None and proc["particle"] == "full":
                    # Use one documented nominal char fraction for the screening particle check.
                    # This keeps the expensive transient simulation independent of yield-grid points.
                    pp_i = replace(pp, char_mass_fraction=0.30)
                    k_ = (process, htt, pp_i.diameter_mm, pp_i.h_W_m2K)
                    if k_ not in t95: t95[k_] = conversion_time_s(htt, pp_i, dt_s=5.0)
                    tt = t95[k_]
                    if tt is None or dur * 60 < safety * tt: stats["rejected_conversion"] += 1; continue
                row = evaluate_design(pred, feed, htt, dur, hr, base_p, base_e, liquid_share, r, process)
                if max_hc is not None and row["pred_H_C"] > max_hc: stats["rejected_hc"] += 1; continue
                row["t95_min"] = (tt / 60.0) if tt else None
                row["particle_kinetics_extrapolated"] = bool(pp is not None and proc["particle"] == "full" and not (300.0 <= htt <= 435.0))
                if require_carbon_ok and not row["carbon_balance_ok"]: stats["rejected_carbon"] += 1; continue
                rows.append(row)
    return rows, (pareto_front(rows) if rows else []), stats

def best_by_surplus(rows):
    return max(rows, key=lambda r: r["annual_economic_surplus_usd_y"]) if rows else None

def tornado(base_p: ProcessInputs, base_e: EconomicInputs, swing=0.2):
    """One-at-a-time +/- swing on key inputs -> change in annual economic surplus."""
    def surplus(p, e): 
        t = calculate_technical(p); return calculate_economics(t, p, e)["annual_economic_surplus_usd_y"]
    base = surplus(base_p, base_e)
    items = [("Biochar price", "e", "char_price_usd_t"), ("Carbon credit price", "e", "carbon_credit_usd_tco2e"),
             ("CAPEX", "e", "capex_usd"), ("Feedstock cost", "e", "feedstock_cost_usd_t_wet"),
             ("Logistics cost", "e", "logistics_cost_usd_t_wet"), ("Labour", "e", "labour_usd_y"),
             ("Plant throughput", "p", "wet_feed_t_y"), ("Char yield", "p", "char_yield_dry"),
             ("Feed moisture", "p", "moisture_wet_basis")]
    out = []
    for label, kind, attr in items:
        res = []
        for s in (1 - swing, 1 + swing):
            p, e = base_p, base_e
            if kind == "e": e = replace(e, **{attr: getattr(e, attr) * s})
            else:
                p = replace(p, **{attr: getattr(p, attr) * s})
                if attr == "char_yield_dry":  # keep mass balance closed by rescaling the other fractions
                    rest_old = 1 - base_p.char_yield_dry; rest_new = 1 - p.char_yield_dry
                    k = rest_new / rest_old if rest_old else 0
                    p = replace(p, liquid_yield_dry=base_p.liquid_yield_dry * k, gas_yield_dry=base_p.gas_yield_dry * k,
                                other_yield_dry=base_p.other_yield_dry * k)
            try: res.append(surplus(p, e) - base)
            except ValueError: res.append(0.0)
        out.append({"input": label, "low": res[0], "high": res[1]})
    return base, sorted(out, key=lambda r: -max(abs(r["low"]), abs(r["high"])))
