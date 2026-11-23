## 4.2.7 — Model Library display-math rendering fix

- Fixed the technical-reference tabs: display equations written with `\[ ... \]` are now extracted and sent to `st.latex()` instead of being passed through Markdown as literal text.
- Converted inline `\( ... \)` expressions to Streamlit-supported `$ ... $` delimiters before Markdown rendering.
- Kept prose, headings, lists, and citations in Markdown; equations are rendered separately.
- Added regression coverage for the Model Library renderer and reference delimiters.

# Changelog

## v4.2.0 - flow diagram and carbon credits
- Process > Flow diagram: animated process flow (stream widths follow t/y and GJ/y), heat self-sufficiency badge, mass Sankey and new process-heat Sankey (engine/flows.py).
- Economics > Carbon credits: CO2 removed per year, credit revenue, net of registry/MRV, per tonne biochar, break-even price, price sweep; one click applies the effective price to the model (engine/carbon.py).
- Overview shows credits and credit revenue. Added tests/test_v41.py with independent hand calculations (34 tests pass).

## v4.1.0 - 3D structure viewer and guided workflow
- New 3D biochar structure viewer (Biochar step): atomic turbostratic lattice and porous particle section, driven by predicted H/C, temperature, ash and feedstock class. Offline three.js, stylised not simulated. Optional 400/600/800 C comparison.
- New engine/structure.py (structure descriptors and generators) and viz3d.py + static/biochar3d component.
- Navigation rebuilt as a numbered flow: Overview, 1 Evidence, 2 Biochar, 3 Process, 4 Economics, 5 Optimize, with clickable stepper, Back/Next buttons and quick-start presets.
- One shared scenario in the sidebar replaces duplicated controls; optimizer results apply back to it.
- Audit material (logs, equations, assumptions, verification) grouped into one Audit tab per page.

## v4.0.0
- CFD removed (adapter, gating, tests, UI). The particle model remains and is labelled as reduced-order.
- New process inputs: fast pyrolysis, torrefaction, gasification, HTC (steam-free slurry energy balance with heat recovery). Optimizer can compare processes.
- Mathematical model tab and calculation log on every page. New UI: KPI cards, check chips, cleaner navigation.

## v3.0.0
- **Bug fix (affects v1 and v2 results):** useful process heat and co-product chemical energy totals were divided by 1000 twice, so absolute heat duties, purchased-heat cost and exported-electricity revenue were 1000x too small (signs of deficit/surplus were unaffected). Fixed, with a hand-calculation regression test. Any v2 economics for wet feedstocks were optimistic.
- Pages restructured: Executive dashboard, Rough estimates, Technical, Economic, Optimize. AI analyst (Groq) on every page.
- Optimize now enforces technical constraints (particle conversion time, carbon balance) alongside H/C and adds objective choice and breakeven carbon price.
- UI redesign; API keys are never stored in the repo (sidebar, st.secrets or GROQ_API_KEY).


## 4.0.1 — engineering audit fixes
- Carbon-credit revenue defaults to zero unless explicitly selected as a scenario.
- Undefined IRR is displayed as N/A rather than 0%.
- Separated liquid coproduct diversion to process heat from the saleable liquid fraction to avoid double counting.
- Random-forest inference now falls back to the feedstock-class mean when that baseline outperforms the forest in publication-grouped cross-validation.
- Added an explicit warning when the beech-wood kinetic parameters are used outside their 573–708 K fit range.
- Added a technical model reference documenting equations, units, assumptions, numerical methods and applicability limits.
- Added regression tests for coproduct allocation, validation and predictor model selection.


## 4.0.2 — dashboard and engineering transparency redesign
- Executive dashboard is now a literature-evidence overview; removed duplicated live technical, financial and optimiser outputs.
- Dashboard explicitly identifies the scope and limitations of the bundled April 2024 literature datasets and lists Egypt-specific evidence gaps rather than implying that market/supplier/regulatory research is already present.
- Technical calculation log now exposes more numerical substitutions and model inputs alongside equations, results, units and model/source labels.
- Technical AI analyst receives the governing equations and calculation log; revised prompt requires step-by-step engineering interpretation, drivers, assumptions and limitations, with a larger response budget.

