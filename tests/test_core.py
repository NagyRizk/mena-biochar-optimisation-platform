from engine.core import evaluate_configuration, run_optimisation, application_gate

def test_reference_scenario_returns_consistent_mass_outputs():
    result = evaluate_configuration("Egypt","rice_husk",10000,0.12,60,
                                    "slow_pyrolysis","cdr",0.85)
    assert result is not None
    assert result["dry_feed_tpy"] > 0
    assert result["char_tpy"] < result["dry_feed_tpy"]
    assert result["carbon_revenue_usd_y"] == 0
    assert result["CDR_credit_revenue_enabled"] is False

def test_route_gate_rejects_hydrochar_for_cdr():
    gate = application_gate("hydrothermal_carbonisation","cdr")
    assert gate["route_eligible_by_model"] is False
    assert gate["certification_claim_allowed"] is False

def test_optimiser_returns_pareto_subset():
    all_rows, pareto = run_optimisation()
    assert len(all_rows) > 0
    assert len(pareto) > 0
    assert pareto["pareto_optimal"].all()
