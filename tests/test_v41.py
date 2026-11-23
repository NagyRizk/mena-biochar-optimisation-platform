"""Independent hand calculations for the v4.1 flow and carbon-credit features."""
import math
from engine.models import ProcessInputs, EconomicInputs, calculate_technical, calculate_economics
from engine.flows import mass_flows, energy_flows
from engine.carbon import credit_calc, effective_price_on_gross


def _case(**kw):
    base = dict(wet_feed_t_y=10000.0, moisture_wet_basis=0.15, char_yield_dry=0.29, liquid_yield_dry=0.40, gas_yield_dry=0.31, other_yield_dry=0.0,
                reactor_temp_C=540.0, feed_temp_C=25.0, use_steam_tables=False, char_carbon_fraction=0.757, stable_carbon_fraction=0.83, feed_carbon_fraction_dry=0.45)
    base.update(kw); return ProcessInputs(**base)


def test_hand_calculation_heat_and_carbon():
    p = _case(); t = calculate_technical(p)
    dry, water = 8500.0, 1500.0
    q_water = water * (4.18 * 75 + 2257 + 2.01 * 440) / 1000          # GJ/y
    q_solid = dry * 1.5 * 515 / 1000
    useful = q_water + q_solid
    purchased = useful / (1 - 0.15) / 0.75
    assert math.isclose(t["useful_process_heat_GJ_y"], useful, rel_tol=1e-9)
    assert math.isclose(t["purchased_heat_requirement_GJ_y"], purchased, rel_tol=1e-9)
    gross_co2 = dry * 0.29 * 0.757 * 0.83 * 44 / 12
    assert math.isclose(t["gross_stored_co2_t_y"], gross_co2, rel_tol=1e-9)
    assert math.isclose(gross_co2, 5678.9, rel_tol=1e-4)                 # tonnes CO2/y, hand total
    assert math.isclose(t["carbon_retained_fraction"], dry * 0.29 * 0.757 / (dry * 0.45), rel_tol=1e-9)


def test_energy_balance_closes_and_self_sufficiency():
    for kw in ({}, {"liquid_to_heat_fraction": 0.5}, {"liquid_to_heat_fraction": 1.0, "recoverable_coproduct_heat_fraction": 0.9}):
        p = _case(**kw); t = calculate_technical(p); e = energy_flows(t, p)
        assert math.isclose(e["balance_in"], e["requirement"], rel_tol=1e-9)
        assert math.isclose(e["balance_out"], e["requirement"], rel_tol=1e-9)
        assert 0 <= e["self_sufficiency"] <= 1
        out = {}
        for a, b, v in e["links"]: out[b] = out.get(b, 0) + v
        inn = {}
        for a, b, v in e["links"]: inn[a] = inn.get(a, 0) + v
        assert math.isclose(inn["Recovered heat"], out["Recovered heat"], rel_tol=1e-9)


def test_mass_flows_conserve():
    t = calculate_technical(_case())
    L = mass_flows(t); out = {}
    for a, b, v in L: out[a] = out.get(a, 0) + v
    assert math.isclose(out["Wet feed"], 10000.0) and math.isclose(out["Dry feed"], 8500.0)


def test_htc_energy_balance():
    p = _case(process_type="htc", reactor_temp_C=220.0, moisture_wet_basis=0.75); t = calculate_technical(p); e = energy_flows(t, p)
    assert math.isclose(e["balance_out"], e["requirement"], rel_tol=1e-9)


def test_credit_calculator_hand_numbers():
    c = credit_calc(5678.9, 135.0, 0.15, 0.10, 8.0)
    assert math.isclose(c["credits_t_y"], 5678.9 * 0.85 * 0.90)
    assert math.isclose(c["revenue_usd_y"], c["credits_t_y"] * 135.0)
    assert math.isclose(c["net_revenue_usd_y"], c["credits_t_y"] * 127.0)
    assert math.isclose(c["gross_t_y"], c["lifecycle_t_y"] + c["buffer_t_y"] + c["credits_t_y"])
    assert math.isclose(c["cars_equivalent"], c["credits_t_y"] / 4.6)


def test_effective_price_reproduces_net_revenue_in_economic_model():
    p = _case(); t = calculate_technical(p); price, life, buf, fee = 135.0, 0.15, 0.10, 8.0
    eff = effective_price_on_gross(price, life, buf, fee)
    ec = calculate_economics(t, p, EconomicInputs(carbon_credit_usd_tco2e=eff))
    assert math.isclose(ec["carbon_revenue_usd_y"], credit_calc(t["gross_stored_co2_t_y"], price, life, buf, fee)["net_revenue_usd_y"], rel_tol=1e-9)
