"""Calculation engine adapted from MENA_Biochar_Optimisation_Platform_FINAL.ipynb.

The scenario constants below are copied from the notebook. They remain editable
screening assumptions, not verified country quotations or vendor guarantees.
"""
from itertools import product
import pandas as pd

COUNTRY_SCENARIOS = {
    'Egypt': dict(currency='EGP', fx_per_usd=50.0, electricity_usd_kwh=0.10, heat_fuel_usd_GJ=8.0, labour_usd_t_y=18.0, logistics_usd_t_km=0.08, feedstock_gate_usd_t=12.0, char_price_usd_t=180.0, carbon_price_usd_t=100.0, demand_char_t_y=15000),
    'Saudi Arabia':dict(currency='SAR', fx_per_usd=3.75, electricity_usd_kwh=0.08, heat_fuel_usd_GJ=6.0, labour_usd_t_y=30.0, logistics_usd_t_km=0.10, feedstock_gate_usd_t=25.0, char_price_usd_t=220.0, carbon_price_usd_t=100.0, demand_char_t_y=20000),
    'UAE':         dict(currency='AED', fx_per_usd=3.6725, electricity_usd_kwh=0.11, heat_fuel_usd_GJ=9.0, labour_usd_t_y=40.0, logistics_usd_t_km=0.12, feedstock_gate_usd_t=35.0, char_price_usd_t=260.0, carbon_price_usd_t=100.0, demand_char_t_y=12000),
    'Morocco':     dict(currency='MAD', fx_per_usd=10.0, electricity_usd_kwh=0.12, heat_fuel_usd_GJ=10.0, labour_usd_t_y=20.0, logistics_usd_t_km=0.07, feedstock_gate_usd_t=10.0, char_price_usd_t=170.0, carbon_price_usd_t=100.0, demand_char_t_y=10000),
    'Jordan':      dict(currency='JOD', fx_per_usd=0.709, electricity_usd_kwh=0.15, heat_fuel_usd_GJ=12.0, labour_usd_t_y=28.0, logistics_usd_t_km=0.09, feedstock_gate_usd_t=15.0, char_price_usd_t=190.0, carbon_price_usd_t=100.0, demand_char_t_y=5000),
    'Oman':        dict(currency='OMR', fx_per_usd=0.385, electricity_usd_kwh=0.10, heat_fuel_usd_GJ=8.0, labour_usd_t_y=32.0, logistics_usd_t_km=0.09, feedstock_gate_usd_t=18.0, char_price_usd_t=210.0, carbon_price_usd_t=100.0, demand_char_t_y=7000),
}
FEEDSTOCKS = {
 'rice_husk': dict(ash_frac=0.18, carbon_dry=0.40, nitrogen_dry=0.005, contamination=0.02),
 'rice_straw': dict(ash_frac=0.17, carbon_dry=0.42, nitrogen_dry=0.006, contamination=0.02),
 'wheat_straw': dict(ash_frac=0.08, carbon_dry=0.45, nitrogen_dry=0.006, contamination=0.02),
 'cotton_stalk': dict(ash_frac=0.04, carbon_dry=0.46, nitrogen_dry=0.007, contamination=0.02),
 'date_palm': dict(ash_frac=0.07, carbon_dry=0.45, nitrogen_dry=0.008, contamination=0.02),
 'wood': dict(ash_frac=0.01, carbon_dry=0.50, nitrogen_dry=0.002, contamination=0.01),
 'manure': dict(ash_frac=0.30, carbon_dry=0.36, nitrogen_dry=0.025, contamination=0.08),
}
TECHNOLOGIES = {
 'slow_pyrolysis': dict(product='biochar', char_yield=0.32, process_heat_GJ_t_dry=1.6, electricity_kWh_t_dry=90, capex_usd_per_tpy=950, fixed_opex_fraction=0.06, char_C_fraction=0.68, stable_C_fraction=0.70, allowed_routes=['soil','construction','activation_precursor','cdr']),
 'fast_pyrolysis': dict(product='char_plus_bio_oil', char_yield=0.15, process_heat_GJ_t_dry=2.2, electricity_kWh_t_dry=130, capex_usd_per_tpy=1500, fixed_opex_fraction=0.07, char_C_fraction=0.72, stable_C_fraction=0.55, allowed_routes=['soil','construction','activation_precursor']),
 'flash_pyrolysis':dict(product='char_plus_vapours', char_yield=0.10, process_heat_GJ_t_dry=2.8, electricity_kWh_t_dry=170, capex_usd_per_tpy=1900, fixed_opex_fraction=0.08, char_C_fraction=0.75, stable_C_fraction=0.50, allowed_routes=['soil','construction']),
 'gasification': dict(product='gas_and_ash_char', char_yield=0.08, process_heat_GJ_t_dry=1.3, electricity_kWh_t_dry=110, capex_usd_per_tpy=2100, fixed_opex_fraction=0.08, char_C_fraction=0.45, stable_C_fraction=0.30, allowed_routes=['energy_recovery'], energy_export_GJ_t_dry=4.5),
 'torrefaction': dict(product='torrefied_solid', char_yield=0.70, process_heat_GJ_t_dry=0.8, electricity_kWh_t_dry=55, capex_usd_per_tpy=500, fixed_opex_fraction=0.05, char_C_fraction=0.58, stable_C_fraction=0.20, allowed_routes=['solid_fuel'], solid_product_LHV_GJ_t=18.0),
 'hydrothermal_carbonisation': dict(product='hydrochar', char_yield=0.55, process_heat_GJ_t_dry=2.5, electricity_kWh_t_dry=100, capex_usd_per_tpy=1800, fixed_opex_fraction=0.08, char_C_fraction=0.55, stable_C_fraction=0.35, allowed_routes=['soil_screening','solid_fuel']),
}
ROUTES = {
 'soil': dict(price_key='char_price_usd_t', route_cost_usd_t=35, demand_fraction=1.0, needs_quality=True),
 'construction': dict(price_key='char_price_usd_t', route_cost_usd_t=55, demand_fraction=0.5, needs_quality=True),
 'activation_precursor': dict(price_key='char_price_usd_t', route_cost_usd_t=90, demand_fraction=0.15, needs_quality=True),
 'cdr': dict(price_key='char_price_usd_t', route_cost_usd_t=45, demand_fraction=0.5, needs_quality=True),
 'energy_recovery': dict(price_key=None, route_cost_usd_t=15, demand_fraction=1.0, needs_quality=False),
 'solid_fuel': dict(price_key=None, route_cost_usd_t=20, demand_fraction=1.0, needs_quality=False),
 'soil_screening': dict(price_key='char_price_usd_t', route_cost_usd_t=45, demand_fraction=0.2, needs_quality=True),
}
ENERGY_VALUE_USD_GJ = 4.0  # illustrative energy-sale price, USD/GJ; replace with an offtake quote
CDR_CREDITING_ENABLED = False
CDR_ACCOUNTING_INPUTS_VERIFIED = False
DISCOUNT_RATE = 0.12
PLANT_LIFE_Y = 15
PLANT_AVAILABILITY = 0.85
DEFAULT_COUNTRY = "Egypt"
DEFAULT_FEEDSTOCK = "rice_husk"

