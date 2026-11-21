from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any
import math
from .thermo import water_enthalpies, liquid_water_heating_kJ_kg

MODEL_REGISTRY = {
    "MASS-001": {
        "name": "Dry-basis feedstock and product mass balance",
        "method": "Overall mass conservation; product split fractions are user inputs, not predicted yields.",
        "equation": "m_dry = m_wet(1 - Xw); m_char + m_liquid + m_gas + m_other = m_dry",
        "source": "Felder, Rousseau & Bullard, Elementary Principles of Chemical Processes, 4th ed., Wiley (2016), material balances.",
        "url": "https://www.wiley.com/en-us/Elementary+Principles+of+Chemical+Processes%2C+4th+Edition-p-9781119586102",
        "status": "Conservation identity; implementation tested. Product split values come from the ML-001 predictor or user inputs."
    },
    "ENERGY-001": {
        "name": "Feed heating and water evaporation duty",
        "method": "Sensible heating plus latent heat for water removed; excludes bound-water effects and detailed dryer efficiency unless explicitly entered.",
        "equation": "Q = m_dry Cp_s ΔT + m_evap[Cp,w(T_b-T_in) + ΔHvap + Cp,v(T_out-T_b)]",
        "source": "NIST Chemistry WebBook, SRD 69, Water thermochemistry and phase-change data; Chase (1998), NIST-JANAF Thermochemical Tables.",
        "url": "https://webbook.nist.gov/cgi/cbook.cgi?Name=water",
        "status": "Screening energy balance; property values are configurable approximations unless linked to a selected property package."
    },
    "PYRO-001": {
        "name": "Biomass pyrolysis product distribution",
        "method": "User-specified char/liquid/gas/other fractions on dry feed basis. This release does not infer yield from temperature.",
        "equation": "Y_char + Y_liquid + Y_gas + Y_other = 1",
        "source": "Di Blasi, C. (2008). Modeling chemical and physical processes of wood and biomass pyrolysis. Progress in Energy and Combustion Science, 34(1), 47–90. DOI: 10.1016/j.pecs.2006.12.001.",
        "url": "https://doi.org/10.1016/j.pecs.2006.12.001",
        "status": "Literature-informed model structure; numerical product fractions are scenario inputs and must be validated for the feedstock/reactor."
    },
    "ECON-001": {
        "name": "Capital recovery factor and discounted cash flow",
        "method": "Standard discounted-cash-flow screening; no taxes, debt structure, working capital or escalation unless separately modelled.",
        "equation": "CRF = i(1+i)^n / [(1+i)^n - 1]; NPV = -CAPEX + Σ CF_t/(1+i)^t",
        "source": "Peters, Timmerhaus & West, Plant Design and Economics for Chemical Engineers, 5th ed., McGraw-Hill (2003).",
        "url": "https://www.mheducation.com/highered/mhp/product/plant-design-economics-chemical-engineers-fifth-edition.html",
        "status": "Standard financial mathematics; all project-specific financial inputs are user-supplied assumptions."
    },
    "OPT-001": {
        "name": "Scenario Pareto screening",
        "method": "Non-dominated sorting across evaluated user-defined scenarios; no unvalidated surrogate model.",
        "equation": "Scenario A dominates B if A is no worse in all objectives and strictly better in at least one.",
        "source": "Deb, K. (2001). Multi-Objective Optimization Using Evolutionary Algorithms. Wiley.",
        "url": "https://doi.org/10.1002/9780470371461",
        "status": "Deterministic comparison of candidate scenarios; optimality is limited to the scenarios supplied."
    }
}

