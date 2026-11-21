# Platform information architecture — v4.0.3

## Executive dashboard — research-derived findings
The dashboard is an aggregation and interpretation layer for findings extracted from source material. It presents feedstock performance, conversion conditions, biochar quality, process/design implications, and commercial evidence where the underlying records support those claims. Source records remain linked to their DOI and experimental conditions. It must not present paper counts or research-theme counts as the primary content.

The currently bundled structured experimental dataset (April 2024) contains feedstock names/classes, conversion type, HTT, residence duration, heating rate and selected biochar properties. It does **not** contain comparable plant CAPEX/OPEX, market prices, Egypt-wide feedstock availability, supplier quotations or a complete legal register. The dashboard explicitly identifies these gaps rather than manufacturing commercial conclusions. A separate source-backed economics/market dataset must be populated before economic findings can be aggregated.

## Rough estimates
Data-driven screening from the publication dataset, including model validation and uncertainty caveats.

## Technical
Engineering calculation workspace: mass and carbon balances, thermodynamic duty, coproduct energy, particle heat transfer/kinetics, calculation log, assumptions, equations and solver verification. Results are screening-level where noted in the model registry.

## Economic
Financial model and cash-flow analysis based on explicit user-editable assumptions. Current cash flow remains simplified and is not a bankable feasibility study. Scenario inputs must be distinguished from literature-verified costs and prices.

## Optimize
Grid-based design search using the technical and economic models, with feasibility filters and Pareto comparison.

## AI analyst
The Technical analyst explains current scenario calculations, equations and logs. It is not an independent numerical solver and must not invent missing inputs or validation.
