# Technical audit and correction log — v4.3.0

## Scope

This release is a correction and audit pass over the existing application. It does not add product features. It checks code paths, equations, unit handling, input validation, optimisation semantics, and test coverage. The platform remains a screening model, not a validated plant design package or digital twin.

## Corrections made

1. **Non-finite input validation.** `NaN` and infinity can bypass ordinary `<` / `>` validation. Process and economic numeric inputs are now checked for finiteness before calculations.
2. **Atmospheric evaporation boundary.** The non-HTC water-duty calculation explicitly assumes evaporation at approximately 1 atm. Sub-boiling reactor temperatures are rejected rather than assigning a latent-heat duty at a physically inconsistent temperature. HTC remains on a separate liquid-water path.
3. **Carbon conservation diagnostic.** The code now returns the carbon residual (feed carbon minus char carbon) and evaluates feasibility with a numerical tolerance. This is a necessary check, not a complete species-resolved carbon balance.
4. **Heat-to-power allocation.** Heat allocated to electricity generation is deducted from residual surplus heat. Electricity output is computed from the thermal input multiplied by conversion efficiency. This prevents the same surplus heat from being presented as both exported power and remaining heat.
5. **Economic and process input checks.** Non-finite and negative cost/price inputs are rejected; annualisation, export fraction and conversion efficiency are range-checked; unsupported process names and non-integer project lives are rejected.
6. **Model claims clarified.** The finite grid is not a global optimiser. Carbon permanence and lifecycle calculations remain explicit screening proxies; the numerical H/C-to-stability interpolation is not a validated BC+100 model and cannot support verified credit revenue.

## Verification performed

- Full existing test suite plus new regression tests: **42 passed**.
- Python module compilation: performed during packaging.
- ZIP integrity: checked after packaging.
- Tests cover dry-basis mass closure, product split validation, NaN rejection, sub-boiling boundary, heat recovery, electricity allocation, carbon feasibility, economics relationships, particle conduction verification, predictor grouped-CV strategy and process grid behaviour.

## Important unresolved model limitations

These are not hidden or represented as solved by this release:

- **Product yields:** slow-pyrolysis yields are ML estimates from heterogeneous literature observations. On the bundled data, publication-grouped five-fold CV gave Yield R²=0.376 (MAE=7.50 percentage points; n=460; 52 papers), H/C R²=0.511 (MAE=0.152; n=1,006; 97 papers). For char C, the feedstock-class mean baseline (R²=0.425) slightly outperformed the forest (R²=0.414); for Ash, the class-mean baseline (R²=0.447) outperformed the forest (R²=0.363). The platform therefore uses the baseline for C and Ash. These are internal cross-validation metrics, not independent external validation. Grouped CV is a statistical check, not reactor validation. Fast pyrolysis, torrefaction and gasification use simplified literature anchors; HTC uses a screening interpolation.
- **Thermal duty:** solids heat capacity, heat loss, heating efficiency, gas/liquid LHV and recovery fraction remain user assumptions or defaults. The model omits detailed dryer/reactor/combustor heat integration, flue-gas composition, heat exchanger approach temperatures, pressure drop and auxiliary thermal loads.
- **HTC:** no pressure-vessel design, pressure-work, process-water chemistry, wastewater treatment, or validated yield kinetics.
- **Particle model:** one-dimensional sphere, assumed properties and lumped boundary coefficient; one-step beech-wood kinetics are extrapolated outside 573–708 K and to other feedstocks. No bed-scale transport, shrinkage, internal gas pressure or secondary reactions.
- **Carbon:** the H/C-to-stability map is a placeholder. Lifecycle emissions default to zero unless entered. Feedstock counterfactual, methane/N2O, transport, auxiliary energy, application, reversal and monitoring are not comprehensively modelled. Carbon revenue is therefore illustrative only.
- **Economics:** CAPEX, feedstock prices, logistics, product prices, labour, utilities and maintenance are scenario assumptions. NPV uses level annual EBITDA-like cash flows and omits taxes, financing structure, working capital, escalation, ramp-up, replacement capital, salvage and decommissioning. Results are not investment-grade TEA.
- **Optimisation:** results are only best/non-dominated among the enumerated candidates. Grid resolution can miss an optimum between points. The Pareto set inherits every uncertainty and domain limitation of the underlying models.
- **Market evidence:** evidence scores describe traceability/strength of supporting evidence, not market size, sales, willingness to pay, or profitability.

## Recommended validation before external investment use

1. Replace feedstock presets with measured moisture, ultimate/proximate analysis, ash and bulk density for each supply region.
2. Obtain supplier quotations and site-specific installed CAPEX/OPEX, utility tariffs, labour, logistics and offtake contracts, all dated and currency-normalised.
3. Run representative feedstock trials and reconcile measured product yields, gas composition, char elemental analysis, energy consumption and emissions.
4. Replace permanence proxy with the current applicable methodology calculation (e.g. current Verra methodology/IPCC 2019 Refinement or applicable EBC protocol) and a complete, documented project LCA/MRV boundary.
5. Validate the particle model against measured internal particle temperatures and conversion profiles; independently validate kinetics for each feedstock family.
6. Conduct grid-refinement tests and compare the Pareto set at multiple step sizes; report sensitivity and uncertainty rather than a single deterministic optimum.
7. Independently review the model and sign off all assumptions before using outputs for procurement, permitting, guarantees or investment decisions.

## Reference notes

- IAPWS water/steam formulations: https://iapws.org/technical-guidance/newform
- CoolProp IF97 documentation: https://coolprop.org/fluid_properties/IF97.html
- NIST Chemistry WebBook, water: https://webbook.nist.gov/cgi/cbook.cgi?Name=water
- Verra biochar methodology FAQs (scope, production, end-use and GHG accounting): https://verra.org/methodologies-main/biochar-methodology-faqs/
- EBC Carbon Sink Guidelines, Version 2 (2021): https://www.european-biochar.org/media/doc/26/c-sink_en_version2_0.pdf
- Di Blasi (2008), biomass pyrolysis modelling review: https://doi.org/10.1016/j.pecs.2006.12.001
- Di Blasi & Branca (2001), primary product formation kinetics: https://doi.org/10.1021/ie000997e