MODEL_REGISTRY.update({
    "ML-001": {
        "name": "Data-driven char property predictor",
        "method": "Random forest regression on the bundled slow-pyrolysis literature dataset (features: HTT, residence time, heating rate, feedstock class). Predicts char yield, C, ash and H/C; spread across trees is shown as uncertainty.",
        "equation": "y_hat = mean_b T_b(x); sigma = std_b T_b(x); validated with GroupKFold by publication",
        "source": "Breiman, L. (2001). Random Forests. Machine Learning 45, 5-32. DOI: 10.1023/A:1010933404324.",
        "url": "https://doi.org/10.1023/A:1010933404324",
        "status": "Published lab/pilot data only. Five-fold publication-grouped CV is compared with a feedstock-class mean; inference uses the class mean for targets where it beats the forest. Tree spread is not a calibrated interval. Not reactor-validated."
    },
    "PERM-001": {
        "name": "Char carbon permanence from H/C (screening)",
        "method": "Piecewise-linear map from predicted molar H/C to the fraction of char carbon stable beyond 100 years.",
        "equation": "f_stable = interp(H/C; [0, 0.4, 0.7, 1.0, 1.5] -> [0.90, 0.85, 0.65, 0.40, 0.20])",
        "source": "Shape follows the common H/Corg quality classes (0.4 / 0.7; 0.7 is the EBC/IBI limit). Numeric values are placeholders, not a published regression.",
        "url": "https://www.european-biochar.org/en/ct/2-EBC-Guidelines",
        "status": "PLACEHOLDER VALUES. Replace with a published BC+100 regression before any quantitative claim."
    },
    "DESIGN-001": {
        "name": "Predicted-yield process design and grid optimisation",
        "method": "Predicted char yield sets the char fraction; the non-char remainder is split liquid/gas by a user-set share. Exhaustive grid over feedstock, HTT, residence time and heating rate, then Pareto filtering.",
        "equation": "maximise (annual economic surplus, net removal proxy) over the design grid; optional constraint H/C <= limit",
        "source": "Deb, K. (2001) for Pareto dominance; grid enumeration (no stochastic optimiser).",
        "url": "https://doi.org/10.1002/9780470371461",
        "status": "Optimal only within the grid and the predictor's validity range. Liquid/gas split, costs and carbon price are assumptions."
    },
    "PATH-001": {
        "name": "CDR pathway comparison",
        "method": "Indicative global cost and potential ranges per removal pathway.",
        "equation": "n/a (literature ranges)",
        "source": "IPCC AR6 WGIII Chapter 12, Table 12.6.",
        "url": "https://www.ipcc.ch/report/ar6/wg3/chapter/chapter-12/",
        "status": "DACCS and enhanced weathering re-verified; biochar, BECCS and A/R figures recalled and flagged for re-check."
    },
})

MODEL_REGISTRY.update({
    "PART-001": {
        "name": "Particle heat transfer (1-D spherical conduction, finite volume)",
        "method": "Transient conduction in a sphere with convective surface, properties blended by conversion, implicit Euler, optional reaction enthalpy. Reduced-order, not CFD.",
        "equation": "rho cp dT/dt = (1/r^2) d/dr (k r^2 dT/dr) - dH * rho0 * (-df/dt);  -k dT/dr|R = h (T_s - T_inf)",
        "source": "Verified in code against the analytical sphere solution (Carslaw & Jaeger, Conduction of Heat in Solids, 2nd ed., 1959).",
        "url": "https://global.oup.com/academic/product/conduction-of-heat-in-solids-9780198533689",
        "status": "Verified (solves its equations correctly: <0.1% vs analytical). Not validated against measured particle temperatures; property values and h are assumptions; single particle, no bed effects."
    },
    "KIN-001": {
        "name": "One-step global devolatilisation kinetics",
        "method": "First-order Arrhenius consumption of virgin material, k = A exp(-E/RT).",
        "equation": "df/dt = -k f;  k = exp(ln A - E/(R T));  ln A = 22.2 1/s, E = 141.2 kJ/mol",
        "source": "Di Blasi, C. and Branca, C. (2001). Kinetics of primary product formation from wood pyrolysis. Ind. Eng. Chem. Res. 40(23), 5547-5556. DOI: 10.1021/ie000997e.",
        "url": "https://doi.org/10.1021/ie000997e",
        "status": "Parameters taken from the paper's abstract for beech wood, fitted over 573-708 K. Other feedstocks and higher temperatures are extrapolations. Used only for conversion time, not for product yields."
    },
})

