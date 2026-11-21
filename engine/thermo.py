"""Water/steam thermodynamics. IAPWS-95 via CoolProp when installed, else constant-cp fallback."""
try:
    from CoolProp.CoolProp import PropsSI
    HAVE_COOLPROP = True
except Exception:  # pragma: no cover
    HAVE_COOLPROP = False

P_ATM = 101325.0

def water_enthalpies(T_in_C: float, T_out_C: float, P: float = P_ATM,
                     cp_w=4.18, cp_v=2.01, hfg=2257.0) -> dict:
    """Specific heat to take liquid water at T_in to steam at T_out, split in three steps (kJ/kg)."""
    if HAVE_COOLPROP:
        Ts = PropsSI("T", "P", P, "Q", 0, "Water") - 273.15
        hf = PropsSI("H", "P", P, "Q", 0, "Water") / 1000
        hg = PropsSI("H", "P", P, "Q", 1, "Water") / 1000
        h_in = PropsSI("H", "T", min(T_in_C, Ts - 0.01) + 273.15, "P", P, "Water") / 1000
        h_out = PropsSI("H", "T", max(T_out_C, Ts + 0.01) + 273.15, "P", P, "Water") / 1000
        return {"sensible": hf - h_in, "latent": hg - hf, "superheat": h_out - hg, "Tsat_C": Ts,
                "source": "IAPWS-95 (CoolProp), 1 atm"}
    return {"sensible": cp_w * (100 - T_in_C), "latent": hfg, "superheat": cp_v * max(0, T_out_C - 100),
            "Tsat_C": 100.0, "source": "constant cp fallback (CoolProp not installed)"}


def liquid_water_heating_kJ_kg(T_in_C: float, T_out_C: float) -> dict:
    """Heat to take liquid water from T_in (1 atm) to saturated liquid at T_out (autogenous pressure), kJ/kg.
    Used for hydrothermal carbonisation, where water never vaporises."""
    if HAVE_COOLPROP:
        h_in = PropsSI("H", "T", T_in_C + 273.15, "Q", 0, "Water") / 1000
        h_out = PropsSI("H", "T", T_out_C + 273.15, "Q", 0, "Water") / 1000
        p_sat = PropsSI("P", "T", T_out_C + 273.15, "Q", 0, "Water") / 1e5
        return {"kJ_kg": h_out - h_in, "P_sat_bar": p_sat, "source": "IAPWS-95 (CoolProp), saturated liquid"}
    return {"kJ_kg": 4.18 * (T_out_C - T_in_C), "P_sat_bar": float("nan"), "source": "constant cp fallback"}
