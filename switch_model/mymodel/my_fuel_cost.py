from __future__ import division

import logging
import os, collections

import pandas as pd
from pyomo.environ import *

from switch_model.reporting import write_table
from switch_model.utilities import unwrap

dependencies = (
    "switch_model.timescales",
    "switch_model.balancing.load_zones",
    "switch_model.financials",
    "switch_model.energy_sources.properties",
    "switch_model.generators.core.build",
)
optional_dependencies = "switch_model.transmission.local_td"


def define_components(mod):
    # mod.gen_energy_source = Param(
    #     mod.GENERATION_PROJECTS,
    #     validate=lambda m, val, g: val in m.ENERGY_SOURCES or val == "multiple",
    #     within=Any,
    # )   
    
    mod.gen_uses_fuel = Param(
        mod.GENERATION_PROJECTS,
        within=Boolean,
        initialize=lambda m, g: (
            m.gen_energy_source[g] in m.FUELS or m.gen_energy_source[g] == "multiple"
        ),
    )
    
    mod.FUEL_BASED_GENS = Set(
        dimen=1,
        initialize=mod.GENERATION_PROJECTS,
        filter=lambda m, g: m.gen_uses_fuel[g],
    )
    mod.gen_full_load_heat_rate = Param(mod.FUEL_BASED_GENS, within=NonNegativeReals)
    
    mod.gen_startup_fuel = Param(
        mod.FUEL_BASED_GENS, default=0.0, within=NonNegativeReals
    )
     
    mod.MULTIFUEL_GENS = Set(
        dimen=1,
        within=Any,
        initialize=mod.GENERATION_PROJECTS,
        filter=lambda m, g: m.gen_energy_source[g] == "multiple",
    )
    mod.MULTI_FUEL_GEN_FUELS = Set(
        dimen=2, validate=lambda m, g, f: g in m.MULTIFUEL_GENS and f in m.FUELS
    )
        
    def FUELS_FOR_MULTIFUEL_GEN_init(m, g):
        if not hasattr(m, "FUELS_FOR_MULTIFUEL_GEN_dict"):
            m.FUELS_FOR_MULTIFUEL_GEN_dict = {_g: [] for _g in m.MULTIFUEL_GENS}
            for _g, f in m.MULTI_FUEL_GEN_FUELS:
                m.FUELS_FOR_MULTIFUEL_GEN_dict[_g].append(f)
        result = m.FUELS_FOR_MULTIFUEL_GEN_dict.pop(g)
        if not m.FUELS_FOR_MULTIFUEL_GEN_dict:
            del m.FUELS_FOR_MULTIFUEL_GEN_dict
        return result
    
    mod.FUELS_FOR_MULTIFUEL_GEN = Set(
        mod.MULTIFUEL_GENS,
        dimen=1,
        within=mod.FUELS,
        initialize=FUELS_FOR_MULTIFUEL_GEN_init,
    )  
    
    mod.FUELS_FOR_GEN = Set(
        mod.FUEL_BASED_GENS,
        dimen=1,
        initialize=lambda m, g: (
            m.FUELS_FOR_MULTIFUEL_GEN[g]
            if g in m.MULTIFUEL_GENS
            else [m.gen_energy_source[g]]
        ),
    )
    mod.FUEL_BASED_GEN_TPS = Set(
        dimen=2,
        initialize=lambda m: (
            (g, tp) for g in m.FUEL_BASED_GENS for tp in m.TPS_FOR_GEN[g]
        ),
    )
    mod.GEN_TP_FUELS = Set(
        dimen=3,
        initialize=lambda m: (
            (g, t, f) for (g, t) in m.FUEL_BASED_GEN_TPS for f in m.FUELS_FOR_GEN[g]
        ),
    )
    
    # 燃料使用率，是根据前面我说没啥用的集合来设置的。换个位置
    mod.GenFuelUseRate = Var(
        mod.GEN_TP_FUELS,
        within=NonNegativeReals,
        doc=(
            "Other modules constraint this variable based on DispatchGen and "
            "module-specific formulations of unit commitment and heat rates."
        ),
    )
    
    mod.ZONE_FUEL_PERIODS = Set(
        dimen=3,
        validate=lambda m, z, f, p: (
            z in m.LOAD_ZONES and f in m.FUELS and p in m.PERIODS
        ),
    )
    mod.fuel_cost = Param(mod.ZONE_FUEL_PERIODS, within=NonNegativeReals)
    mod.min_data_check("ZONE_FUEL_PERIODS", "fuel_cost")

    mod.GEN_TP_FUELS_UNAVAILABLE = Set(
        dimen=3,
        initialize=mod.GEN_TP_FUELS,
        filter=lambda m, g, t, f: (m.gen_load_zone[g], f, m.tp_period[t])
        not in m.ZONE_FUEL_PERIODS,
    )
    
    mod.Enforce_Fuel_Unavailability = Constraint(
        mod.GEN_TP_FUELS_UNAVAILABLE,
        rule=lambda m, g, t, f: m.GenFuelUseRate[g, t, f] == 0,
    )

    # Summarize total fuel costs in each timepoint for the objective function
    def FuelCostsPerTP_rule(m, t):
        if not hasattr(m, "FuelCostsPerTP_dict"):
            # cache all Fuel_Cost_TP values in a dictionary (created in one pass)
            m.FuelCostsPerTP_dict = {t2: 0.0 for t2 in m.TIMEPOINTS}
            for (g, t2, f) in m.GEN_TP_FUELS:
                if (g, t2, f) not in m.GEN_TP_FUELS_UNAVAILABLE:
                    m.FuelCostsPerTP_dict[t2] += (
                        m.GenFuelUseRate[g, t2, f]
                        * m.fuel_cost[m.gen_load_zone[g], f, m.tp_period[t2]]
                    )
        # return a result from the dictionary and pop the element each time
        # to release memory
        return m.FuelCostsPerTP_dict.pop(t)

    mod.FuelCostsPerTP = Expression(mod.TIMEPOINTS, rule=FuelCostsPerTP_rule)
    mod.Cost_Components_Per_TP.append("FuelCostsPerTP")


def load_inputs(mod, switch_data, inputs_dir):
    """
    Import simple fuel cost data. The following file is expected in
    the input directory:

    fuel_cost.csv
        load_zone, fuel, period, fuel_cost

    """
    
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "gen_info.csv"),
        param=(
            # mod.gen_energy_source,
            mod.gen_full_load_heat_rate,
            mod.gen_startup_fuel
        ),
    )

    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "fuel_cost.csv"),
        index=mod.ZONE_FUEL_PERIODS,
        param=[mod.fuel_cost],
    )
    