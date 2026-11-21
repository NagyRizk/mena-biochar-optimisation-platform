# MENA Biochar Engineering Platform (v4)

Pages: **Executive dashboard** · **Rough estimates** (trained predictors) · **Technical** (balances, thermodynamics, particle heat transfer and kinetics) · **Economic** · **Optimize**.
Every page has a **Mathematical model** tab (equations), a **Calculation log** tab (every step with inputs and sources) and an AI analyst panel.

Processes: slow pyrolysis (data-driven), fast pyrolysis, torrefaction, gasification, hydrothermal carbonisation (HTC / wet pyrolysis). Only slow pyrolysis is modelled from the dataset; the others use published typical product splits (Bridgwater 2012) or screening lines, flagged as such.

## AI analyst
Groq API (OpenAI-compatible). Key in the sidebar, `.streamlit/secrets.toml` (`GROQ_API_KEY = "..."`) or the `GROQ_API_KEY` environment variable. Never commit a key.

## Run
```powershell
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
pytest -q
```
See CHANGELOG.md and docs/VALIDATION_ROADMAP.md.


## Engineering model documentation

See [`docs/TECHNICAL_MODEL_REFERENCE.md`](docs/TECHNICAL_MODEL_REFERENCE.md) for the governing equations, variable definitions, units, assumptions, numerical methods, validity domains and limitations for the mass/energy balances, particle heat-transfer model, one-step devolatilisation kinetics, data-driven predictor, carbon screen, economics and optimiser.

The platform's particle kinetics are a single global first-order model; they are not a detailed multi-reaction biomass chemistry model. Read the validity warnings before using calculated conversion times as design constraints.

## Tests

Run `pytest -q` from the project root.
