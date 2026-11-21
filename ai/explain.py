def explain_results(technical, economics, predicted=False, design=None):
    notes = []
    notes.append(
        f"The dry feed rate is {technical['dry_feed_t_y']:,.1f} t/y from "
        f"{technical['wet_feed_t_y']:,.1f} t/y wet feed. The mass-balance residual is "
        f"{technical['mass_balance_residual_t_y']:.6f} t/y."
    )
    if predicted and design:
        notes.append(
            f"Product yields come from the literature-trained predictor for {design['feed']} at {design['htt']:.0f} \u00b0C and "
            f"{design['dur']:.0f} min. The char fraction is predicted; the liquid/gas split of the remainder is an assumption "
            f"({design['liquid_share']:.0%} liquid)."
        )
    else:
        notes.append("Product fractions are manual inputs, not model-predicted yields.")
    notes.append(
        f"The scenario produces {technical['char_t_y']:,.1f} t/y char, "
        f"{technical['liquid_t_y']:,.1f} t/y liquid and {technical['gas_t_y']:,.1f} t/y gas."
    )
    notes.append(
        f"Estimated purchased heat is {technical['purchased_heat_requirement_GJ_y']:,.1f} GJ/y; "
        f"recoverable co-product heat is {technical['recoverable_coproduct_heat_GJ_y']:,.1f} GJ/y. "
        "This is a screening energy balance, not a reactor heat-transfer simulation."
    )
    notes.append(
        f"Revenue is ${economics['total_revenue_usd_y']:,.0f}/y against operating costs of "
        f"${economics['operating_cost_usd_y']:,.0f}/y. EBITDA-like surplus is ${economics['ebitda_like_usd_y']:,.0f}/y; "
        f"after annualised capital recovery the economic surplus is ${economics['annual_economic_surplus_usd_y']:,.0f}/y."
    )
    if economics.get("carbon_revenue_usd_y", 0) > 0:
        share = economics["carbon_revenue_usd_y"] / max(economics["total_revenue_usd_y"], 1e-9)
        notes.append(f"Carbon credits contribute ${economics['carbon_revenue_usd_y']:,.0f}/y ({share:.0%} of revenue). This depends on the removal proxy being verified and creditable, which it currently is not.")
    notes.append(
        f"The net-removal figure ({technical['net_removal_proxy_tco2e_y']:,.1f} tCO2e/y) is a screening proxy, "
        "not a verified removal quantity."
    )
    if economics["annual_economic_surplus_usd_y"] < 0:
        notes.append("The scenario is economically negative under the entered assumptions. Check offtake prices, feedstock logistics, energy integration, utilisation and capital cost.")
    if technical["heat_deficit_GJ_y"] > 0:
        notes.append("Co-product heat does not cover the process duty; external heat is required in this case.")
    return notes