APPLICATION_REQUIREMENTS = {
 'soil': ['H/Corg and O/Corg; PAHs; heavy metals; PCBs/dioxins where relevant; pH; EC; ash; nutrients; pathogen/contaminant screen; agronomic field validation'],
 'construction': ['particle size; moisture; ash/mineralogy; compressive strength; durability; leaching; fire/smoke behaviour; compatibility with binder; standards testing'],
 'activation_precursor': ['activation route and yield; BET surface area; pore-size distribution; iodine/methylene-blue adsorption; abrasion/hardness; chemical/water use; effluent treatment'],
 'cdr': ['approved methodology; feedstock sustainability; chain of custody; net lifecycle removal; stability/permanence; leakage; MRV; independent validation/verification'],
 'energy_recovery': ['LHV; ash fusion; emissions; particulate/NOx/SOx; operating permits; boiler/gasifier compatibility'],
 'solid_fuel': ['LHV; moisture; ash; durability; emissions; applicable fuel/product standards'],
 'soil_screening': ['hydrochar-specific contaminant and agronomic testing; soil/ecotoxicity assessment; jurisdictional approval'],
}

def capital_recovery_factor(rate, years):
    return rate*(1+rate)**years/((1+rate)**years-1) if rate else 1/years

def evaluate_configuration(country, feedstock, feed_tpy_as_received, moisture_wb, transport_km,
                           technology, route, availability=0.85, char_price_override=None,
                           carbon_credit_price=None, capex_multiplier=1.0, energy_multiplier=1.0,
                           market_override=None, technology_override=None, discount_rate=DISCOUNT_RATE,
                           plant_life_y=PLANT_LIFE_Y, route_override=None):
    """Evaluate one steady-state case; all commercial inputs are screening assumptions.

    EBITDA-like operating surplus excludes capital recovery. Annual economic surplus
    deducts the annualised capital charge and is retained as the optimisation objective.
    """
    if technology not in TECHNOLOGIES or feedstock not in FEEDSTOCKS or country not in COUNTRY_SCENARIOS:
        raise ValueError("Unknown country, feedstock or technology")
    if not (0 <= discount_rate <= 1) or plant_life_y < 1:
        raise ValueError("Discount rate must be in [0, 1] and plant life at least one year")
    if capex_multiplier < 0 or energy_multiplier < 0:
        raise ValueError("CAPEX and energy multipliers must be non-negative")
    tech = TECHNOLOGIES[technology].copy()
    tech.update(technology_override or {})
    market = (market_override or COUNTRY_SCENARIOS[country]).copy()
    if route not in tech["allowed_routes"] or route not in ROUTES:
        return None
    if not (0 <= moisture_wb < 0.9):
        raise ValueError("Moisture must be a wet-basis fraction between 0 and 0.9")
    if feed_tpy_as_received < 0 or transport_km < 0 or not (0 < availability <= 1):
        raise ValueError("Feed rate and transport must be non-negative; availability must be in (0, 1].")

    processed_feed_tpy_as_received = feed_tpy_as_received * availability
    dry_feed_tpy = processed_feed_tpy_as_received * (1 - moisture_wb)
    water_per_dry_t = moisture_wb / max(1 - moisture_wb, 1e-9)
    drying_heat_GJ_t_dry = water_per_dry_t * 2.6 / 0.70
    total_heat_GJ_t_dry = (drying_heat_GJ_t_dry + tech["process_heat_GJ_t_dry"]) * energy_multiplier
    char_tpy = dry_feed_tpy * tech["char_yield"]

    feed_cost = processed_feed_tpy_as_received * market["feedstock_gate_usd_t"]
    transport_cost = processed_feed_tpy_as_received * transport_km * market["logistics_usd_t_km"]
    electricity_cost = dry_feed_tpy * tech["electricity_kWh_t_dry"] * market["electricity_usd_kwh"] * energy_multiplier
    heat_cost = dry_feed_tpy * total_heat_GJ_t_dry * market["heat_fuel_usd_GJ"]
    installed_capex = dry_feed_tpy * tech["capex_usd_per_tpy"] * capex_multiplier
    annual_capital = installed_capex * capital_recovery_factor(discount_rate, plant_life_y)
    fixed_opex = installed_capex * tech["fixed_opex_fraction"]
    labour = dry_feed_tpy * market["labour_usd_t_y"]

    route_cfg = ROUTES[route].copy()
    route_cfg.update(route_override or {})
    route_cost = char_tpy * route_cfg["route_cost_usd_t"]
    unit_price = float(char_price_override if char_price_override is not None else market["char_price_usd_t"])
    energy_price = float(market.get("energy_price_usd_GJ", ENERGY_VALUE_USD_GJ))
    marketable_char_t = min(char_tpy, market.get("demand_char_t_y", 0) * route_cfg["demand_fraction"]) if route_cfg["price_key"] else char_tpy
    product_revenue = marketable_char_t * unit_price if route_cfg["price_key"] else 0.0

    # Energy sales use an energy quantity, not tonnes multiplied directly by USD/GJ.
    # These are explicit placeholder export yields/LHV values and are not plant guarantees.
    energy_export_GJ_y = 0.0
    if route == "energy_recovery":
        energy_export_GJ_y = dry_feed_tpy * float(tech.get("energy_export_GJ_t_dry", 0.0)) * energy_multiplier
    elif route == "solid_fuel":
        energy_export_GJ_y = char_tpy * float(tech.get("solid_product_LHV_GJ_t", 0.0))
    energy_revenue = energy_export_GJ_y * energy_price

    eligible_for_cdr = route == "cdr" and tech["product"] == "biochar"
    gross_stable_C_t = char_tpy * tech["char_C_fraction"] * tech["stable_C_fraction"] if eligible_for_cdr else 0.0
    gross_stable_CO2_t = gross_stable_C_t * 44 / 12
    heat_emissions = dry_feed_tpy * total_heat_GJ_t_dry * 0.056
    grid_emissions = dry_feed_tpy * tech["electricity_kWh_t_dry"] * 0.00045
    logistics_emissions = processed_feed_tpy_as_received * transport_km * 0.00008
    lifecycle_emissions_tCO2 = heat_emissions + grid_emissions + logistics_emissions
    net_removal_tCO2 = max(0.0, gross_stable_CO2_t - lifecycle_emissions_tCO2) if eligible_for_cdr else 0.0
    c_price = carbon_credit_price if carbon_credit_price is not None else market["carbon_price_usd_t"]
    crediting_ready = bool(CDR_CREDITING_ENABLED and CDR_ACCOUNTING_INPUTS_VERIFIED)
    carbon_revenue = net_removal_tCO2 * c_price if (eligible_for_cdr and crediting_ready) else 0.0

    operating_cost = feed_cost + transport_cost + electricity_cost + heat_cost + fixed_opex + labour + route_cost
    total_revenue = product_revenue + energy_revenue + carbon_revenue
    ebitda_like = total_revenue - operating_cost
    total_cost_including_capital = operating_cost + annual_capital
    economic_surplus = total_revenue - total_cost_including_capital
    return {
        "country": country, "feedstock": feedstock, "technology": technology,
        "product_type": tech["product"], "route": route,
        "processed_feed_tpy_as_received": processed_feed_tpy_as_received,
        "dry_feed_tpy": dry_feed_tpy, "char_tpy": char_tpy,
        "marketable_char_tpy": marketable_char_t,
        "yield_dry_basis": tech["char_yield"],
        "gross_stable_CO2_tpy": gross_stable_CO2_t,
        "lifecycle_emissions_tCO2py": lifecycle_emissions_tCO2,
        "net_removal_tCO2py": net_removal_tCO2,
        "feedstock_cost_usd_y": feed_cost, "transport_cost_usd_y": transport_cost,
        "electricity_cost_usd_y": electricity_cost, "heat_cost_usd_y": heat_cost,
        "annualised_capex_usd_y": annual_capital, "fixed_opex_usd_y": fixed_opex,
        "labour_usd_y": labour, "route_cost_usd_y": route_cost,
        "operating_cost_usd_y": operating_cost,
        "product_revenue_usd_y": product_revenue,
        "energy_export_GJ_y": energy_export_GJ_y, "energy_revenue_usd_y": energy_revenue,
        "carbon_revenue_usd_y": carbon_revenue,
        "total_cost_usd_y": total_cost_including_capital,
        "total_revenue_usd_y": total_revenue,
        "ebitda_like_usd_y": ebitda_like,
        "annual_economic_surplus_usd_y": economic_surplus,
        "annual_margin_usd_y": economic_surplus,
        "unit_product_price_usd_t": unit_price,
        "energy_price_usd_GJ": energy_price,
        "eligible_for_CDR_screen": eligible_for_cdr,
        "CDR_credit_revenue_enabled": crediting_ready,
        "net_removal_status": "SCREENING PROXY ONLY — NOT VERIFIED LCA/MRV",
        "quality_status": "LAB TESTS REQUIRED — NOT CERTIFIED",
        "finance_note": "EBITDA-like operating surplus excludes annualised capital recovery; annual economic surplus deducts it. NPV/IRR/payback are not calculated because project cash-flow, tax, working-capital and financing schedules are not modelled.",
        "mass_balance_note": "Yield, energy export and LHV values are editable screening placeholders; no generic coproduct balance is implied."
    }

