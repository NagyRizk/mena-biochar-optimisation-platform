"""Transparent, deterministic explanations for model outputs and constraints."""
import pandas as pd

def cost_revenue_breakdown(result):
    costs = {
        "Feedstock procurement": result["feedstock_cost_usd_y"],
        "Inbound logistics": result["transport_cost_usd_y"],
        "Electricity": result["electricity_cost_usd_y"],
        "Process and drying heat": result["heat_cost_usd_y"],
        "Annualised capital recovery": result["annualised_capex_usd_y"],
        "Fixed operating cost": result["fixed_opex_usd_y"],
        "Labour": result["labour_usd_y"],
        "Application-route cost": result["route_cost_usd_y"],
    }
    revenues = {
        "Product revenue": result["product_revenue_usd_y"],
        "Energy export revenue": result.get("energy_revenue_usd_y", 0),
        "Carbon-credit revenue": result["carbon_revenue_usd_y"],
        "Annualised capital recovery": result["annualised_capex_usd_y"],
    }
    return pd.DataFrame(
        [{"category": k, "type": "Cost", "usd_per_year": v} for k,v in costs.items()] +
        [{"category": k, "type": "Revenue", "usd_per_year": v} for k,v in revenues.items()]
    )

def deterministic_reasons(result, inputs, gate):
    reasons = []
    if inputs["moisture"] > 0.20:
        reasons.append("Feed moisture exceeds 20 wt% wet basis; the screening model increases drying heat demand with moisture.")
    else:
        reasons.append("Drying duty is calculated from the selected wet-basis feed moisture; no measured dryer performance is implied.")
    if inputs["transport_km"] >= 100:
        reasons.append("The selected transport distance materially increases inbound logistics cost and the logistics-emissions proxy.")
    if result["marketable_char_tpy"] < result["char_tpy"]:
        reasons.append("Modelled char output exceeds the route's assumed market-demand cap; revenue is limited to marketable output.")
    if not gate["route_eligible_by_model"]:
        reasons.append("The selected technology-route pair is rejected by the notebook's route-eligibility matrix.")
    elif gate["required_tests"]:
        reasons.append("Route passes the model eligibility screen only; the listed laboratory, performance and/or regulatory checks remain open.")
    if result["eligible_for_CDR_screen"]:
        reasons.append("The scenario is eligible for a CDR screening calculation because the selected route is 'cdr' and the model product is biochar.")
        reasons.append("The reported net-removal quantity remains a simplified proxy, not a verified LCA/MRV result or credit issuance quantity.")
    if not result["CDR_credit_revenue_enabled"]:
        reasons.append("Carbon-credit revenue is zero because both explicit CDR crediting guard flags are not enabled.")
    reasons.append("Pareto status compares annual margin and screening net removal; it does not encode a stakeholder preference or risk tolerance.")
    return reasons

def scenario_comparison(df):
    cols = ["technology","route","annual_margin_usd_y","net_removal_tCO2py","char_tpy","pareto_optimal"]
    return df[cols].copy() if len(df) else pd.DataFrame(columns=cols)

def model_validation_warning():
    return (
        "The notebook's production-property predictors are research baselines evaluated with publication-grouped "
        "cross-validation. Their predictive metrics are not evidence of reactor guarantees or independent plant validation. "
        "The application does not currently use these research predictors to determine the economics or optimiser ranking."
    )
