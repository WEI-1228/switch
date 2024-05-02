from __future__ import division
import os
from pyomo.environ import Set, Param, Expression, Constraint, Suffix, NonNegativeReals
import switch_model.reporting as reporting


def define_components(model):
    
    model.carbon_cap_tco2_per_yr = Param(
        model.PERIODS,
        within=NonNegativeReals,
        default=float("inf"),
        doc=(
            "Emissions from this model must be less than this cap. "
            "This is specified in metric tonnes of CO2 per year."
        ),
    )
# 计算二氧化碳排放量
    def DispatchEmissions_rule(m, g, t, f):
        return m.GenFuelUseRate[g, t, f] * (
                m.f_co2_intensity[f] + m.f_upstream_co2_intensity[f]
            )
            
    
    model.DispatchEmissions = Expression(model.GEN_TP_FUELS, rule=DispatchEmissions_rule)
    model.AnnualEmissions = Expression(
        model.PERIODS,
        rule=lambda m, period: sum(
            m.DispatchEmissions[g, t, f] * m.tp_weight_in_year[t]
            for (g, t, f) in m.GEN_TP_FUELS
            if m.tp_period[t] == period
        ),
        doc="The system's annual emissions, in metric tonnes of CO2 per year.",
    )
    
    model.Enforce_Carbon_Cap = Constraint(
        model.PERIODS,
        rule=lambda m, p: Constraint.Skip
        if m.carbon_cap_tco2_per_yr[p] == float("inf")
        else m.AnnualEmissions[p] <= m.carbon_cap_tco2_per_yr[p],
        doc=("Enforces the carbon cap for generation-related emissions."),
    )
    # Make sure the model has a dual suffix for determining implicit carbon costs
    if not hasattr(model, "dual"):
        model.dual = Suffix(direction=Suffix.IMPORT)

    model.carbon_cost_dollar_per_tco2 = Param(
        model.PERIODS,
        within=NonNegativeReals,
        default=0.0,
        doc="The cost adder applied to emissions, in future dollars per metric tonne of CO2.",
    )
    model.EmissionsCosts = Expression(
        model.PERIODS,
        rule=lambda model, period: model.AnnualEmissions[period]
        * model.carbon_cost_dollar_per_tco2[period],
        doc=("Enforces the carbon cap for generation-related emissions."),
    )
    model.Cost_Components_Per_Period.append("EmissionsCosts")


def load_inputs(model, switch_data, inputs_dir):
    """
    Typically, people will specify either carbon caps or carbon costs, but not
    both. If you provide data for both columns, the results may be difficult
    to interpret meaningfully.

    Expected input files:
    carbon_policies.csv
        PERIOD, carbon_cap_tco2_per_yr, carbon_cost_dollar_per_tco2

    """
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "carbon_policies.csv"),
        optional=True,
        optional_params=(
            model.carbon_cap_tco2_per_yr,
            model.carbon_cost_dollar_per_tco2,
        ),
        param=(model.carbon_cap_tco2_per_yr, model.carbon_cost_dollar_per_tco2),
    )
