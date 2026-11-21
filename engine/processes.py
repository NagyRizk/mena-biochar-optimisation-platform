"""Thermochemical process types offered as inputs.

Slow pyrolysis is data-driven (ML-001, trained on the bundled dataset). The other processes use
published typical product splits (Bridgwater 2012, dry wood basis) for yields; char quality for
fast pyrolysis / torrefaction / gasification is taken from the same slow-pyrolysis predictor at the
process temperature (an extrapolation in heating rate and mode, flagged). HTC has no model in the
dataset: its yield and char-property lines are screening interpolations flagged as such.
"""

PROCESSES = {
    "slow_pyrolysis": {
        "label": "Slow pyrolysis", "T": (300, 800), "T_default": 540, "T_step": 20, "dur_default": 120.0, "dur_options": (15, 30, 60, 120, 240),
        "yields": "ml", "wet_ok": False, "particle": "full", "particle_defaults": {"d": 20.0, "h": 50.0}, "liquid_price_usd_t": None,
        "desc": "Dry biomass heated slowly (minutes to hours) in the absence of oxygen. Main product: biochar. Yields and char properties predicted from literature data (ML-001).",
        "status": "Data-driven (grouped-CV skill: modest).", "yield_source": "ML-001"},
    "fast_pyrolysis": {
        "label": "Fast pyrolysis", "T": (450, 600), "T_default": 500, "T_step": 25, "dur_default": 0.17, "dur_options": None,
        "yields": "table", "anchors": {"liquid": 0.75, "char": 0.12, "gas": 0.13}, "wet_ok": False, "max_moisture": 0.10, "particle": "full",
        "particle_defaults": {"d": 2.0, "h": 300.0}, "liquid_price_usd_t": None,
        "desc": "Very fast heating of small particles, vapours quenched within about 2 s. Main product: bio-oil, char as by-product. Feed must be dried to about 10% water.",
        "status": "Typical yields (Bridgwater 2012, wood); char quality extrapolated from the slow-pyrolysis predictor.", "yield_source": "Bridgwater 2012"},
    "torrefaction": {
        "label": "Torrefaction", "T": (250, 320), "T_default": 290, "T_step": 10, "dur_default": 30.0, "dur_options": None,
        "yields": "table", "anchors": {"liquid": 0.0, "char": 0.80, "gas": 0.20}, "wet_ok": False, "particle": "heatup",
        "particle_defaults": {"d": 20.0, "h": 50.0}, "liquid_price_usd_t": 0.0,
        "desc": "Mild thermal treatment (about 250-320 C). Product is a dry, brittle solid fuel, not a stable biochar: expect low carbon permanence.",
        "status": "Typical yields (Bridgwater 2012, wood); char quality extrapolated from the slow-pyrolysis predictor.", "yield_source": "Bridgwater 2012"},
    "gasification": {
        "label": "Gasification", "T": (750, 900), "T_default": 800, "T_step": 25, "dur_default": 30.0, "dur_options": None,
        "yields": "table", "anchors": {"liquid": 0.05, "char": 0.10, "gas": 0.85}, "wet_ok": False, "particle": "heatup",
        "particle_defaults": {"d": 10.0, "h": 100.0}, "liquid_price_usd_t": 0.0,
        "desc": "High-temperature conversion with a limited oxidant to a combustible gas; char is a minor by-product. Oxidant demand and gas cleaning are not modelled.",
        "status": "Typical yields (Bridgwater 2012, wood); char quality extrapolated from the slow-pyrolysis predictor; char gasification kinetics not modelled.", "yield_source": "Bridgwater 2012"},
    "htc": {
        "label": "Hydrothermal carbonisation (wet pyrolysis)", "T": (180, 260), "T_default": 220, "T_step": 10, "dur_default": 60.0, "dur_options": None,
        "yields": "htc", "wet_ok": True, "particle": "none", "particle_defaults": {"d": 20.0, "h": 500.0}, "liquid_price_usd_t": 0.0,
        "desc": "Biomass in hot compressed water (about 180-260 C, 2-10 MPa), no drying needed. Product: hydrochar plus process water. Hydrochar carbon is usually less stable than pyrolysis char.",
        "status": "Screening only: yield line interpolated between the reported 35-65% range; char properties are unsourced typical values.", "yield_source": "interpolation"},
}

# HTC screening lines (assumption): endpoints of the reported hydrochar yield range (35-65 wt%) mapped to 260 C and 180 C.
def htc_properties(T_C: float) -> dict:
    x = min(max((T_C - 180.0) / 80.0, 0.0), 1.0)
    return {"char": 0.65 - 0.30 * x, "gas": 0.05, "C": 0.55 + 0.10 * x, "H_C": 1.10 - 0.20 * x}
