from engine.core import evaluate_configuration, run_optimisation, application_gate


def test_reference_scenario_returns_consistent_mass_outputs():
    result = evaluate_configuration("Egypt", "rice_husk", 10000, 0.12, 60,
                                    "slow_pyrolysis", "cdr", 0.85)
    assert result is not None
    assert result["dry_feed_tpy"] > 0
    assert result["char_tpy"] < result["dry_feed_tpy"]
    assert result["carbon_revenue_usd_y"] == 0
    assert result["CDR_credit_revenue_enabled"] is False


def test_route_gate_rejects_hydrochar_for_cdr():
    gate = application_gate("hydrothermal_carbonisation", "cdr")
    assert gate["route_eligible_by_model"] is False
    assert gate["certification_claim_allowed"] is False


def test_optimiser_returns_pareto_subset():
    all_rows, pareto = run_optimisation()
    assert len(all_rows) > 0
    assert len(pareto) > 0
    assert pareto["pareto_optimal"].all()


def test_financial_metrics_separate_operating_surplus_from_capital_recovery():
    r = evaluate_configuration("Egypt", "rice_husk", 10000, 0.12, 60,
                               "slow_pyrolysis", "soil", 0.85)
    assert abs(r["annual_economic_surplus_usd_y"] -
               (r["ebitda_like_usd_y"] - r["annualised_capex_usd_y"])) < 1e-7
    assert r["annual_margin_usd_y"] == r["annual_economic_surplus_usd_y"]
    assert r["total_cost_usd_y"] == r["operating_cost_usd_y"] + r["annualised_capex_usd_y"]


def test_energy_revenue_uses_gj_times_usd_per_gj():
    r = evaluate_configuration("Egypt", "rice_husk", 10000, 0.12, 60,
                               "gasification", "energy_recovery", 0.85)
    assert r["energy_export_GJ_y"] > 0
    assert abs(r["energy_revenue_usd_y"] -
               r["energy_export_GJ_y"] * r["energy_price_usd_GJ"]) < 1e-7
    assert r["product_revenue_usd_y"] == 0


def test_solid_fuel_route_uses_product_lhv_not_tonnes_as_energy():
    r = evaluate_configuration("Egypt", "rice_husk", 10000, 0.12, 60,
                               "torrefaction", "solid_fuel", 0.85)
    assert abs(r["energy_export_GJ_y"] -
               r["char_tpy"] * 18.0) < 1e-7
    assert r["energy_revenue_usd_y"] > 0


def test_carbon_revenue_remains_disabled_by_default():
    r = evaluate_configuration("Egypt", "rice_husk", 10000, 0.12, 60,
                               "slow_pyrolysis", "cdr", 0.85)
    assert r["net_removal_tCO2py"] >= 0
    assert r["carbon_revenue_usd_y"] == 0
