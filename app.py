import os
import streamlit as st
import pandas as pd
import plotly.express as px

from engine.core import (
    COUNTRY_SCENARIOS, FEEDSTOCKS, TECHNOLOGIES, ROUTES,
    DEFAULT_COUNTRY, DEFAULT_FEEDSTOCK, PLANT_AVAILABILITY, APPLICATION_REQUIREMENTS,
    evaluate_configuration, run_optimisation, application_gate, run_sensitivity
)
from explainability.engine import cost_revenue_breakdown, deterministic_reasons, scenario_comparison, model_validation_warning
from ai.groq_analyst import explain_with_groq

st.set_page_config(page_title="MENA Biochar Platform", page_icon="🌱", layout="wide")
px.defaults.template = "plotly_white"
px.defaults.color_discrete_sequence = ["#176b5b", "#d49a45", "#6d8fba", "#9a78a8", "#6f8580"]
# Streamlit-hosted secrets are copied into the server environment for the AI module.
if "GROQ_API_KEY" not in os.environ:
    try:
        if st.secrets.get("GROQ_API_KEY"):
            os.environ["GROQ_API_KEY"] = str(st.secrets["GROQ_API_KEY"])
        if st.secrets.get("GROQ_MODEL"):
            os.environ["GROQ_MODEL"] = str(st.secrets["GROQ_MODEL"])
    except Exception:
        pass
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700;800&display=swap');
:root { --ink:#172b2a; --muted:#687b78; --green:#176b5b; --green2:#e7f1ed; --line:#e2e9e6; --paper:#f5f8f6; }
html, body, [class*="css"] { font-family:'DM Sans',sans-serif; }
.stApp { background:var(--paper); color:var(--ink); }
[data-testid="stHeader"] { background:rgba(245,248,246,.92); }
.block-container { max-width:1480px; padding-top:1.65rem; padding-bottom:3rem; }
h1,h2,h3,h4 { font-family:'Manrope','DM Sans',sans-serif !important; color:var(--ink); letter-spacing:-.035em; }
h1 { font-size:2rem !important; font-weight:800 !important; }
h2 { font-size:1.5rem !important; font-weight:750 !important; }
h3 { font-size:1.08rem !important; font-weight:700 !important; }
p, label, .stCaption { color:#536663; }
[data-testid="stSidebar"] { background:#fff; border-right:1px solid var(--line); }
[data-testid="stSidebar"] > div:first-child { padding-top:1.2rem; }
[data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 { letter-spacing:-.02em; }
[data-testid="stMetric"] { background:#fff; border:1px solid var(--line); border-radius:14px; padding:18px 18px 15px; box-shadow:0 2px 8px rgba(20,55,47,.035); }
[data-testid="stMetricLabel"] { color:var(--muted); font-size:.78rem; font-weight:600; }
[data-testid="stMetricValue"] { color:var(--ink); font-family:'Manrope',sans-serif; font-size:1.65rem; font-weight:800; }
[data-testid="stPlotlyChart"], [data-testid="stDataFrame"], [data-testid="stTable"] { background:#fff; border:1px solid var(--line); border-radius:14px; padding:10px; }
[data-testid="stExpander"] { background:#fff; border:1px solid var(--line); border-radius:12px; margin-bottom:.55rem; }
[data-testid="stExpander"] details summary { font-weight:650; color:var(--ink); }
.stButton > button, .stDownloadButton > button, button[kind="primary"] { border-radius:9px; font-weight:650; min-height:2.65rem; }
.stButton > button[kind="primary"], button[kind="primary"] { background:var(--green); border-color:var(--green); }
.stButton > button:hover { border-color:var(--green); color:var(--green); }
[data-testid="stAlert"] { border-radius:10px; }
[data-testid="stTextInput"] input, [data-testid="stNumberInput"] input, [data-testid="stSelectbox"] div[data-baseweb="select"] { border-radius:8px; }
hr { border-color:var(--line); }
.brandbar { display:flex; align-items:center; gap:13px; padding:8px 0 20px; border-bottom:1px solid var(--line); margin-bottom:26px; }
.brandmark { width:42px; height:42px; border-radius:12px; display:grid; place-items:center; background:#176b5b; color:white; font-size:21px; }
.brandname { font-family:'Manrope',sans-serif; color:#172b2a; font-weight:800; font-size:1.13rem; letter-spacing:-.03em; }
.brandmeta { color:#71827e; font-size:.76rem; margin-top:2px; }
.eyebrow { color:#176b5b; text-transform:uppercase; letter-spacing:.12em; font-size:.68rem; font-weight:800; margin-bottom:6px; }
.pagelead { color:#637571; font-size:.94rem; margin-top:-8px; margin-bottom:20px; max-width:900px; }
.sidebar-note { background:#f1f6f3; border:1px solid #e0ebe5; border-radius:10px; padding:11px 12px; color:#536b63; font-size:.76rem; line-height:1.5; }
[data-testid="stRadio"] label { font-weight:600; }
</style>
<div class="brandbar">
  <div class="brandmark">🌱</div>
  <div><div class="brandname">MENA Biochar Platform</div><div class="brandmeta">FEEDSTOCK → CONVERSION → MARKET · DECISION SUPPORT</div></div>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### Workspace")
    pages = ["Executive dashboard", "Technical", "Optimisation", "Sensitivity", "AI analyst"]
    page = st.radio("Navigate", pages, label_visibility="collapsed")
    st.divider()
    st.markdown("### Scenario inputs")
    country = st.selectbox("Country / market", list(COUNTRY_SCENARIOS), index=list(COUNTRY_SCENARIOS).index(DEFAULT_COUNTRY))
    feedstock = st.selectbox("Feedstock", list(FEEDSTOCKS), index=list(FEEDSTOCKS).index(DEFAULT_FEEDSTOCK))
    feed_tpy = st.number_input("Feedstock received · t/year", min_value=0.0, value=10000.0, step=500.0)
    moisture = st.slider("Moisture · wet basis", 0.0, 0.80, 0.12, 0.01, format="%.0f%%")
    transport_km = st.number_input("One-way transport · km", min_value=0.0, value=60.0, step=5.0)
    availability = st.slider("Plant availability", 0.10, 1.00, float(PLANT_AVAILABILITY), 0.01, format="%.0f%%")
    capex_mult = st.slider("CAPEX multiplier", 0.50, 2.00, 1.00, 0.05)
    energy_mult = st.slider("Energy-demand multiplier", 0.50, 2.00, 1.00, 0.05)

    st.divider()
    selected_tech = st.selectbox("Technology to customise", list(TECHNOLOGIES), index=list(TECHNOLOGIES).index("slow_pyrolysis"))
    base_tech = TECHNOLOGIES[selected_tech]
    st.caption("Changes recalculate the screening outputs automatically.")
    with st.expander("Engineering assumptions", expanded=False):
        custom_tech = {
            "char_yield": st.number_input("Product yield · dry basis", 0.01, 0.95, float(base_tech["char_yield"]), 0.01),
            "process_heat_GJ_t_dry": st.number_input("Process heat · GJ/t dry", 0.0, 20.0, float(base_tech["process_heat_GJ_t_dry"]), 0.1),
            "electricity_kWh_t_dry": st.number_input("Electricity · kWh/t dry", 0.0, 2000.0, float(base_tech["electricity_kWh_t_dry"]), 5.0),
            "capex_usd_per_tpy": st.number_input("Installed CAPEX · USD per t/y", 0.0, 20000.0, float(base_tech["capex_usd_per_tpy"]), 50.0),
            "fixed_opex_fraction": st.number_input("Fixed OPEX / CAPEX", 0.0, 0.5, float(base_tech["fixed_opex_fraction"]), 0.01),
            "char_C_fraction": st.number_input("Product carbon fraction", 0.0, 1.0, float(base_tech["char_C_fraction"]), 0.01),
            "stable_C_fraction": st.number_input("Stable carbon fraction", 0.0, 1.0, float(base_tech["stable_C_fraction"]), 0.01),
        }
    base_market = COUNTRY_SCENARIOS[country].copy()
    market_override = base_market.copy()
    with st.expander("Commercial assumptions · USD", expanded=False):
        market_override["feedstock_gate_usd_t"] = st.number_input("Feedstock purchase · USD/t", 0.0, 5000.0, float(base_market["feedstock_gate_usd_t"]), 1.0)
        market_override["electricity_usd_kwh"] = st.number_input("Electricity · USD/kWh", 0.0, 5.0, float(base_market["electricity_usd_kwh"]), 0.01, format="%.3f")
        market_override["heat_fuel_usd_GJ"] = st.number_input("Thermal energy · USD/GJ", 0.0, 500.0, float(base_market["heat_fuel_usd_GJ"]), 1.0)
        market_override["labour_usd_t_y"] = st.number_input("Labour · USD/t dry", 0.0, 1000.0, float(base_market["labour_usd_t_y"]), 1.0)
        market_override["logistics_usd_t_km"] = st.number_input("Transport · USD/t-km", 0.0, 5.0, float(base_market["logistics_usd_t_km"]), 0.01, format="%.3f")
        market_override["char_price_usd_t"] = st.number_input("Product price · USD/t", 0.0, 10000.0, float(base_market["char_price_usd_t"]), 5.0)
        market_override["demand_char_t_y"] = st.number_input("Annual product demand · t/y", 0.0, 10000000.0, float(base_market["demand_char_t_y"]), 500.0)
    with st.expander("Project finance assumptions", expanded=False):
        discount_rate = st.number_input("Discount rate", 0.0, 0.50, 0.12, 0.005, format="%.3f", help="Used in the capital recovery factor for annualised CAPEX.")
        plant_life_y = st.number_input("Economic plant life · years", 1, 50, 15, 1)
    route_overrides = {}
    with st.expander("Market-route assumptions", expanded=False):
        st.caption("Adjust route processing cost and the fraction of annual demand addressable through each route.")
        for route_name, route_cfg in ROUTES.items():
            st.markdown(f"**{route_name.replace('_', ' ').title()}**")
            rc1, rc2 = st.columns(2)
            route_overrides[route_name] = {
                "route_cost_usd_t": rc1.number_input(f"Route cost · USD/t · {route_name}", 0.0, 5000.0, float(route_cfg["route_cost_usd_t"]), 1.0, key=f"route_cost_{route_name}"),
                "demand_fraction": rc2.number_input(f"Addressable demand fraction · {route_name}", 0.0, 1.0, float(route_cfg["demand_fraction"]), 0.05, key=f"route_demand_{route_name}")
            }
    st.markdown('<div class="sidebar-note">Defaults are illustrative starting assumptions, not live quotations. Replace them with project data and supplier offers before investment decisions.</div>', unsafe_allow_html=True)

tech_overrides = {selected_tech: custom_tech}
results, pareto = run_optimisation(country, feedstock, feed_tpy, moisture, transport_km, availability, capex_mult, energy_mult, market_override=market_override, technology_overrides=tech_overrides, discount_rate=discount_rate, plant_life_y=plant_life_y, route_overrides=route_overrides)


if page == "Executive dashboard":
    st.markdown('<div class="eyebrow">Portfolio overview</div>', unsafe_allow_html=True)
    st.header("Executive decision dashboard")
    st.markdown('<div class="pagelead">A decision-focused summary of production, indicative project economics and carbon-removal screening. Adjust the assumptions in the left panel to test alternative cases.</div>', unsafe_allow_html=True)
    if results.empty:
        st.warning("No feasible configurations were returned for these inputs.")
    else:
        best_margin = results.sort_values("annual_margin_usd_y", ascending=False).iloc[0]
        best_cdr = results.sort_values("net_removal_tCO2py", ascending=False).iloc[0]
        pareto_count = int(results["pareto_optimal"].sum())
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Best annual operating margin", f"${best_margin.annual_margin_usd_y:,.0f}", help="Highest modelled annual revenue minus annual modelled costs.")
        c2.metric("Highest CDR screening estimate", f"{best_cdr.net_removal_tCO2py:,.0f} tCO₂/y", help="Screening proxy only; not verified carbon removal or creditable tonnes.")
        c3.metric("Pareto-efficient options", f"{pareto_count}", help="Options not dominated on both margin and screening removal.")
        c4.metric("Dry feed throughput", f"{best_margin.dry_feed_tpy:,.0f} t/y")

        if best_margin.annual_margin_usd_y < 0:
            st.warning("**Current case is below break-even.** This is a result of the assumptions shown in the sidebar, not proof that the technology is inherently unviable. Test feedstock cost, selling price, demand, energy costs, CAPEX, discount rate and plant life against supplier quotations and offtake evidence.")
        else:
            st.success("The best-ranked configuration has a positive modelled annual margin under the current assumptions. This is a screening result, not a bankable feasibility conclusion.")

        st.subheader("1 · Which configurations perform best financially?")
        ranked = results.sort_values("annual_margin_usd_y", ascending=True).copy()
        ranked["configuration"] = ranked["technology"].astype(str).str.replace("_", " ").str.title() + " · " + ranked["route"].astype(str).str.replace("_", " ").str.title()
        fig = px.bar(ranked, x="annual_margin_usd_y", y="configuration", orientation="h", color="pareto_optimal",
                     color_discrete_map={True:"#176b5b",False:"#b9c8c2"},
                     labels={"annual_margin_usd_y":"Annual margin (USD/year)","configuration":"Technology · route","pareto_optimal":"Pareto-efficient"},
                     hover_data={"char_tpy":":,.0f","net_removal_tCO2py":":,.0f","annual_margin_usd_y":":,.0f"})
        fig.add_vline(x=0, line_dash="dash", line_color="#d49a45", annotation_text="Break-even", annotation_position="top")
        fig.update_layout(height=max(390, min(720, 30*len(ranked)+130)), legend_title_text="")
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Bars to the right of zero have a positive modelled annual margin; bars to the left indicate an annual loss. Green identifies Pareto-efficient options.")

        st.subheader("2 · Compare the two decision priorities")
        left,right = st.columns(2)
        with left:
            st.markdown("**Best financial outcome**")
            st.metric("Annual margin", f"${best_margin.annual_margin_usd_y:,.0f}")
            st.write(f"{str(best_margin.technology).replace('_',' ').title()} · {str(best_margin.route).replace('_',' ').title()}")
            st.write(f"Screening removal: **{best_margin.net_removal_tCO2py:,.0f} tCO₂/year**")
        with right:
            st.markdown("**Highest removal estimate**")
            st.metric("Screening net removal", f"{best_cdr.net_removal_tCO2py:,.0f} tCO₂/year")
            st.write(f"{str(best_cdr.technology).replace('_',' ').title()} · {str(best_cdr.route).replace('_',' ').title()}")
            st.write(f"Annual margin: **${best_cdr.annual_margin_usd_y:,.0f}/year**")
        st.caption("These may be different configurations because the model optimises financial margin and screening carbon removal as separate objectives.")

        st.subheader("3 · Where does the best financial case spend and earn money?")
        best_breakdown = cost_revenue_breakdown(best_margin.to_dict())
        if not best_breakdown.empty:
            cost_fig = px.bar(best_breakdown, x="usd_per_year", y="category", color="type", orientation="h",
                              color_discrete_map={"Cost":"#d49a45","Revenue":"#176b5b"},
                              labels={"usd_per_year":"USD/year","category":"","type":"Cash-flow type"})
            cost_fig.update_layout(height=360, legend_title_text="")
            st.plotly_chart(cost_fig, use_container_width=True)
        marketable = float(best_margin.get("marketable_char_tpy", 0) or 0)
        if marketable > 0:
            break_even_price = (float(best_margin.total_cost_usd_y)-float(best_margin.carbon_revenue_usd_y))/marketable
            st.info(f"Approximate break-even product price for this configuration: **${break_even_price:,.0f}/t** at the modelled marketable volume of {marketable:,.0f} t/year. This is a simple screening threshold; it assumes other costs, demand and output remain unchanged.")

        with st.expander("Full configuration comparison", expanded=False):
            display_cols=["technology","product_type","route","char_tpy","marketable_char_tpy","product_revenue_usd_y","total_cost_usd_y","annual_margin_usd_y","net_removal_tCO2py","pareto_optimal","quality_status"]
            st.dataframe(results[display_cols].rename(columns={"technology":"Technology","product_type":"Product","route":"Route","char_tpy":"Product (t/y)","marketable_char_tpy":"Marketable product (t/y)","product_revenue_usd_y":"Product revenue (USD/y)","total_cost_usd_y":"Total cost (USD/y)","annual_margin_usd_y":"Annual margin (USD/y)","net_removal_tCO2py":"Screening removal (tCO₂/y)","pareto_optimal":"Pareto-efficient","quality_status":"Quality status"}), use_container_width=True, hide_index=True)
            st.download_button("Download configuration comparison (CSV)", results.to_csv(index=False), "biochar_configuration_comparison.csv", "text/csv")
        st.caption("Model outputs are indicative. Country prices, technology yields, utility demand and CAPEX remain editable assumptions; validate them with local quotations, plant data and offtake evidence. Carbon removal is a simplified screening proxy, not verified LCA/MRV.")

elif page == "Technical":
    st.markdown('<div class="eyebrow">Model documentation</div>', unsafe_allow_html=True)
    st.header("Technical reference")
    st.write("This section documents the deterministic screening engine currently used by the platform. Values shown are defaults; sidebar overrides are applied to the active scenario. These are not vendor guarantees or verified country quotations.")
    st.warning("Model status: engineering and commercial screening only. Product quality requires laboratory testing; carbon removal is a simplified proxy, not a verified LCA/MRV result.")

    with st.expander("1. System boundary and calculation sequence", expanded=True):
        st.markdown("""
        **Calculation sequence**
        1. Received feedstock × plant availability → processed received feed.
        2. Wet-basis moisture correction → dry feed throughput.
        3. Dry feed × technology-specific product yield → annual solid-product output.
        4. Drying and conversion energy → electricity and thermal costs/emissions.
        5. Feedstock, logistics, labour, route, capital recovery and fixed OPEX → annual cost.
        6. Demand-limited product sales and (only if explicitly enabled and verified) CDR revenue → annual margin.
        7. For eligible biochar CDR scenarios, stable-carbon proxy less modelled operating emissions → screening net removal.

        The current calculation is annual and steady-state. It does not perform equipment sizing, transient process simulation, coproduct mass balancing, or split allocation of product across multiple markets.
        """)

    with st.expander("2. Mass balance and moisture model", expanded=True):
        st.latex(r"F_{processed}=F_{received}\,A")
        st.latex(r"F_{dry}=F_{processed}(1-M_{wb})")
        st.latex(r"W/F_{dry}=\frac{M_{wb}}{1-M_{wb}}")
        st.latex(r"Q_{drying}=\frac{M_{wb}}{1-M_{wb}}\frac{2.6}{0.70}\;\mathrm{GJ/t_{dry}}")
        st.latex(r"Q_{total}=(Q_{drying}+Q_{process})\,m_E")
        st.latex(r"P_{solid}=F_{dry}\,Y_{solid,dry}")
        st.markdown("`A` is plant availability; `M_wb` is wet-basis moisture fraction; 2.6 GJ/t-water is the assumed latent/sensible drying duty and 0.70 is assumed drying efficiency; `m_E` is the user energy-demand multiplier. Product yield is a technology input, not a trained prediction.")

    with st.expander("3. Technology assumptions"):
        tech_rows=[]
        for name, cfg in TECHNOLOGIES.items():
            tech_rows.append({"Technology":name,"Product represented":cfg['product'],"Solid yield (dry basis)":cfg['char_yield'],"Process heat (GJ/t dry)":cfg['process_heat_GJ_t_dry'],"Electricity (kWh/t dry)":cfg['electricity_kWh_t_dry'],"CAPEX (USD per t/y)":cfg['capex_usd_per_tpy'],"Fixed OPEX/CAPEX":cfg['fixed_opex_fraction'],"Product C fraction":cfg['char_C_fraction'],"Stable C fraction":cfg['stable_C_fraction'],"Routes":", ".join(cfg['allowed_routes'])})
        st.dataframe(pd.DataFrame(tech_rows), use_container_width=True, hide_index=True)
        st.caption("The table values are editable scenario defaults. HTC is hydrochar; torrefaction is a torrefied solid-fuel route; gasification is represented as gas and ash/char, not automatically as biochar.")

    with st.expander("4. Feedstock and country input assumptions"):
        st.markdown("**Feedstock descriptors currently stored**")
        st.dataframe(pd.DataFrame.from_dict(FEEDSTOCKS, orient="index").rename_axis("Feedstock"), use_container_width=True)
        st.markdown("**Country commercial defaults (USD-based inputs)**")
        market_rows=[]
        for name, cfg in COUNTRY_SCENARIOS.items():
            market_rows.append({"Country":name, **{k:v for k,v in cfg.items() if k not in ('currency','fx_per_usd')}})
        st.dataframe(pd.DataFrame(market_rows).set_index("Country"), use_container_width=True)
        st.caption("Feedstock ash/carbon/nitrogen/contamination descriptors are reference inputs; the current core calculation does not yet use them to predict yield or product properties. FX metadata is not used to convert the USD calculations.")

    with st.expander("5. Route and fixed model constants"):
        route_rows=[]
        for route_name, route_cfg in ROUTES.items():
            route_rows.append({"Route":route_name,"Route cost (USD/t solid)":route_cfg["route_cost_usd_t"],"Demand fraction":route_cfg["demand_fraction"],"Price field":route_cfg["price_key"] or "Energy-value constant"})
        st.dataframe(pd.DataFrame(route_rows), use_container_width=True, hide_index=True)
        st.markdown("**Global constants:** discount rate = 12%; plant life = 15 years; default availability = 85%; energy-route value constant = USD 4.0; carbon crediting disabled; CDR accounting inputs not verified.")
        st.error("Known unit limitation: energy_recovery and solid_fuel currently multiply solid-product tonnes by the USD 4.0 energy-value constant. No product LHV (GJ/t) conversion is applied, so those route revenues are dimensionally incomplete and must not be used as commercial estimates until an LHV-based model is added.")

    with st.expander("6. Economic model", expanded=True):
        st.latex(r"C_{feed}=F_{processed}\,c_{gate}")
        st.latex(r"C_{transport}=F_{processed}\,d\,c_{logistics}")
        st.latex(r"C_{electricity}=F_{dry}\,e_{spec}\,p_e\,m_E")
        st.latex(r"C_{heat}=F_{dry}\,Q_{total}\,p_h")
        st.latex(r"CRF=\frac{r(1+r)^n}{(1+r)^n-1};\quad C_{capital,annual}=CAPEX\,CRF")
        st.latex(r"CAPEX=F_{dry}\,c_{CAPEX}\,m_{CAPEX}")
        st.latex(r"C_{fixed}=CAPEX\,f_{OPEX};\quad C_{labour}=F_{dry}\,c_{labour}")
        st.latex(r"C_{route}=P_{solid}\,c_{route}")
        st.latex(r"P_{marketable}=\min(P_{solid},D_{annual}\,f_{route})")
        st.latex(r"R_{product}=P_{marketable}\,p_{product}")
        st.latex(r"\Pi=R_{product}+R_{CDR}-[C_{feed}+C_{transport}+C_{electricity}+C_{heat}+C_{capital,annual}+C_{fixed}+C_{labour}+C_{route}]")
        st.markdown("The discount rate and plant life are editable in the sidebar under Project finance assumptions and are used in the capital recovery factor. Route-specific demand fractions and route costs are fixed in the `ROUTES` configuration. Carbon-credit revenue is zero unless both crediting and accounting-verification flags are enabled (both are currently false).")

    with st.expander("7. Carbon-removal screening model", expanded=True):
        st.latex(r"C_{stable}=P_{solid}\,f_{C,char}\,f_{stable}")
        st.latex(r"CO_{2,gross}=C_{stable}\frac{44}{12}")
        st.latex(r"E_{heat}=F_{dry}\,Q_{total}\,0.056")
        st.latex(r"E_{grid}=F_{dry}\,e_{spec}\,0.00045")
        st.latex(r"E_{logistics}=F_{processed}\,d\,0.00008")
        st.latex(r"CO_{2,net,screen}=\max(0,CO_{2,gross}-E_{heat}-E_{grid}-E_{logistics})")
        st.markdown("This proxy is only calculated for the `cdr` route when the technology product label is `biochar`. Emission factors and stable-carbon fractions are simplified assumptions. No baseline/additionality, full supply chain, leakage, indirect effects, uncertainty, permanence methodology, MRV or third-party verification is implemented. It must not be represented as creditable removal.")

    with st.expander("8. Application eligibility and quality gates"):
        st.markdown("Technology-route compatibility is a rule-based allow-list. A compatible route is only **eligible for further testing**. It is not a compliance decision or certification. The required tests below are hold points before commercial qualification.")
        for route_name, tests in APPLICATION_REQUIREMENTS.items():
            st.markdown(f"**{route_name.replace('_',' ').title()}**")
            st.write("; ".join(tests))

    with st.expander("9. Optimisation mathematics and decision rule"):
        st.latex(r"\max (\Pi,\;CO_{2,net,screen})")
        st.markdown("The optimiser enumerates the technology-route combinations permitted by the technology table, evaluates each deterministically, and marks a scenario Pareto-optimal if no other scenario is at least as good in both annual margin and screening net removal and strictly better in one. It does not use a weighted score or select a universal winner. The current implementation assigns the full solid output to one route per scenario; it does not optimise split allocations.")

    with st.expander("10. What is not currently modelled"):
        st.markdown("""
        - No trained feedstock-to-yield/property predictor is called by the calculation engine.
        - Feedstock ash, elemental descriptors and contamination fields are displayed as reference data but are not yet used in the core mass/economic equations.
        - No detailed reactor kinetics, temperature/residence-time model, heat integration, gas/oil coproduct balance or equipment sizing.
        - No plant-specific utilities balance, water balance, emissions permit model, taxes, financing structure, NPV/IRR or construction schedule.
        - No measured product quality, certification, offtake validation or full LCA/MRV.
        - Sensitivity grid is deterministic; it is not Monte Carlo or probabilistic uncertainty quantification.
        """)

    st.markdown("#### Live calculation trace for the active sidebar scenario")
    tech = selected_tech
    route_options = TECHNOLOGIES[tech]["allowed_routes"]
    route = st.selectbox("Product route", route_options)
    result = evaluate_configuration(country, feedstock, feed_tpy, moisture, transport_km, tech, route,
                                     availability, capex_multiplier=capex_mult, energy_multiplier=energy_mult,
                                     market_override=market_override, technology_override=custom_tech)
    gate = application_gate(tech, route)
    if result:
        a,b,c = st.columns(3)
        a.metric("Dry feed", f"{result['dry_feed_tpy']:,.1f} t/y")
        b.metric("Char / solid product", f"{result['char_tpy']:,.1f} t/y")
        c.metric("Annual margin", f"${result['annual_margin_usd_y']:,.0f}")
        st.markdown("#### Mass, cost and revenue outputs")
        st.dataframe(pd.DataFrame([result]).T.rename(columns={0:"Value"}), use_container_width=True)
        st.markdown("#### Deterministic cost and revenue decomposition")
        breakdown = cost_revenue_breakdown(result)
        st.plotly_chart(px.bar(breakdown, x="usd_per_year", y="category", color="type", orientation="h",
                               labels={"usd_per_year":"USD/year","category":""}), use_container_width=True)
        st.markdown("#### Application gate")
        st.write(gate["status"])
        st.write("Certification claim allowed:", gate["certification_claim_allowed"])
        for item in gate["required_tests"]:
            st.write("• " + item)
        st.markdown("#### Why this result looks this way")
        for reason in deterministic_reasons(result, {"moisture":moisture,"transport_km":transport_km}, gate):
            st.write("• " + reason)
        st.info(model_validation_warning())
    else:
        st.warning("The selected technology-route combination is not eligible in the current model.")

elif page == "Optimisation":
    st.markdown('<div class="eyebrow">What-if analysis</div>', unsafe_allow_html=True)
    st.header("Custom scenario runner")
    st.write("Build and run independent what-if cases. The platform's supplied baseline comparison remains on the Executive dashboard; scenarios created here are stored separately in this session.")
    with st.form("custom_scenario_form"):
        st.markdown("#### 1. Scenario definition")
        c1,c2,c3 = st.columns(3)
        custom_country = c1.selectbox("Country", list(COUNTRY_SCENARIOS), index=list(COUNTRY_SCENARIOS).index(DEFAULT_COUNTRY), key="custom_country")
        custom_feedstock = c2.selectbox("Feedstock", list(FEEDSTOCKS), index=list(FEEDSTOCKS).index(DEFAULT_FEEDSTOCK), key="custom_feedstock")
        custom_tech_name = c3.selectbox("Technology", list(TECHNOLOGIES), index=list(TECHNOLOGIES).index("slow_pyrolysis"), key="custom_technology")
        cfg = TECHNOLOGIES[custom_tech_name]
        c1,c2,c3 = st.columns(3)
        custom_route = c1.selectbox("Product / market route", cfg["allowed_routes"], key=f"custom_route_{custom_tech_name}")
        custom_feed_rate = c2.number_input("Feedstock received (t/y)", min_value=0.0, value=10000.0, step=250.0, key="custom_feed_rate")
        custom_moisture = c3.slider("Moisture (wet basis)", 0.0, 0.80, 0.12, 0.01, key="custom_moisture")
        c1,c2,c3 = st.columns(3)
        custom_distance = c1.number_input("One-way transport (km)", min_value=0.0, value=60.0, step=5.0, key="custom_distance")
        custom_availability = c2.slider("Plant availability", 0.10, 1.00, 0.85, 0.01, key="custom_availability")
        custom_capex_mult = c3.number_input("CAPEX multiplier", 0.1, 5.0, 1.0, 0.05, key="custom_capex_mult")
        st.markdown("#### 2. Custom engineering assumptions")
        c1,c2,c3 = st.columns(3)
        custom_yield = c1.number_input("Solid product yield (dry basis)", 0.01, 0.95, float(cfg["char_yield"]), 0.01, key=f"custom_yield_{custom_tech_name}")
        custom_heat = c2.number_input("Process heat (GJ/t dry)", 0.0, 20.0, float(cfg["process_heat_GJ_t_dry"]), 0.1, key=f"custom_heat_{custom_tech_name}")
        custom_electricity = c3.number_input("Electricity (kWh/t dry)", 0.0, 2000.0, float(cfg["electricity_kWh_t_dry"]), 5.0, key=f"custom_electricity_{custom_tech_name}")
        c1,c2,c3 = st.columns(3)
        custom_capex = c1.number_input("CAPEX (USD per t/y)", 0.0, 20000.0, float(cfg["capex_usd_per_tpy"]), 50.0, key=f"custom_capex_{custom_tech_name}")
        custom_fixed_opex = c2.number_input("Fixed OPEX / CAPEX", 0.0, 0.5, float(cfg["fixed_opex_fraction"]), 0.01, key=f"custom_fixed_opex_{custom_tech_name}")
        custom_char_c = c3.number_input("Product carbon fraction", 0.0, 1.0, float(cfg["char_C_fraction"]), 0.01, key=f"custom_char_c_{custom_tech_name}")
        custom_stable_c = st.number_input("Stable carbon fraction", 0.0, 1.0, float(cfg["stable_C_fraction"]), 0.01, key=f"custom_stable_c_{custom_tech_name}")
        st.markdown("#### 3. Custom commercial assumptions (USD)")
        mkt = COUNTRY_SCENARIOS[custom_country]
        c1,c2,c3 = st.columns(3)
        custom_feed_cost = c1.number_input("Feedstock gate cost (USD/t received)", 0.0, 5000.0, float(mkt["feedstock_gate_usd_t"]), 1.0, key=f"custom_feed_cost_{custom_country}")
        custom_elec_price = c2.number_input("Electricity price (USD/kWh)", 0.0, 5.0, float(mkt["electricity_usd_kwh"]), 0.01, key=f"custom_elec_price_{custom_country}")
        custom_heat_price = c3.number_input("Thermal energy price (USD/GJ)", 0.0, 500.0, float(mkt["heat_fuel_usd_GJ"]), 1.0, key=f"custom_heat_price_{custom_country}")
        c1,c2,c3 = st.columns(3)
        custom_labour = c1.number_input("Labour (USD/t dry)", 0.0, 1000.0, float(mkt["labour_usd_t_y"]), 1.0, key=f"custom_labour_{custom_country}")
        custom_logistics = c2.number_input("Logistics (USD/t-km)", 0.0, 5.0, float(mkt["logistics_usd_t_km"]), 0.01, key=f"custom_logistics_{custom_country}")
        custom_product_price = c3.number_input("Product price (USD/t)", 0.0, 10000.0, float(mkt["char_price_usd_t"]), 5.0, key=f"custom_product_price_{custom_country}")
        custom_demand = st.number_input("Annual addressable demand (t/y)", 0.0, 10000000.0, float(mkt["demand_char_t_y"]), 250.0, key=f"custom_demand_{custom_country}")
        custom_energy_mult = st.number_input("Energy-demand multiplier", 0.1, 5.0, 1.0, 0.05, key="custom_energy_mult")
        run_custom = st.form_submit_button("Run custom scenario", type="primary")

    if run_custom:
        market_custom = mkt.copy()
        market_custom.update({"feedstock_gate_usd_t":custom_feed_cost,"electricity_usd_kwh":custom_elec_price,
            "heat_fuel_usd_GJ":custom_heat_price,"labour_usd_t_y":custom_labour,
            "logistics_usd_t_km":custom_logistics,"char_price_usd_t":custom_product_price,
            "demand_char_t_y":custom_demand})
        tech_custom = {"char_yield":custom_yield,"process_heat_GJ_t_dry":custom_heat,
            "electricity_kWh_t_dry":custom_electricity,"capex_usd_per_tpy":custom_capex,
            "fixed_opex_fraction":custom_fixed_opex,"char_C_fraction":custom_char_c,
            "stable_C_fraction":custom_stable_c}
        custom_result = evaluate_configuration(custom_country,custom_feedstock,custom_feed_rate,custom_moisture,
            custom_distance,custom_tech_name,custom_route,custom_availability,capex_multiplier=custom_capex_mult,
            energy_multiplier=custom_energy_mult,market_override=market_custom,technology_override=tech_custom)
        if custom_result:
            custom_result["scenario_name"] = f"Custom {len(st.session_state.get('custom_scenarios', []))+1}"
            st.session_state.setdefault("custom_scenarios", []).append(custom_result)
            st.session_state["last_custom_result"] = custom_result

    if st.session_state.get("last_custom_result"):
        r = st.session_state["last_custom_result"]
        st.markdown("#### Latest custom run")
        a,b,c,d = st.columns(4)
        a.metric("Solid product", f"{r['char_tpy']:,.1f} t/y")
        b.metric("Annual margin", f"${r['annual_margin_usd_y']:,.0f}")
        c.metric("Screening net removal", f"{r['net_removal_tCO2py']:,.1f} tCO₂/y")
        d.metric("Dry feed", f"{r['dry_feed_tpy']:,.1f} t/y")
        st.dataframe(pd.DataFrame([r]).T.rename(columns={0:"Value"}), use_container_width=True)
    saved = st.session_state.get("custom_scenarios", [])
    if saved:
        st.markdown("#### Custom scenario history")
        custom_df = pd.DataFrame(saved)
        custom_vals = custom_df[["annual_margin_usd_y","net_removal_tCO2py"]].to_numpy()
        custom_df["pareto_optimal"] = [not (((custom_vals[:,0]>=m)&(custom_vals[:,1]>=c)&((custom_vals[:,0]>m)|(custom_vals[:,1]>c))).any()) for m,c in custom_vals]
        st.dataframe(custom_df[["scenario_name","country","feedstock","technology","route","dry_feed_tpy","char_tpy","annual_margin_usd_y","net_removal_tCO2py","pareto_optimal"]], use_container_width=True)
        st.plotly_chart(px.scatter(custom_df,x="net_removal_tCO2py",y="annual_margin_usd_y",color="pareto_optimal",hover_data=["scenario_name","technology","route"],labels={"net_removal_tCO2py":"Screening net removal (tCO₂/y)","annual_margin_usd_y":"Annual margin (USD/y)"}),use_container_width=True)
        st.download_button("Download custom scenario results (CSV)",custom_df.to_csv(index=False),"custom_biochar_scenarios.csv","text/csv")
        if st.button("Clear custom scenario history"):
            st.session_state["custom_scenarios"] = []
            st.session_state.pop("last_custom_result", None)
            st.rerun()
    else:
        st.info("No custom scenarios have been run in this session yet. The supplied baseline results are not mixed into this workspace.")

elif page == "Sensitivity":
    st.markdown('<div class="eyebrow">Robustness check</div>', unsafe_allow_html=True)
    st.header("Sensitivity analysis")
    with st.spinner("Evaluating feedstock-cost, CAPEX and energy-demand multipliers..."):
        sensitivity = run_sensitivity(country, feedstock, feed_tpy, moisture, transport_km, availability)
    st.caption("Deterministic scenario grid, not a probabilistic uncertainty analysis.")
    st.dataframe(sensitivity, use_container_width=True)
    if len(sensitivity):
        st.plotly_chart(px.scatter(sensitivity, x="best_margin_usd_y", y="net_removal_tCO2py",
                                   color="best_technology", symbol="best_route",
                                   labels={"best_margin_usd_y":"Best annual margin (USD/y)",
                                           "net_removal_tCO2py":"Screening net removal (tCO₂/y)"}),
                        use_container_width=True)
    st.download_button("Download sensitivity grid", sensitivity.to_csv(index=False), "mena_sensitivity.csv", "text/csv")

elif page == "AI analyst":
    st.markdown('<div class="eyebrow">Decision support</div>', unsafe_allow_html=True)
    st.header("AI analyst")
    st.write("Ask for an explanation of the current scenario. The LLM receives structured outputs and assumptions; calculations and optimisation remain deterministic.")
    session_key = st.text_input("Groq API key (optional; session only)", type="password", key="groq_session_key")
    if len(results):
        top = results.iloc[0].to_dict()
        context = {
            "selected_inputs":{"country":country,"feedstock":feedstock,"feedstock_received_tpy":feed_tpy,
                               "moisture_wet_basis":moisture,"transport_km":transport_km,
                               "availability":availability,"capex_multiplier":capex_mult,"energy_multiplier":energy_mult},
            "top_ranked_scenario_by_current_sort":top,
            "pareto_count":len(pareto),
            "cdr_credit_revenue_enabled":False,
            "model_status":"screening prototype; country/technology inputs are placeholders until verified",
            "validation_warning":model_validation_warning(),
            "application_note":"Application gates are screening only, not certification."
        }
        question = st.text_area("Question", "Explain the main economic drivers, carbon-screening trade-offs and the most important data gaps.")
        if st.button("Generate explanation", type="primary"):
            try:
                with st.spinner("Generating explanation..."):
                    st.markdown(explain_with_groq(question, context, api_key=session_key or None))
            except Exception as exc:
                st.error(str(exc))
    else:
        st.warning("Run a scenario with feasible outputs before asking the analyst.")
    st.caption("A key entered above is session-only. For a permanent deployment, use the hosting provider’s server-side secret manager. Never commit a key to Git or put it in the notebook.")

st.divider()
st.caption("Decision-support prototype • All outputs require project-specific engineering, laboratory, commercial and regulatory validation.")
