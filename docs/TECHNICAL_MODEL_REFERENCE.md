# Technical model reference — MENA Biochar Engineering Platform v4.2.2

This document describes the equations implemented in `engine/`. It distinguishes conservation equations and numerical solvers from empirical assumptions and screening correlations. It is not a claim that the platform is a validated reactor digital twin.

## 1. Basis, units and conventions

- Annual throughput is entered as tonnes of wet feed per year.
- Moisture is on a wet basis: \(X_w=m_w/m_{wet}\).
- Product yields are fractions of dry feed and must sum to one.
- In the mass/energy implementation, \(1\ \mathrm{t}\times1\ \mathrm{kJ\,kg^{-1}}=1\ \mathrm{MJ}\), and dividing by 1000 converts MJ to GJ.
- Temperatures in Arrhenius equations are absolute (K); temperature differences in sensible-heat terms may be expressed in °C or K.
- The default property values are screening assumptions. Replace them with measured feedstock data, vendor data and site utility data for engineering design.

## 2. Dry-basis mass balance — MASS-001

**Equation basis:** overall conservation-of-mass accounting [REF-001]. The equations are balance identities; the predicted or selected product fractions are empirical/model inputs and are not established by the balance equation itself.

For wet feed rate \(\dot m_{wet}\) and wet-basis moisture \(X_w\):

\[
\dot m_{dry}=\dot m_{wet}(1-X_w),\qquad
\dot m_{water}=\dot m_{wet}X_w
\]

For dry-basis product fractions \(Y_i\):

\[
Y_{char}+Y_{liquid}+Y_{gas}+Y_{other}=1
\]
\[
\dot m_i=\dot m_{dry}Y_i,\qquad
\epsilon_m=\dot m_{dry}-\sum_i\dot m_i
\]

The code rejects a product split that does not sum to unity (within tolerance). The model is an overall mass balance; it does not resolve individual gas species, condensable species or ash partitioning.

## 3. Process heat and thermodynamics — ENERGY-001

**Equation basis:** sensible heating, latent heat and enthalpy differences follow standard chemical-engineering thermodynamics [REF-002]. The optional water-property backend is based on IAPWS-95 [REF-003] and CoolProp [REF-004]. Heat-transfer terminology and boundary-condition context follow standard transport texts [REF-005, REF-007].

### 3.1 Drying water for pyrolysis, torrefaction and gasification

At the selected pressure \(P\), the water duty is calculated as liquid sensible heating, vaporisation and steam superheating:

\[
q_w=[h_f(P)-h_l(T_{in},P)]+[h_g(P)-h_f(P)]+[h_v(T_r,P)-h_g(P)]
\]
\[
Q_w=\dot m_{water}q_w
\]

When CoolProp is installed, water enthalpies are evaluated using its IAPWS-95 water property implementation. Otherwise the code uses constant-property approximations \(c_{p,l}=4.18\), \(c_{p,v}=2.01\ \mathrm{kJ\,kg^{-1}K^{-1}}\), and \(\Delta h_{vap}=2257\ \mathrm{kJ\,kg^{-1}}\) at approximately 1 atm. The fallback is not a high-pressure steam-table model.

### 3.2 Solids and reaction heat

\[
Q_s=\dot m_{dry}c_{p,s}(T_r-T_{in})
\]
\[
Q_{rx}=\dot m_{dry}\Delta h_{rx}
\]
\[
Q_{useful}=Q_w+Q_s+Q_{rx}
\]

\(\Delta h_{rx}\) is a user-entered lumped reaction-heat term; it defaults to zero. It is not calculated from a detailed reaction network.

The current implementation then applies a heat-loss fraction \(\phi\) and a global heating-system efficiency \(\eta_h\):

\[
Q_{gross}=\frac{Q_{useful}}{1-\phi},\qquad
Q_{purchased}=\frac{Q_{gross}}{\eta_h}
\]