## 4.0.3 — Executive dashboard corrected to aggregate findings
- Replaced paper/database-count reporting with source-linked aggregation of experimental findings: feedstock yield and quality, operating conditions, temperature/property trends, and process/design implications.
- Added filters for conversion route and feedstock family, feedstock comparison tables, distributions, and DOI-linked experimental records.
- Added an explicit commercial evidence section explaining that the bundled structured dataset does not contain comparable CAPEX/OPEX, market prices, Egypt-wide feedstock supply, supplier quotations or a complete regulatory register. These are not fabricated or inferred from paper counts.
- Kept scenario calculations and financial modelling in their dedicated Technical and Economic modules.

## 4.0.4 — technical and economic UI workflow
- Reframed Technical and Economic page descriptions around the questions each module answers.
- Added short step-by-step guidance and numbered navigation tabs so users can follow the analysis in sequence.
- Clarified what each mass-balance, heat-duty, particle-model, cash-flow, cost-driver and sensitivity view is intended to show.
- Renamed input expanders to distinguish editable scenario inputs from results and audit material.
- Preserved the calculation engine, equations, calculation logs, model references, sensitivity calculations and verification routines.


## 4.0.5 — Optimizer redesign
- Restricted the optimizer to slow pyrolysis; other routes remain excluded until process-specific, comparable yield/quality/energy/economic models exist.
- Reframed the page around design basis, decision variables, feasibility constraints, objectives, candidate comparison, and model scope.
- Added NPV as the default selectable objective, alongside annual economic surplus, net-removal proxy, and break-even carbon price.
- Added user-visible candidate grid ranges, a comparison table, selection rationale, and explicit assumptions/limitations.
- Corrected particle conversion screening to use each candidate's predicted char fraction rather than a single fixed value.
- Added explicit warning for particle-kinetics use outside the cited 300–435 °C fit range.
- Updated optimization model documentation and calculation log.

## v4.2.1 — cited numerical assumptions and ground cases
- Added a Case Studies page with condition-matched model-vs-literature comparisons for rice husk and corn stover, plus rice-straw and pilot-plant energy benchmarks.
- Added a numerical provenance register for model constants, defaults, process anchors, economic assumptions and scenario-only values.
- Added citations/qualifications and explicit cautions against treating literature comparisons as independent validation.

## v4.2.2 — expanded mathematical citations

- Added equation-level model citation matrix covering mass/energy balances, water properties, particle conduction and kinetics, ML, carbon accounting, economics, Pareto screening, and process-specific anchors.
- Added uploaded 122-record bibliography to `data/reference_bibliography_uploaded.csv` and a curated relevance crosswalk.
- Corrected technical model reference version label to v4.2.2.
- Explicitly separated governing-equation sources, parameter sources, software citations, experimental evidence, numerical verification and assumptions.
- Clarified that torrefaction/gasification splits, HTC interpolation, particle properties, lifecycle emissions and several economic defaults remain placeholders rather than cited empirical constants.


## v4.2.3 — Model Library and navigation

- Added a dedicated **Model Library** navigation page, separate from scenario controls.
- Split technical equations and economic equations into directly accessible sections.
- Added searchable, downloadable equation-to-source and numerical-assumption registers.
- Added guidance distinguishing governing-equation citations, parameter provenance, numerical-method references, calibration and validation evidence.
- Updated technical reference release label.

## v4.2.4 — MENA feedstock evidence

- Added a searchable MENA feedstock evidence register covering Egypt collection-cost benchmarks and Saudi/UAE date-palm/date-pit techno-economic studies.
- Added a dedicated Model Library tab explaining purchase, collection, baling, handling, transport and delivered-cost boundaries.
- Explicitly labelled legacy optimiser feedstock cost presets as provisional placeholders, not market prices. They remain unchanged until comparable, project-specific procurement evidence is available.
- Distinguished date pits from date-palm prunings and mixed date-palm waste.

## 4.2.5 — MENA Market Opportunity & Project Value
- Added dedicated Market & Value navigation page.
- Added sourced MENA/MEA market-needs evidence register with limitations and URLs.
- Added qualitative feedstock × application evidence-fit heatmap; explicitly not a demand forecast.
- Added platform value proposition and carefully qualified case-study counterfactuals.
- Added downloadable CSV registers for market evidence and heatmap evidence.

## 4.2.6 — Model Library LaTeX repair
- Corrected double-escaped LaTeX commands in the optimisation equations and economic equation summary.
- Added a regression test to reject doubled command escapes in equation strings.