@dataclass
class ProcessInputs:
    wet_feed_t_y: float = 10000.0
    moisture_wet_basis: float = 0.20
    char_yield_dry: float = 0.25
    liquid_yield_dry: float = 0.35
    gas_yield_dry: float = 0.30
    other_yield_dry: float = 0.10
    feed_temp_C: float = 25.0
    reactor_temp_C: float = 500.0
    solid_cp_kJ_kgK: float = 1.50
    water_cp_kJ_kgK: float = 4.18
    steam_cp_kJ_kgK: float = 2.01
    water_latent_kJ_kg: float = 2257.0
    heat_loss_fraction: float = 0.15
    dryer_efficiency: float = 0.75
    gas_lhv_MJ_kg: float = 8.0
    liquid_lhv_MJ_kg: float = 15.0
    recoverable_coproduct_heat_fraction: float = 0.50
    liquid_to_heat_fraction: float = 0.0  # liquid product diverted from sale to process fuel
    char_carbon_fraction: float = 0.70
    stable_carbon_fraction: float = 0.80
    lifecycle_emissions_tco2e_y: float = 0.0
    use_steam_tables: bool = True
    process_type: str = "slow_pyrolysis"
    htc_water_to_dry_ratio: float = 5.0        # HTC slurry water per kg dry feed (reviews: 5-25)
    htc_heat_recovery_fraction: float = 0.6    # HTC heat-exchanger recovery (assumption)
    pyrolysis_enthalpy_kJ_kg_dry: float = 0.0   # reaction heat, endothermic positive; user assumption
    feed_carbon_fraction_dry: float = 0.46      # typical lignocellulosic value; set per feedstock

@dataclass
class EconomicInputs:
    capex_usd: float = 2_000_000.0
    project_life_y: int = 15
    discount_rate: float = 0.10
    feedstock_cost_usd_t_wet: float = 15.0
    logistics_cost_usd_t_wet: float = 8.0
    char_price_usd_t: float = 180.0
    liquid_price_usd_t: float = 0.0
    electricity_price_usd_kwh: float = 0.10
    purchased_heat_price_usd_GJ: float = 8.0
    electricity_use_kwh_t_dry: float = 80.0
    labour_usd_y: float = 150_000.0
    maintenance_fraction_capex_y: float = 0.03
    other_opex_usd_y: float = 100_000.0
    annualisation_fraction: float = 1.0
    electricity_export_fraction_of_surplus: float = 0.0
    electricity_conversion_efficiency: float = 0.30
    carbon_credit_usd_tco2e: float = 0.0  # scenario assumption; only meaningful if removal is verified and creditable

def _nonnegative(name: str, value: float):
    if value < 0:
        raise ValueError(f"{name} must be non-negative")

def validate_process(x: ProcessInputs):
    if x.wet_feed_t_y <= 0: raise ValueError("Annual wet feed must be positive.")
    if not 0 <= x.moisture_wet_basis < 1: raise ValueError("Moisture must be in [0, 1).")
    ys=[x.char_yield_dry,x.liquid_yield_dry,x.gas_yield_dry,x.other_yield_dry]
    if any(y < 0 for y in ys): raise ValueError("Product fractions cannot be negative.")
    if not math.isclose(sum(ys),1.0,abs_tol=1e-6):
        raise ValueError(f"Dry-basis product fractions must sum to 1. Current sum: {sum(ys):.4f}")
    if x.reactor_temp_C <= x.feed_temp_C: raise ValueError("Reactor temperature must exceed feed temperature.")
    if not 0 < x.dryer_efficiency <= 1: raise ValueError("Dryer efficiency must be in (0, 1].")
    if not 0 <= x.heat_loss_fraction < 1: raise ValueError("Heat-loss fraction must be in [0, 1).")
    if not 0 <= x.recoverable_coproduct_heat_fraction <= 1: raise ValueError("Recovery fraction must be in [0, 1].")
    if not 0 <= x.liquid_to_heat_fraction <= 1: raise ValueError("Liquid-to-heat fraction must be in [0, 1].")
    if not 0 <= x.stable_carbon_fraction <= 1 or not 0 <= x.char_carbon_fraction <= 1:
        raise ValueError("Carbon fractions must be in [0, 1].")