The input is named `dryer_efficiency` internally for backward compatibility but is labelled “Heating efficiency” in the UI. It is applied to the overall useful duty, not only to a standalone dryer. This is a simplified plant-level allowance, not a unit-operation dryer model.

### 3.3 Hydrothermal carbonisation (HTC)

HTC uses liquid-water sensible enthalpy; no water vaporisation or superheating term is included:

\[
m_{slurry\,water}=\max(r_{w/d}m_{dry},m_{water,feed})
\]
\[
Q_w=m_{slurry\,water}[h_l(T_r)-h_l(T_{in})]
\]
\[
Q_{useful,HTC}=(1-\epsilon_{HX})(Q_w+Q_s+Q_{rx})
\]

The slurry water-to-dry-feed ratio and heat-exchanger recovery \(\epsilon_{HX}\) are user assumptions. A real HTC system requires pressure-vessel design and pressure-dependent water properties at operating pressure; the present calculation is a heat-duty screen, not a pressure-vessel or phase-equilibrium design.

### 3.4 Co-product heat recovery without double counting liquid sales

The gas fraction is assumed available for combustion. Only the explicitly diverted fraction \(f_{L\to H}\) of liquid product is burned:

\[
E_{co}=m_{gas}LHV_{gas}+m_{liquid}f_{L\to H}LHV_{liquid}
\]
\[
Q_{recovered}=f_{rec}E_{co}
\]
\[
Q_{deficit}=\max(0,Q_{purchased}-Q_{recovered}),\quad
Q_{surplus}=\max(0,Q_{recovered}-Q_{purchased})
\]

The liquid sales revenue is calculated only on the undiverted fraction:
\[
R_{liquid}=m_{liquid}(1-f_{L\to H})p_{liquid}
\]

This allocation avoids counting the same liquid product as both fuel and a saleable product. Gas-cleaning losses, combustion efficiency by species, flue-gas heat recovery and emissions are not explicitly modelled.

## 4. Carbon accounting screen — PERM-001

**Equation basis:** the factor 44/12 is the molecular-mass ratio for converting carbon mass to CO₂ mass. This gross stoichiometric conversion is not a carbon-removal methodology. Creditable net removal requires a methodology-compliant project boundary and life-cycle inventory [REF-020], while biochar sampling and analytical quality should follow recognised procedures such as EBC [REF-021].

\[
C_{feed}=m_{dry}x_{C,feed},\qquad C_{char}=m_{char}x_{C,char}
\]
\[
\eta_C=C_{char}/C_{feed}
\]

A scenario is flagged if \(\eta_C>1\). This is a necessary carbon-conservation check, not a full carbon balance over gas, liquid and char.

The current gross storage proxy is:
\[
CO_{2,gross}=m_{char}x_{C,char}f_{stable}\frac{44}{12}
\]
\[
CO_{2,net,proxy}=CO_{2,gross}-E_{lifecycle,user}
\]

The \(f_{stable}(H/C)\) map is a placeholder interpolation, not a validated BC+100 regression. Lifecycle emissions are entered by the user and default to zero; therefore the displayed net-removal proxy must not be interpreted as measured net carbon dioxide removal, verified storage, or eligible carbon credits. A defensible CDR assessment requires a defined system boundary, feedstock counterfactual, measured carbon content, permanence model, leakage/reversal treatment, transport, process energy, application emissions and MRV.

## 5. Particle heat transfer — PART-001

**Equation basis:** the spherical transient-conduction equation and analytical verification case are grounded in classical heat conduction [REF-005–REF-007]. Biomass pyrolysis particle models commonly couple heat transfer and reaction kinetics; Di Blasi (2003) is a direct modelling precedent [REF-009], and Di Blasi (2008) reviews the broader modelling literature [REF-008]. The platform is materially simpler than those detailed models.

The reduced-order model is transient, one-dimensional radial conduction in a sphere with a convective boundary:

\[
\rho c_p\frac{\partial T}{\partial t}=
\frac{1}{r^2}\frac{\partial}{\partial r}
\left(kr^2\frac{\partial T}{\partial r}\right)
-\Delta H\,\rho_0\left(-\frac{\partial f}{\partial t}\right)
\]

