import pytest
from engine.models import ProcessInputs, EconomicInputs, calculate_technical, calculate_economics, pareto_front

def test_mass_balance_closes():
    p=ProcessInputs()
    t=calculate_technical(p)
    assert abs(t["mass_balance_residual_t_y"]) < 1e-8

def test_product_split_must_sum_to_one():
    p=ProcessInputs(char_yield_dry=.3,liquid_yield_dry=.3,gas_yield_dry=.3,other_yield_dry=.3)
    with pytest.raises(ValueError): calculate_technical(p)

def test_dry_feed_calculation():
    p=ProcessInputs(wet_feed_t_y=1000,moisture_wet_basis=.2)
    t=calculate_technical(p)
    assert t["dry_feed_t_y"] == pytest.approx(800)

def test_economic_surplus_relationship():
    p=ProcessInputs(); e=EconomicInputs()
    t=calculate_technical(p); ec=calculate_economics(t,p,e)
    assert ec["annual_economic_surplus_usd_y"] == pytest.approx(ec["ebitda_like_usd_y"]-ec["annualised_capex_usd_y"])

def test_heat_recovery_cannot_exceed_coproduct_energy():
    p=ProcessInputs(); t=calculate_technical(p)
    assert t["recoverable_coproduct_heat_GJ_y"] <= t["coproduct_chemical_energy_GJ_y"]

def test_pareto_front():
    rows=[
        {"annual_economic_surplus_usd_y":10,"net_removal_proxy_tco2e_y":10},
        {"annual_economic_surplus_usd_y":5,"net_removal_proxy_tco2e_y":5},
        {"annual_economic_surplus_usd_y":15,"net_removal_proxy_tco2e_y":7},
    ]
    f=pareto_front(rows)
    assert len(f)==2


# ---- data-driven layer -------------------------------------------------------
import pytest as _pt
from dataclasses import replace
from engine.predict import BiocharPredictor, stable_fraction_from_hc
from engine.design import FEEDSTOCKS, evaluate_design, search_designs, tornado
from engine.pathways import pathways_df


@_pt.fixture(scope="module")
def pred():
    return BiocharPredictor.train(run_cv=False)


def test_predictor_physical_trends(pred):
    lo, hi = pred.predict("woody", 350), pred.predict("woody", 700)
    assert lo["Yield"]["mean"] > hi["Yield"]["mean"]   # more char at low temperature
    assert lo["H_C"]["mean"] > hi["H_C"]["mean"]       # less aromatic at low temperature


def test_stable_fraction_monotonic():
    xs = [0.1, 0.4, 0.7, 1.0, 1.6]
    ys = [stable_fraction_from_hc(x) for x in xs]
    assert all(a >= b for a, b in zip(ys, ys[1:])) and 0 <= min(ys) and max(ys) <= 1


def test_design_closes_mass_balance(pred):
    for feed in FEEDSTOCKS:
        r = evaluate_design(pred, feed, 500, 60, 10, ProcessInputs(), EconomicInputs())
        assert abs(r["mass_balance_residual_t_y"]) < 1e-6


def test_search_respects_hc_constraint(pred):
    rows, front, stats = search_designs(pred, ProcessInputs(), EconomicInputs(carbon_credit_usd_tco2e=50),
                                        feeds=["Rice straw", "Cotton stalks"], max_hc=0.7)
    assert rows and front and all(r["pred_H_C"] <= 0.7 for r in rows)


def test_carbon_revenue_added():
    p, e = ProcessInputs(), EconomicInputs(carbon_credit_usd_tco2e=100)
    t = calculate_technical(p); ec = calculate_economics(t, p, e)
    assert ec["carbon_revenue_usd_y"] == pytest.approx(max(0, t["net_removal_proxy_tco2e_y"]) * 100)


def test_tornado_runs_and_is_signed_sensibly():
    base, rows = tornado(ProcessInputs(), EconomicInputs(carbon_credit_usd_tco2e=50))
    capex = next(r for r in rows if r["input"] == "CAPEX")
    assert capex["low"] > 0 > capex["high"]   # cheaper plant raises surplus


def test_pathways_table():
    assert {"Biochar", "Direct air capture + storage"} <= set(pathways_df().Pathway)