def calculate_technical(x: ProcessInputs) -> dict[str, Any]:
    validate_process(x)
    wet = x.wet_feed_t_y
    dry = wet * (1-x.moisture_wet_basis)
    water_in = wet-dry
    char = dry*x.char_yield_dry
    liquid = dry*x.liquid_yield_dry
    gas = dry*x.gas_yield_dry
    other = dry*x.other_yield_dry
    # Units: tonne/y x kJ/kg = MJ/y; /1000 -> GJ/y.
    slurry_water = water_in
    if x.process_type == "htc":
        slurry_water = max(x.htc_water_to_dry_ratio*dry, water_in)
        lw = liquid_water_heating_kJ_kg(x.feed_temp_C, x.reactor_temp_C)
        water_sensible = slurry_water*lw["kJ_kg"]/1000; water_vap = 0.0; steam_superheat = 0.0
        w = {"source": lw["source"]}
    else:
        if x.use_steam_tables:
            w = water_enthalpies(x.feed_temp_C, x.reactor_temp_C, cp_w=x.water_cp_kJ_kgK, cp_v=x.steam_cp_kJ_kgK, hfg=x.water_latent_kJ_kg)
            sens_kJ, lat_kJ, sup_kJ = w["sensible"], w["latent"], w["superheat"]
        else:
            sens_kJ = x.water_cp_kJ_kgK*(100-x.feed_temp_C); lat_kJ = x.water_latent_kJ_kg
            sup_kJ = x.steam_cp_kJ_kgK*max(0,x.reactor_temp_C-100)
        water_sensible = water_in*sens_kJ/1000
        water_vap = water_in*lat_kJ/1000
        steam_superheat = water_in*sup_kJ/1000
    solids_sensible = dry*x.solid_cp_kJ_kgK*(x.reactor_temp_C-x.feed_temp_C)/1000
    reaction_heat = dry*x.pyrolysis_enthalpy_kJ_kg_dry/1000
    useful_process_heat_GJ = water_sensible+water_vap+steam_superheat+solids_sensible+reaction_heat
    if x.process_type == "htc":
        useful_process_heat_GJ *= (1 - x.htc_heat_recovery_fraction)
    gross_heat_GJ = useful_process_heat_GJ/(1-x.heat_loss_fraction)
    purchased_heat_GJ = gross_heat_GJ/x.dryer_efficiency
    # Gas is assumed available for combustion; liquid is burned only if explicitly diverted.
    # This prevents counting the same liquid mass as both sales revenue and process fuel.
    liquid_to_heat_GJ = liquid*x.liquid_to_heat_fraction*x.liquid_lhv_MJ_kg
    coproduct_chemical_GJ = gas*x.gas_lhv_MJ_kg + liquid_to_heat_GJ  # t x MJ/kg = GJ
    recoverable_heat_GJ = coproduct_chemical_GJ*x.recoverable_coproduct_heat_fraction
    heat_surplus_GJ = max(0.0,recoverable_heat_GJ-purchased_heat_GJ)
    heat_deficit_GJ = max(0.0,purchased_heat_GJ-recoverable_heat_GJ)
    # Screening carbon storage proxy; not lifecycle-certified or creditable.
    gross_stored_co2 = char*x.char_carbon_fraction*x.stable_carbon_fraction*(44/12)
    net_removal_proxy = gross_stored_co2-x.lifecycle_emissions_tco2e_y
    feed_c = dry*x.feed_carbon_fraction_dry
    char_c = char*x.char_carbon_fraction
    retained = char_c/feed_c if feed_c > 0 else float("inf")
    return {
        "feed_carbon_t_y":feed_c,"char_carbon_t_y":char_c,"carbon_retained_fraction":retained,
        "carbon_balance_ok":bool(retained <= 1.0),"reaction_heat_GJ_y":reaction_heat,
        "water_property_source":(w["source"] if (x.use_steam_tables or x.process_type=="htc") else "user constants"),"slurry_water_t_y":slurry_water,"process_type":x.process_type,
        "wet_feed_t_y":wet,"dry_feed_t_y":dry,"feed_water_t_y":water_in,
        "char_t_y":char,"liquid_t_y":liquid,"gas_t_y":gas,"other_t_y":other,
        "mass_balance_residual_t_y":dry-(char+liquid+gas+other),
        "water_sensible_GJ_y":water_sensible,"water_vaporisation_GJ_y":water_vap,
        "steam_superheat_GJ_y":steam_superheat,"solids_sensible_GJ_y":solids_sensible,
        "useful_process_heat_GJ_y":useful_process_heat_GJ,"gross_heat_duty_GJ_y":gross_heat_GJ,
        "purchased_heat_requirement_GJ_y":purchased_heat_GJ,
        "coproduct_chemical_energy_GJ_y":coproduct_chemical_GJ,"liquid_to_heat_energy_GJ_y":liquid_to_heat_GJ,
        "recoverable_coproduct_heat_GJ_y":recoverable_heat_GJ,
        "heat_surplus_GJ_y":heat_surplus_GJ,"heat_deficit_GJ_y":heat_deficit_GJ,
        "gross_stored_co2_t_y":gross_stored_co2,"net_removal_proxy_tco2e_y":net_removal_proxy,
        "model_ids":["MASS-001","ENERGY-001","PYRO-001"]
    }