Centre symmetry and surface convection:
\[
\left.\frac{\partial T}{\partial r}\right|_{r=0}=0,\qquad
-k\left.\frac{\partial T}{\partial r}\right|_{r=R}=h(T_s-T_\infty)
\]

The finite-volume mesh uses spherical shell volumes and face areas, harmonic-mean conductivity, an implicit Euler time step and a banded linear solve. Effective properties are blended with remaining virgin fraction \(f\) and assumed char mass fraction \(y_c\):

\[
(\rho c_p)_{eff}=\rho_0[fc_{p,v}+y_c(1-f)c_{p,c}],\quad
k_{eff}=fk_v+(1-f)k_c
\]

The solver is verified against the analytical transient-conduction solution for a sphere with constant properties and a prescribed surface temperature. This verifies the conduction discretisation under that test case; it does not validate assumed particle properties, convection coefficient, reaction kinetics or packed-bed behaviour.

## 6. Global devolatilisation kinetics — KIN-001

**Kinetic source:** the parameter pair is attributed to Di Blasi & Branca (2001) [REF-010]. The coupled particle modelling context is discussed by Di Blasi (2003, 2008) [REF-008, REF-009].

The implemented chemistry is a **single global first-order reaction**, not a detailed cellulose/hemicellulose/lignin scheme, not a set of parallel reactions and not a gas-species reaction mechanism:

\[
\frac{df}{dt}=-k(T)f,\qquad
k(T)=A\exp\left(-\frac{E}{RT}\right)
=\exp\left(\ln A-\frac{E}{RT}\right)
\]

\[
f(t)=\exp\left[-\int_0^t k(T(\tau))\,d\tau\right],\qquad
X=1-\frac{\sum_i f_iV_i}{\sum_iV_i}
\]

The default parameters are \(E=141.2\ \mathrm{kJ\,mol^{-1}}\) and \(\ln A=22.2\) (with \(A\) in s\(^{-1}\)), attributed to Di Blasi & Branca (2001) for beech wood. The paper's fitted range is 573–708 K (approximately 300–435 °C). Results outside this temperature range, or for other feedstocks, are extrapolations. The model is used for a particle conversion-time screen only; it does not determine product yields. Product yields come from the separate predictor or process-specific screening anchors.

## 7. Data-driven char property predictor — ML-001

**Algorithm source:** random forests originate from the ensemble method described by Breiman [REF-011]. Publication-grouped splitting uses the GroupKFold procedure documented by scikit-learn [REF-012]. The predictor feature choices are consistent with literature identifying feedstock and process conditions as important determinants of biochar properties [REF-013, REF-014]; these reviews do not validate this trained model. Experimental records in the project bibliography include corn-stover and multi-feedstock studies [REF-015–REF-018].

The predictor is a random forest (200 trees; minimum leaf size 8; maximum features 0.6) using:
- highest treatment temperature (HTT),
- \(\ln(1+t_{res})\),
- heating rate,
- one-hot feedstock class.

Missing numerical inputs are median-imputed. Evaluation uses five-fold `GroupKFold`, grouping by publication title to reduce leakage between observations from the same paper. A feedstock-class mean baseline is also evaluated. For any target where the baseline has higher grouped-CV \(R^2\) than the forest, inference now uses that simpler baseline instead of the inferior forest. Tree-to-tree standard deviation is model disagreement, not a prediction interval. The dataset contains published laboratory/pilot observations and does not establish performance in a particular commercial reactor or in all regional feedstocks.

## 8. Economics — ECON-001

**Equation basis:** capital recovery and discounted cash-flow treatment follow standard plant-design economics [REF-024, REF-025]. These sources support the financial mathematics, not the placeholder commercial inputs or the feasibility of a specific Egyptian project.

