"""Mass and energy flow tables derived from calculate_technical() output (no new physics)."""
from __future__ import annotations


def mass_flows(t: dict) -> list[tuple[str, str, float]]:
    """(source, target, t/y). Dry feed splits into products; feed water leaves separately."""
    L = [("Wet feed", "Feed water", t["feed_water_t_y"]), ("Wet feed", "Dry feed", t["dry_feed_t_y"]),
         ("Dry feed", "Biochar", t["char_t_y"]), ("Dry feed", "Bio-oil", t["liquid_t_y"]), ("Dry feed", "Syngas", t["gas_t_y"]), ("Dry feed", "Other / losses", t["other_t_y"])]
    return [x for x in L if x[2] > 1e-9]


def energy_flows(t: dict, p) -> dict:
    """Process-heat flows in GJ/y in the same terms as the engine: requirement (fuel basis) = purchased_heat_requirement,
    supply = recoverable co-product heat + external heat for any deficit."""
    gas_chem = t["gas_t_y"] * p.gas_lhv_MJ_kg
    oil_chem = t["liquid_to_heat_energy_GJ_y"]
    f = p.recoverable_coproduct_heat_fraction
    rec_gas, rec_oil = gas_chem * f, oil_chem * f
    req = t["purchased_heat_requirement_GJ_y"]
    recovered = rec_gas + rec_oil
    used = min(recovered, req); surplus = max(0.0, recovered - req); external = max(0.0, req - recovered)
    comps = {"Water heating": t["water_sensible_GJ_y"], "Water evaporation": t["water_vaporisation_GJ_y"], "Steam superheat": t["steam_superheat_GJ_y"],
             "Solids heating": t["solids_sensible_GJ_y"], "Reaction heat": t["reaction_heat_GJ_y"]}
    raw = sum(comps.values()); scale = t["useful_process_heat_GJ_y"] / raw if raw else 0.0   # HTC heat recovery scales all terms
    comps = {k: v * scale for k, v in comps.items()}
    comps["Heat losses"] = t["gross_heat_duty_GJ_y"] - t["useful_process_heat_GJ_y"]
    comps["Burner / dryer inefficiency"] = req - t["gross_heat_duty_GJ_y"]
    links = [("Syngas energy", "Recovered heat", rec_gas), ("Syngas energy", "Unrecovered", gas_chem - rec_gas),
             ("Bio-oil energy (diverted)", "Recovered heat", rec_oil), ("Bio-oil energy (diverted)", "Unrecovered", oil_chem - rec_oil),
             ("Recovered heat", "Process requirement", used), ("Recovered heat", "Surplus heat", surplus), ("External heat", "Process requirement", external)]
    links += [("Process requirement", k, v) for k, v in comps.items()]
    links = [l for l in links if l[2] > 1e-9]
    return {"links": links, "requirement": req, "recovered": recovered, "external": external, "surplus": surplus,
            "self_sufficiency": (min(1.0, recovered / req) if req > 0 else 1.0), "gas_chem": gas_chem, "oil_chem": oil_chem,
            "balance_in": used + external, "balance_out": sum(v for k, v in comps.items() if v > 0)}
