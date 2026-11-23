"""The mathematical models behind each page, written as LaTeX (shown with st.latex) plus short notes.
Each entry: list of (kind, text) where kind is 'md' (markdown) or 'tex' (LaTeX). Keep in sync with the code."""

ESTIMATES = [
    ("md", "**Data-driven predictor (ML-001)**: random forest of B = 200 regression trees, min leaf size 8, max 60% features per split, one model per target y (char yield, carbon, ash, H/C). Missing inputs are median-imputed. Five-fold publication-grouped CV is compared with a feedstock-class mean; the class mean is used at inference whenever it scores better."),
    ("tex", r"x=[\mathrm{HTT},\ \ln(1+t_{res}),\ \beta,\ \text{feedstock-class one-hot}]"),
    ("tex", r"\hat y(x)=\frac1B\sum_{b=1}^{B}T_b(x),\qquad \sigma(x)=\sqrt{\frac1B\sum_{b=1}^{B}\big(T_b(x)-\hat y(x)\big)^2}"),
    ("md", "The spread \u03c3 is the disagreement between trees, not a calibrated confidence interval."),
    ("md", "**Validation**: 5-fold cross-validation grouped by publication (whole papers held out), compared with a class-mean baseline."),
    ("tex", r"R^2_{CV}=1-\frac{\sum_i (y_i-\hat y_i^{\,oof})^2}{\sum_i (y_i-\bar y)^2}"),
    ("md", "**Carbon permanence screening (PERM-001)**: piecewise-linear map from predicted molar H/C to the fraction of char carbon stable beyond 100 years (placeholder numbers)."),
    ("tex", r"f_{stable}=\mathrm{interp}\big(H/C;\ [0,0.4,0.7,1.0,1.5]\mapsto[0.90,0.85,0.65,0.40,0.20]\big)"),
    ("md", "**Other processes**: fast pyrolysis, torrefaction and gasification use typical product splits (Bridgwater 2012, dry wood) for yields; HTC uses a linear screening line. Char C and H/C for the first three come from the same predictor at the process temperature."),
    ("tex", r"Y_{char}^{HTC}(T)=0.65-0.30\,\frac{T-180}{80},\qquad 180\le T\le 260\ ^\circ\mathrm{C}"),
    ("md", "**Rough result per basis feed**"),
    ("tex", r"m_{dry}=m_{wet}(1-X_w),\quad m_{char}=m_{dry}Y_{char},\quad \mathrm{CO_2}_{stored}=m_{char}\,c_{char}\,f_{stable}\,\tfrac{44}{12}"),
]

TECHNICAL = [
    ("md", "**1. Mass balance (MASS-001)**"),
    ("tex", r"m_{dry}=m_{wet}(1-X_w),\quad m_{w}=m_{wet}-m_{dry},\quad \sum_i Y_i=1,\quad m_i=m_{dry}Y_i,\quad i\in\{char,\ liquid,\ gas,\ other\}"),
    ("md", "**2. Carbon balance** (feasibility check: char cannot hold more carbon than the feed supplies)"),
    ("tex", r"C_{feed}=m_{dry}x_C,\quad C_{char}=m_{char}c_{char},\quad \eta_C=\frac{C_{char}}{C_{feed}}\le 1"),
    ("md", "**3. Energy balance, pyrolysis / torrefaction / gasification (ENERGY-001)**: water is heated, evaporated and superheated at 1 atm using IAPWS-95 enthalpies; solids heated at constant c\u209a."),
    ("tex", r"Q_w=m_w\Big[\big(h_f-h(T_{in})\big)+h_{fg}+\big(h(T_r,P)-h_g\big)\Big],\quad Q_s=m_{dry}\,c_p\,(T_r-T_{in}),\quad Q_{rx}=m_{dry}\,\Delta H_{pyr}"),
    ("tex", r"Q_{useful}=Q_w+Q_s+Q_{rx},\quad Q_{gross}=\frac{Q_{useful}}{1-\phi},\quad Q_{purch}=\frac{Q_{gross}}{\eta_{heat}}"),
    ("tex", r"E_{co}=m_{gas}\,LHV_g+m_{liq}\,LHV_l,\quad Q_{rec}=f_{rec}E_{co},\quad Q_{deficit}=\max(0,Q_{purch}-Q_{rec}),\quad Q_{surplus}=\max(0,Q_{rec}-Q_{purch})"),
    ("md", "**3b. Energy balance, hydrothermal carbonisation**: the slurry stays liquid (no vaporisation); heat recovery by heat exchange."),
    ("tex", r"m_{slurry}=\max(\rho_w m_{dry},\,m_w),\quad Q_w=m_{slurry}\big[h_f(T_r)-h_f(T_{in})\big],\quad Q_{useful}=(1-\varepsilon_{hx})\,(Q_w+Q_s+Q_{rx})"),
    ("md", "**4. Carbon storage proxy (PERM-001)**"),
    ("tex", r"\mathrm{CO_2}_{gross}=m_{char}\,c_{char}\,f_{stable}\,\frac{44}{12},\qquad \mathrm{CO_2}_{net}=\mathrm{CO_2}_{gross}-E_{lifecycle}"),
    ("md", "**5. Particle heat transfer and devolatilisation (PART-001, KIN-001)**: 1-D spherical conduction with a reacting solid; finite volume, implicit Euler."),
    ("tex", r"\rho c_p\frac{\partial T}{\partial t}=\frac1{r^2}\frac{\partial}{\partial r}\Big(k\,r^2\frac{\partial T}{\partial r}\Big)-\Delta H\,\rho_0\Big(-\frac{\partial f}{\partial t}\Big)"),
    ("tex", r"\frac{\partial T}{\partial r}\Big|_{r=0}=0,\qquad -k\frac{\partial T}{\partial r}\Big|_{r=R}=h\,(T_s-T_\infty),\qquad \frac{\partial f}{\partial t}=-k_r(T)\,f"),
    ("tex", r"k_r=\exp\!\Big(\ln A-\frac{E}{RT}\Big),\quad \rho c_p=\rho_0\big[f\,c_v+y_c(1-f)\,c_c\big],\quad k=f\,k_v+(1-f)\,k_c"),
    ("md", "The implemented kinetics are a **single global first-order devolatilisation step**, not detailed cellulose/hemicellulose/lignin reactions or a gas-species mechanism. The cited beech-wood parameters (ln A = 22.2, E = 141.2 kJ/mol) were fitted over 573–708 K; outside this interval the conversion-time result is an extrapolation."),
    ("tex", r"\frac{df}{dt}=-k_r(T)f,\qquad f(t)=\exp\!\left[-\int_0^t k_r(T(\tau))\,d\tau\right],\qquad X=1-\frac{\sum_i f_iV_i}{\sum_iV_i}"),
    ("tex", r"\bar X=1-\frac{\sum_i f_iV_i}{\sum_i V_i},\quad Bi=\frac{hR}{k_v},\quad \tau_{heat}=\frac{R^2}{\pi^2\alpha},\quad \tau_{kin}=\frac{\ln\!\big(1/(1-X^*)\big)}{k_r(T_\infty)}"),
    ("md", "**Verification**: for constant properties and a fixed surface temperature the centre temperature must match the analytical series"),
    ("tex", r"\frac{T_c-T_\infty}{T_0-T_\infty}=2\sum_{n=1}^{\infty}(-1)^{n+1}e^{-n^2\pi^2 Fo},\qquad Fo=\frac{\alpha t}{R^2}"),
]