\[
CRF=\frac{i(1+i)^n}{(1+i)^n-1},\qquad CAPEX_{ann}=CAPEX\cdot CRF\cdot a
\]
\[
OPEX=C_{feed+log}+C_{electricity}+C_{heat}+C_{labour}+C_{maintenance}+C_{other}
\]
\[
EBITDA_{like}=Revenue-OPEX,\quad Surplus=EBITDA_{like}-CAPEX_{ann}
\]
\[
NPV=-CAPEX+\sum_{t=1}^{n}\frac{EBITDA_{like}}{(1+i)^t}
\]

Cash flows are level annual values with no taxes, debt, working capital, escalation, ramp-up, replacement CAPEX or decommissioning. IRR is reported only when a sign-changing cash-flow solution is found. All commercial inputs are scenario assumptions until replaced with dated, scoped quotations and local operating data.

## 9. Optimisation — DESIGN-001 / OPT-001

**Mathematical basis:** non-dominated sorting and Pareto dominance follow standard multi-criteria optimisation concepts [REF-022, REF-023]. The implementation is finite-grid enumeration plus dominance filtering; it is not NSGA-II and cannot claim a global optimum.

The platform enumerates a finite grid of process, feedstock, temperature, residence time and (for slow pyrolysis) heating rate. It filters by optional H/C, carbon-conservation and particle-conversion constraints, then computes a two-objective non-dominated set:

- maximise annual economic surplus,
- maximise net-removal proxy.

The result is optimal only among the enumerated feasible candidates and within the models' applicability domains. It is not a global optimum and does not convert placeholder assumptions into validated engineering facts.

## 10. Process-specific model status

| Process | Yield basis in this release | Important omissions |
|---|---|---|
| Slow pyrolysis | Literature-trained random forest | Liquid/gas split is a user share of non-char products; ML domain limits apply |
| Fast pyrolysis | Typical dry-wood product split | Slow-pyrolysis char-quality model is extrapolated; no vapour-quench or reactor model |
| Torrefaction | Typical dry-wood product split | Solid product is not equivalent to durable biochar; permanence proxy not validated |
| Gasification | Typical dry-wood product split | Oxidant demand, gas equilibrium/speciation, gas cleaning and char gasification kinetics omitted |
| HTC | Linear screening interpolation for char yield and quality | Not a validated kinetic model; pressure-vessel and process-water chemistry omitted |

## References

- Di Blasi, C. (2008). Modeling chemical and physical processes of wood and biomass pyrolysis. *Progress in Energy and Combustion Science*, 34(1), 47–90. https://doi.org/10.1016/j.pecs.2006.12.001
- Di Blasi, C. & Branca, C. (2001). Kinetics of primary product formation from wood pyrolysis. *Industrial & Engineering Chemistry Research*, 40(23), 5547–5556. https://doi.org/10.1021/ie000997e
- Carslaw, H. S. & Jaeger, J. C. (1959). *Conduction of Heat in Solids*, 2nd ed. Oxford University Press.
- Breiman, L. (2001). Random Forests. *Machine Learning*, 45, 5–32. https://doi.org/10.1023/A:1010933404324
- NIST Chemistry WebBook, SRD 69. https://webbook.nist.gov/cgi/cbook.cgi?Name=water
- Felder, R. M., Rousseau, R. W. & Bullard, L. G. *Elementary Principles of Chemical Processes*, 4th ed. Wiley (2016).
- Peters, M. S., Timmerhaus, K. D. & West, R. E. *Plant Design and Economics for Chemical Engineers*, 5th ed. McGraw-Hill (2003).


## 10. Numerical provenance and ground-case benchmarks (v4.2.0)

The platform now includes `references/numerical_assumptions.csv`, which inventories numeric defaults, search bounds, empirical anchors, engineering assumptions and exact identities. Blank source URLs are intentional where a value is a user-entered scenario assumption or where no defensible source has been established. Such values must not be presented as measured facts.

