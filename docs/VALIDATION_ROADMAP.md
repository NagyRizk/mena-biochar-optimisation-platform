# Engineering validation roadmap

## Stage 0 — data-driven layer (new in v2)
- Re-verify the biochar, BECCS and A/R rows of the pathway table against IPCC AR6 WGIII Table 12.6.
- Replace the PERM-001 placeholder map with a published BC+100 regression.
- Add feedstock-specific proximate/ultimate inputs (ash, volatile matter) to the predictor; feedstock class alone explains little of carbon and ash.
- Validate predictions against at least one independent Egyptian or regional pyrolysis dataset.
- Replace placeholder feedstock costs and add sourced availability volumes.

## Stage 1 — balances
- Verify dry-basis mass balance against hand calculations.
- Verify moisture and drying duty against independent calculations.
- Add property tables with explicit temperature ranges and references.
- Add unit tests for unit conversions and limiting cases.

## Stage 2 — process-specific models
- Select one reactor geometry and operating mode.
- Obtain feedstock proximate/ultimate analysis and particle-size distribution.
- Select kinetic scheme from literature and identify its validity domain.
- Calibrate against independent experimental yield and temperature-profile data.
- Keep calibration data separate from validation data.

- Define the physical domain and generate mesh.
- Document mesh quality and mesh-independence study.
- Select solver based on the actual flow, heat-transfer, multiphase and reaction physics.
- Define material properties, boundary/initial conditions and reaction source terms.
- Establish residual, conservation and time-step convergence criteria.
- Validate against published or measured temperature, pressure-drop, residence-time and composition data.
- Archive case dictionaries, solver version, mesh, logs and post-processing outputs.

## Stage 4 — economics
- Obtain vendor budgetary quotations with date, currency, scope and delivery basis.
- Build equipment-level CAPEX and installation factors.
- Add site-specific utility tariffs, labour, feedstock logistics and product offtake.
- Add taxes, debt, working capital, escalation and replacement costs before investment-grade NPV/IRR.
- Sensitivity and uncertainty analysis on dominant assumptions.

## Stage 5 — optimisation
- Only optimise within validated model domains.
- Encode technical feasibility constraints before ranking economics.
- Report Pareto alternatives and trade-offs, not one unsupported universal optimum.