# ---- regression + new physics ---------------------------------------------------
from engine.particle import ParticleParams, simulate_particle, verify_conduction, conversion_time_s
from ai.llm import ask, LLMError


def test_energy_totals_match_hand_calculation():
    """Regression for the v1/v2 bug where totals were divided by 1000 twice."""
    p = ProcessInputs(use_steam_tables=False)
    t = calculate_technical(p)
    dry, water = 8000.0, 2000.0
    hand = (water * (4.18 * 75 + 2257 + 2.01 * 400) + dry * 1.5 * 475) / 1000   # t*kJ/kg = MJ -> GJ
    assert t["useful_process_heat_GJ_y"] == pytest.approx(hand, rel=1e-9)
    assert t["coproduct_chemical_energy_GJ_y"] == pytest.approx(8000 * 0.30 * 8, rel=1e-9)
    assert t["liquid_to_heat_energy_GJ_y"] == 0.0  # default: liquid is sold, not burned


def test_steam_tables_close_to_constants():
    a = calculate_technical(ProcessInputs(use_steam_tables=True))["useful_process_heat_GJ_y"]
    b = calculate_technical(ProcessInputs(use_steam_tables=False))["useful_process_heat_GJ_y"]
    assert a == pytest.approx(b, rel=0.03)


def test_carbon_balance_flags_infeasible():
    p = ProcessInputs(char_yield_dry=0.6, liquid_yield_dry=0.2, gas_yield_dry=0.2, other_yield_dry=0.0,
                      char_carbon_fraction=0.9, feed_carbon_fraction_dry=0.3)
    assert calculate_technical(p)["carbon_balance_ok"] is False


def test_particle_solver_matches_analytical_sphere():
    assert verify_conduction()["max_error_pct"] < 0.5


def test_particle_hotter_converts_faster_and_bounded():
    pp = ParticleParams()
    t_lo, t_hi = conversion_time_s(400, pp), conversion_time_s(600, pp)
    assert t_hi < t_lo
    r = simulate_particle(pp, 600, 1.0)
    assert 0 <= r["X_mean"].min() and r["X_mean"].max() <= 1 and r["T_center_C"].max() <= pp.T_inf_C + 1e-6


def test_llm_client_with_fake_transport():
    class R:
        status_code = 200
        def json(self): return {"choices": [{"message": {"content": " ok "}}]}
    assert ask("p", {"a": 1}, None, "k", post=lambda *a, **k: R()) == "ok"
    class E:
        status_code = 401; text = "x"
        def json(self): return {"error": {"message": "bad key"}}
    with _pt.raises(LLMError): ask("p", {}, None, "k", post=lambda *a, **k: E())
    with _pt.raises(LLMError): ask("p", {}, None, "")


def test_conversion_constraint_binds_for_large_particles(pred):
    from dataclasses import replace as _rp
    big = _rp(ParticleParams(), diameter_mm=90.0, h_W_m2K=15.0)
    rows, front, stats = search_designs(pred, ProcessInputs(), EconomicInputs(), feeds=["Cotton stalks"], particle=big, safety=1.5)
    assert stats["rejected_conversion"] > 0
    assert all(r["duration_min"] * 60 >= 1.5 * r["t95_min"] * 60 - 1e-6 for r in rows)


# ---- process types ---------------------------------------------------------------
from engine.processes import PROCESSES


def test_all_processes_close_mass_and_run(pred):
    for proc in PROCESSES:
        r = evaluate_design(pred, "Cotton stalks", PROCESSES[proc]["T_default"], PROCESSES[proc]["dur_default"], 10,
                            ProcessInputs(), EconomicInputs(), process=proc)
        assert abs(r["mass_balance_residual_t_y"]) < 1e-6, proc
        assert r["process_type"] == proc


def test_htc_has_no_vaporisation_and_wet_feed_is_cheaper_to_heat():
    wet = dict(moisture_wet_basis=0.75, wet_feed_t_y=10000.0)
    htc = calculate_technical(ProcessInputs(process_type="htc", reactor_temp_C=220, **wet))
    pyro = calculate_technical(ProcessInputs(process_type="slow_pyrolysis", reactor_temp_C=500, **wet))
    assert htc["water_vaporisation_GJ_y"] == 0 and htc["steam_superheat_GJ_y"] == 0
    assert htc["useful_process_heat_GJ_y"] < pyro["useful_process_heat_GJ_y"]