def calculate_economics(t: dict[str,Any], p: ProcessInputs, e: EconomicInputs) -> dict[str,Any]:
    if e.project_life_y <= 0: raise ValueError("Project life must be positive.")
    if not 0 <= e.discount_rate < 1: raise ValueError("Discount rate must be in [0, 1).")
    crf = (e.discount_rate*(1+e.discount_rate)**e.project_life_y /
           ((1+e.discount_rate)**e.project_life_y-1)) if e.discount_rate else 1/e.project_life_y
    annualised_capex=e.capex_usd*crf*e.annualisation_fraction
    feed_cost=t["wet_feed_t_y"]*(e.feedstock_cost_usd_t_wet+e.logistics_cost_usd_t_wet)
    electricity_use=t["dry_feed_t_y"]*e.electricity_use_kwh_t_dry
    electricity_cost=electricity_use*e.electricity_price_usd_kwh
    heat_cost=t["heat_deficit_GJ_y"]*e.purchased_heat_price_usd_GJ
    maintenance=e.capex_usd*e.maintenance_fraction_capex_y
    operating_cost=feed_cost+electricity_cost+heat_cost+e.labour_usd_y+maintenance+e.other_opex_usd_y
    char_revenue=t["char_t_y"]*e.char_price_usd_t
    liquid_revenue=t["liquid_t_y"]*(1-p.liquid_to_heat_fraction)*e.liquid_price_usd_t
    export_electricity_kwh=t["heat_surplus_GJ_y"]*277.7777778*e.electricity_conversion_efficiency*e.electricity_export_fraction_of_surplus
    electricity_revenue=export_electricity_kwh*e.electricity_price_usd_kwh
    carbon_revenue=max(0.0,t["net_removal_proxy_tco2e_y"])*e.carbon_credit_usd_tco2e
    revenue=char_revenue+liquid_revenue+electricity_revenue+carbon_revenue
    ebitda_like=revenue-operating_cost
    annual_economic_surplus=ebitda_like-annualised_capex
    cashflows=[-e.capex_usd]+[ebitda_like]*e.project_life_y
    npv=sum(cf/((1+e.discount_rate)**i) for i,cf in enumerate(cashflows)) if e.discount_rate else sum(cashflows)
    # IRR calculated only where a conventional sign-changing cashflow exists.
    irr=None
    if any(v>0 for v in cashflows[1:]) and cashflows[0]<0:
        lo,hi=-0.99,5.0
        def npv_at(r): return sum(cf/((1+r)**i) for i,cf in enumerate(cashflows))
        if npv_at(lo)*npv_at(hi)<=0:
            for _ in range(200):
                mid=(lo+hi)/2
                if npv_at(lo)*npv_at(mid)<=0: hi=mid
                else: lo=mid
            irr=(lo+hi)/2
    payback=e.capex_usd/ebitda_like if ebitda_like>0 else None
    return {
        "annualised_capex_usd_y":annualised_capex,"feedstock_logistics_cost_usd_y":feed_cost,
        "electricity_cost_usd_y":electricity_cost,"purchased_heat_cost_usd_y":heat_cost,
        "maintenance_usd_y":maintenance,"labour_usd_y":e.labour_usd_y,
        "other_opex_usd_y":e.other_opex_usd_y,"operating_cost_usd_y":operating_cost,
        "char_revenue_usd_y":char_revenue,"liquid_revenue_usd_y":liquid_revenue,
        "electricity_revenue_usd_y":electricity_revenue,"carbon_revenue_usd_y":carbon_revenue,"total_revenue_usd_y":revenue,
        "ebitda_like_usd_y":ebitda_like,"annual_economic_surplus_usd_y":annual_economic_surplus,
        "npv_usd":npv,"irr":irr,"simple_payback_y":payback,"crf":crf,
        "model_ids":["ECON-001"]
    }

def evaluate_scenario(name: str, p: ProcessInputs, e: EconomicInputs):
    tech=calculate_technical(p)
    econ=calculate_economics(tech,p,e)
    return {"scenario":name,**tech,**econ}

def pareto_front(rows, maximize=("annual_economic_surplus_usd_y","net_removal_proxy_tco2e_y")):
    kept=[]
    for i,a in enumerate(rows):
        dominated=False
        for j,b in enumerate(rows):
            if i==j: continue
            no_worse=all(b[k]>=a[k] for k in maximize)
            strictly=any(b[k]>a[k] for k in maximize)
            if no_worse and strictly:
                dominated=True; break
        if not dominated: kept.append(a)
    return kept
