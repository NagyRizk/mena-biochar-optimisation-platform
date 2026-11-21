"""Carbon dioxide removal pathway comparison (indicative global ranges, IPCC AR6 WGIII Ch.12)."""
import pandas as pd

SRC = "IPCC AR6 WGIII Ch.12, Table 12.6 (Babiker, Berndes et al., 2022)"
# verified=True: figures re-checked against the chapter text during this build.
# verified=False: recalled from the same table; confirm before citing in the final deliverable.
PATHWAYS = [
    # name, cost_low, cost_high, pot_low, pot_high (GtCO2/yr), permanence, MENA angle, verified
    ("Biochar", 10, 345, 0.3, 6.6, "Centuries (depends on H/C)", "Agri-residues (palm, rice straw, bagasse) + solar-rich, low-water process", False),
    ("BECCS", 15, 400, 0.5, 11.0, "Millennia (geological)", "Needs dedicated biomass + CO2 storage infrastructure", False),
    ("Afforestation / reforestation", 0, 240, 0.5, 10.1, "Decades to centuries", "Constrained by arid land and water", False),
    ("Direct air capture + storage", 100, 300, 5.0, 40.0, "Millennia (geological)", "Abundant solar and storage sites; very energy-intensive", True),
    ("Enhanced weathering", 50, 200, 2.0, 4.0, "Millennia", "Needs suitable mafic rock and spreading logistics", True),
]

def pathways_df() -> pd.DataFrame:
    return pd.DataFrame(PATHWAYS, columns=["Pathway", "Cost low (USD/tCO2)", "Cost high (USD/tCO2)",
                                           "Potential low (GtCO2/yr)", "Potential high (GtCO2/yr)",
                                           "Permanence", "MENA angle", "Figures re-verified"])