ECONOMIC = [
    ("md", "**Cost and revenue (ECON-001)**"),
    ("tex", r"CRF=\frac{i(1+i)^n}{(1+i)^n-1},\qquad CAPEX_{ann}=CAPEX\cdot CRF\cdot a"),
    ("tex", r"OPEX=m_{wet}(c_{feed}+c_{log})+E_{el}\,p_{el}+Q_{deficit}\,p_{heat}+L+m_{maint}\,CAPEX+O"),
    ("tex", r"R=m_{char}p_{char}+m_{liq}p_{liq}+E_{export}\,p_{el}+\max(0,\mathrm{CO_2}_{net})\,p_{C}"),
    ("tex", r"E_{export}=Q_{surplus}\cdot277.78\cdot\eta_{el}\cdot f_{export}\ \ [\mathrm{kWh}]"),
    ("tex", r"EBITDA=R-OPEX,\qquad S_{econ}=EBITDA-CAPEX_{ann}"),
    ("md", "**Project metrics** (constant annual cash flow, no tax, debt, working capital or escalation)"),
    ("tex", r"NPV=-CAPEX+\sum_{t=1}^{n}\frac{EBITDA}{(1+i)^t},\qquad \mathrm{IRR}:\ NPV(r)=0,\qquad t_{payback}=\frac{CAPEX}{EBITDA}"),
    ("md", "**Carbon-price breakeven**: the credit price at which the economic surplus is zero"),
    ("tex", r"p_C^{*}=\max\!\Big(0,\ \frac{CAPEX_{ann}+OPEX-(R-R_{carbon})}{\mathrm{CO_2}_{net}}\Big)"),
    ("md", "**Sensitivity**: one-at-a-time \u00b1 swing on each input, change in S_econ recomputed with the full model (no linearisation)."),
]

OPTIMIZE = [
    ("md", "**Scope**: the implemented optimiser currently searches slow-pyrolysis scenarios only. Other conversion routes use screening-level or cross-process assumptions and are not included in a combined ranking."),
    ("md", "**Decision variables**: feedstock class, reactor temperature T, residence time t and heating rate. The search is exhaustive over a discrete user-selected grid, not a continuous or stochastic optimiser."),
    ("md", "**Fixed basis**: annual throughput and the technical/economic assumptions inherited from the active Technical and Economic scenario. Feedstock moisture, carbon content, cost and logistics are screening presets."),
    ("md", "**Feasibility constraints**"),
    ("tex", r"H/C\le (H/C)_{max},\qquad \eta_C\le 1,\qquad t_{res}\ge s\,t_{95}(T)"),
    ("md", "The particle constraint uses the 1-D single-particle model. Its kinetics are beech-wood parameters fitted over 573–708 K; predictions outside that interval are extrapolations. The optimiser reports only the best candidate within the tested grid."),
    ("md", "**Selectable objective**"),
    ("tex", r"\max NPV,\qquad \max S_{annual},\qquad \max \mathrm{CO_2}_{net,proxy},\qquad \min p_C^*"),
    ("md", "NPV uses the simplified constant annual EBITDA-like cash flow in ECON-001. The break-even carbon price is calculated before carbon revenue. None of these outputs establishes a bankable project case."),
    ("md", "**Trade-off view**: the Pareto set is calculated on annual economic surplus and net-removal proxy. A design is dominated if another design is no worse on both and strictly better on at least one."),
]
BY_PAGE = {"estimates": ESTIMATES, "technical": TECHNICAL, "economic": ECONOMIC, "optimize": OPTIMIZE}