def application_gate(technology, route):
    if technology not in TECHNOLOGIES: raise ValueError("Unknown technology")
    tech=TECHNOLOGIES[technology]
    eligible = route in tech['allowed_routes']
    if route=='cdr' and tech['product']!='biochar': eligible=False
    return {'route_eligible_by_model':eligible, 'certification_claim_allowed':False,
            'status':'ELIGIBLE FOR FURTHER TESTING' if eligible else 'NOT ELIGIBLE IN CURRENT SCREEN',
            'required_tests':APPLICATION_REQUIREMENTS.get(route,[])}

def run_optimisation(country=DEFAULT_COUNTRY, feedstock=DEFAULT_FEEDSTOCK, feed_tpy=10000.0,
                     moisture=0.12, transport_km=60.0, availability=PLANT_AVAILABILITY,
                     capex_multiplier=1.0, energy_multiplier=1.0, market_override=None, technology_overrides=None, discount_rate=DISCOUNT_RATE, plant_life_y=PLANT_LIFE_Y, route_overrides=None):
    rows=[]
    for tech_name, tech in TECHNOLOGIES.items():
        for route in tech['allowed_routes']:
            row=evaluate_configuration(country,feedstock,feed_tpy,moisture,transport_km,
                 tech_name,route,availability,capex_multiplier=capex_multiplier,energy_multiplier=energy_multiplier,
                 market_override=market_override, technology_override=(technology_overrides or {}).get(tech_name),
                 discount_rate=discount_rate, plant_life_y=plant_life_y,
                 route_override=(route_overrides or {}).get(route))
            if row: rows.append(row)
    df=pd.DataFrame(rows)
    if df.empty: return df,df
    vals=df[['annual_margin_usd_y','net_removal_tCO2py']].to_numpy()
    is_pareto=[True]*len(df)
    for i,(m,c) in enumerate(vals):
        dominated=(vals[:,0]>=m)&(vals[:,1]>=c)&((vals[:,0]>m)|(vals[:,1]>c))
        if dominated.any(): is_pareto[i]=False
    df['pareto_optimal']=is_pareto
    return df.sort_values(['pareto_optimal','annual_margin_usd_y'],ascending=[False,False]), df[df.pareto_optimal].sort_values('annual_margin_usd_y',ascending=False)

def run_sensitivity(country, feedstock, feed_tpy, moisture, transport_km, availability):
    rows=[]
    base_market=COUNTRY_SCENARIOS[country]
    for feed_mult, capex_mult, energy_mult in product([0.7,1.0,1.3],[0.8,1.0,1.3],[0.8,1.0,1.25]):
        # Pass a per-call market copy; do not mutate shared globals across cloud sessions.
        scenario=base_market.copy()
        scenario['feedstock_gate_usd_t'] *= feed_mult
        df,_=run_optimisation(country,feedstock,feed_tpy,moisture,transport_km,availability,
                              capex_mult,energy_mult,market_override=scenario)
        if len(df):
            best=df.iloc[0]
            rows.append({'feedstock_cost_multiplier':feed_mult,'capex_multiplier':capex_mult,
                         'energy_multiplier':energy_mult,'best_technology':best.technology,
                         'best_route':best.route,'best_margin_usd_y':best.annual_margin_usd_y,
                         'net_removal_tCO2py':best.net_removal_tCO2py})
    return pd.DataFrame(rows)