`data/case_studies.csv` records benchmark observations with feedstock, operating conditions, reported basis, DOI and evidence type. The Case Studies page compares the current predictor with two point-condition laboratory records from Mohan et al. (2018): rice husk at 550 °C and corn stover at 650 °C, each at 30 min and 10 °C/min. Reported char yields were 33.2 and 29.7 wt% of feed, respectively; reported char carbon was 74.37 and 77.51 wt%, and H/C was 0.29 and 0.34. DOI: 10.1039/C7RA10353K. The model comparison is a literature consistency check, not a blind validation; rice husk is mapped to the herbaceous class because there is no rice-husk-specific model class.

A rice-straw slow-pyrolysis study reports approximately 25% biochar mass yield from the organic fraction above 500 °C (Park et al., 2014, DOI: 10.1016/j.biortech.2013.12.084). Because this is a broad temperature statement rather than a precise matched point, the app shows it as context only and does not compute pointwise error. A 2026 biomass pyrolysis pilot-plant study reports a Case A bottom-outlet process heat demand of 1.37 ± 0.20 MJ/kg and energy efficiency of 80.35 ± 2.86%; system boundaries must be aligned before comparing with platform purchased heat (DOI: 10.1016/j.enconman.2026.121154).

The Case Studies page explicitly distinguishes reported observations from model predictions and screening assumptions. The comparison is not evidence of industrial scale-up, carbon-credit eligibility, or commercial profitability.


## 11. Equation-level citation and evidence map (v4.2.2)

The companion file `references/mathematical_model_references.csv` is the authoritative citation map for this release. It maps model IDs and sub-models to governing-equation references, numerical-method references, empirical parameter sources, software references, and validation scope. The map intentionally distinguishes a source that explains an equation from a paper that supplies a fitted parameter or a dataset that tests predictions.

### Evidence classes used in the citation map

- **Governing equation / textbook:** supports the mathematical form or conservation law.
- **Authoritative property formulation:** supplies thermophysical property functions (for example, IAPWS-95 water properties).
- **Parameter source:** supplies a fitted coefficient or reported empirical value; applicability domain must be retained.
- **Experimental dataset:** measured observations suitable for training or benchmarking after units, basis and operating conditions are reconciled.
- **Numerical verification:** checks whether the numerical implementation solves a stated mathematical problem. This is not experimental validation of the physical model.
- **Assumption / placeholder:** no defensible source has been established for the exact value; it remains user-editable and must not be presented as a literature constant.

### Important limitations retained

1. The mass and energy balances are conservation-based calculations, but product yields, reaction enthalpy, heat losses, heating efficiency and feedstock properties are not automatically literature-validated.
2. The particle solver's comparison with the analytical sphere solution is code verification only. Biomass-specific conductivity, heat capacity, density, particle geometry, heat-transfer coefficient and reaction enthalpy remain assumptions unless measured or sourced for the actual feedstock and reactor.
3. The global kinetic parameters are wood-derived and have a limited fitted temperature range. Their use for rice straw, bagasse, date palm, manure or other feeds is an extrapolation.
4. The random-forest citation supports the algorithm, not model skill. The uploaded bibliography is a candidate source pool; every training row still needs traceable extraction, unit/basis harmonisation, duplicate checks and paper-level grouping.
5. The carbon-storage equation is a gross stoichiometric proxy. A permanence factor interpolated from H/C is not a validated regression, and zero lifecycle emissions is not a defensible project LCA. Use a current recognised methodology and project-specific inventory before any net-removal or credit claim.
6. Bridgwater's fast-pyrolysis review is not a sufficient basis for using one common product split for torrefaction and gasification. Those two process splits remain screening placeholders pending process-specific references and reactor data.
7. The economics equations are standard, but CAPEX, OPEX, selling prices, energy prices, maintenance and financing assumptions are not evidence-based Egypt estimates.

### Suggested model-validation priority

First validate mass closure and water/energy property calculations; then validate particle temperature histories against instrumented experiments; then validate yield/property predictions using a genuinely external feedstock/reactor dataset; finally replace the carbon proxy and financial placeholders with methodology-compliant LCA and Egypt-specific quotations.