def test_bridgwater_anchors_sum_to_one():
    for k, v in PROCESSES.items():
        if "anchors" in v: assert abs(sum(v["anchors"].values()) - 1.0) < 1e-9, k


def test_multi_process_search(pred):
    rows, front, stats = search_designs(pred, ProcessInputs(), EconomicInputs(), feeds=["Olive stones / pits"],
                                        processes=("slow_pyrolysis", "fast_pyrolysis", "torrefaction", "gasification", "htc"), max_hc=None)
    assert {r["process"] for r in rows} == {"slow_pyrolysis", "fast_pyrolysis", "torrefaction", "gasification", "htc"}


def test_liquid_burn_fraction_prevents_double_counting():
    p = ProcessInputs(liquid_to_heat_fraction=0.5)
    e = EconomicInputs(liquid_price_usd_t=100.0)
    t = calculate_technical(p)
    ec = calculate_economics(t, p, e)
    assert t["liquid_to_heat_energy_GJ_y"] == pytest.approx(
        t["liquid_t_y"] * 0.5 * p.liquid_lhv_MJ_kg
    )
    assert ec["liquid_revenue_usd_y"] == pytest.approx(t["liquid_t_y"] * 0.5 * 100.0)


def test_liquid_burn_fraction_validation():
    p = ProcessInputs(liquid_to_heat_fraction=1.1)
    with pytest.raises(ValueError):
        calculate_technical(p)


def test_predictor_uses_baseline_when_it_wins_grouped_cv():
    model = BiocharPredictor.train(run_cv=True)
    for target, metrics in model.cv.items():
        expected = "feedstock_class_mean" if metrics["baseline_r2"] > metrics["r2"] else "random_forest"
        assert model.model_strategy[target] == expected


def test_particle_kinetics_validity_flag():
    base = ParticleParams()
    outside = simulate_particle(base, 1.0, dt_s=0.5)
    inside = simulate_particle(replace(base, T_inf_C=350.0), 1.0, dt_s=0.5)
    assert outside["kinetics_extrapolated"] is True
    assert inside["kinetics_extrapolated"] is False


def test_nan_inputs_are_rejected():
    with pytest.raises(ValueError):
        calculate_technical(ProcessInputs(moisture_wet_basis=float("nan")))
    with pytest.raises(ValueError):
        calculate_economics(calculate_technical(ProcessInputs()), ProcessInputs(), EconomicInputs(capex_usd=float("nan")))


def test_sub_boiling_pyrolysis_evaporation_assumption_is_rejected():
    with pytest.raises(ValueError, match="at least 100"):
        calculate_technical(ProcessInputs(reactor_temp_C=80.0))


def test_electricity_export_does_not_double_count_surplus_heat():
    p = ProcessInputs()
    t = calculate_technical(p)
    e = EconomicInputs(electricity_export_fraction_of_surplus=0.5, electricity_conversion_efficiency=0.3)
    ec = calculate_economics(t, p, e)
    assert ec["export_heat_GJ_y"] == pytest.approx(t["heat_surplus_GJ_y"] * 0.5)
    assert ec["remaining_heat_surplus_GJ_y"] + ec["export_heat_GJ_y"] == pytest.approx(t["heat_surplus_GJ_y"])
    assert ec["export_electricity_kwh_y"] == pytest.approx(ec["export_heat_GJ_y"] * 277.7777778 * 0.3)


def test_invalid_economic_export_fraction_rejected():
    p = ProcessInputs(); t = calculate_technical(p)
    with pytest.raises(ValueError):
        calculate_economics(t, p, EconomicInputs(electricity_export_fraction_of_surplus=1.2))


def test_unknown_process_and_noninteger_life_are_rejected():
    with pytest.raises(ValueError, match="Unsupported process"):
        calculate_technical(ProcessInputs(process_type="magic"))
    p = ProcessInputs(); t = calculate_technical(p)
    with pytest.raises(ValueError, match="whole number"):
        calculate_economics(t, p, EconomicInputs(project_life_y=12.5))
