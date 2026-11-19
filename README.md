# MENA Biochar Feedstock-to-Market Platform

Streamlit decision-support interface for the supplied V5 notebook. It includes an executive dashboard, technical calculation trace, application screening gates, Pareto optimisation, deterministic sensitivity analysis, and an optional Groq narrative analyst.

## Start on Windows

The easiest method is to extract the ZIP and double-click `RUN_PLATFORM.bat`. It creates a Python 3.11 virtual environment, installs dependencies, and launches the app. Open `http://localhost:8501` if the browser does not open automatically. See `RUN_ME_FIRST.md`.

## Groq setup (optional)

You do **not** need to find a Settings page to use the app. Open the **AI analyst** page in the running app and paste a newly rotated Groq API key into the password field. It is held only in the current Streamlit session and is not written to disk. The app works without Groq. For a persistent cloud deployment, configure the key in the hosting provider's server-side secret manager.

A key previously pasted into a chat should be considered exposed: revoke it and generate a new one before use. Never commit a key to Git or place it in the notebook/source files.

## Included workspaces

- Executive dashboard: annual margin, screening removal proxy, throughput, and scenario comparison.
- Technical analysis: mass, cost, revenue, and application gate trace.
- Optimisation: Pareto set for annual margin and screening net removal.
- Sensitivity: deterministic grid for feedstock cost, CAPEX, and energy demand.
- AI analyst: optional narrative explanation of structured platform outputs.

## Scientific and commercial boundaries

This is a transparent screening prototype, not a bankable feasibility study, process guarantee, certification engine, or carbon-credit calculator. Country prices/costs, process yields, energy demand, CAPEX, market demand and stable-carbon fractions are editable notebook placeholders until replaced by local quotations, measured plant data and verified LCA/MRV inputs. Net removal is a simplified screening proxy, not verified or creditable removal. Carbon-credit revenue remains disabled. Application gates are screening only and do not establish certification.

The calculation engine follows the core scenario equations and assumptions in `reference/MENA_Biochar_Optimisation_Platform_V5.ipynb`. The separate coproduct workbook model is slow-pyrolysis-specific and is not treated as a generic energy model here. Research ML results are not used to generate plant guarantees or optimise project economics.

## Run manually

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

## Tests

```powershell
pytest -q
```

## Cloud deployment

Deploy `app.py` from a private Git repository to Streamlit Community Cloud or a managed container host. Set `GROQ_API_KEY` as a server-side secret if you want a persistent deployment key. Do not upload `.env`, `.streamlit/secrets.toml`, or API keys to the repository. For container deployment, see `DEPLOYMENT.md`.

## Before operational use

1. Replace every placeholder with traceable local project data and provenance.
2. Validate mass/energy balances and equipment guarantees with vendors and engineering design.
3. Add authentication, authorisation, project persistence and audit logging before multi-user deployment.
4. Validate all regulatory/product routes with accredited laboratories and jurisdiction-specific requirements.
5. Complete an independently reviewed LCA/MRV and applicable methodology assessment before any CDR claim.
