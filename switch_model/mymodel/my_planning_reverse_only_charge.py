import os
from pyomo.environ import *

dependencies = (
    "switch_model.timescales",
    "switch_model.financials",
    "switch_model.balancing.load_zones",
    "switch_model.energy_sources.properties",
    "switch_model.generators.core.build",
    "switch_model.generators.core.dispatch",
)
optional_prerequisites = (
    "switch_model.generators.storage",
    "switch_model.transmission.local_td",
    "switch_model.transmission.transport.build",
    "switch_model.transmission.transport.dispatch",
)


def define_dynamic_lists(model):
    model.CAPACITY_FOR_RESERVES = []
    model.REQUIREMENTS_FOR_CAPACITY_RESERVES = []


def define_components(model):
    # 一堆计划储备应该满足的要求
    model.PLANNING_RESERVE_REQUIREMENTS = Set(
        dimen=1, doc="Areas and times where planning reserve margins are specified."
    )
    # 一堆计划储备和它限制的区域z，其实每个prr就对应一个z
    model.PRR_ZONES = Set(
        dimen=2,
        doc=(
            "A set of (prr, z) that describes which zones contribute to each "
            "Planning Reserve Requirement."
        ),
    )
    # 计划系数
    model.prr_cap_reserve_margin = Param(
        model.PLANNING_RESERVE_REQUIREMENTS, within=PercentFraction, default=0.15
    )
    # 这一系列要求要满足的时间点，输入里都是peak load
    model.prr_enforcement_timescale = Param(
        model.PLANNING_RESERVE_REQUIREMENTS,
        default="peak_load",
        within=Any,
        validate=lambda m, value, prr: value in {"all_timepoints", "peak_load"},
        doc=(
            "Determines whether planning reserve requirements are enforced in "
            "each timepoint, or just timepoints with peak load (zone_demand_mw)."
        ),
    )
# 得到peak load的时间点
    def get_peak_timepoints(m, prr):
        """
        Return the set of timepoints with peak load within a planning reserve
        requirement area for each period. For this calculation, load is defined
        statically (zone_demand_mw), ignoring the impact of all distributed
        energy resources.
        """
        peak_timepoint_list = []
        # 根据输入的约束prr在prr zones里找到相应的zones存在list里
        ZONES = [z for (_prr, z) in m.PRR_ZONES if _prr == prr]
        # 针对这个约束prr的z，得到周期p中所有时间点里负载最大的时间点，和相应的负载
        for p in m.PERIODS:
            peak_load = 0.0
            for t in m.TPS_IN_PERIOD[p]:
                load = sum(m.zone_demand_mw[z, t] for z in ZONES)
                if load >= peak_load:
                    peak_timepoint = t
                    peak_load = load
            peak_timepoint_list.append(peak_timepoint)
        return peak_timepoint_list

    def PRR_TIMEPOINTS_init(m):
        PRR_TIMEPOINTS = []
        for prr in m.PLANNING_RESERVE_REQUIREMENTS:
            if m.prr_enforcement_timescale[prr] == "all_timepoints":
                PRR_TIMEPOINTS.extend([(prr, t) for t in m.TIMEPOINTS])
            elif m.prr_enforcement_timescale[prr] == "peak_load":
                PRR_TIMEPOINTS.extend([(prr, t) for t in get_peak_timepoints(m, prr)])
            else:
                raise ValueError(
                    "prr_enforcement_timescale not recognized: '{}'".format(
                        m.prr_enforcement_timescale[prr]
                    )
                )
        return PRR_TIMEPOINTS
# 根据输入参数prr_enforcement_timescale，强制要求需要满足的时间点是all time points还是peak load
# 得到这个集合
# 输入里都是peak load
    model.PRR_TIMEPOINTS = Set(
        dimen=2,
        within=model.PLANNING_RESERVE_REQUIREMENTS * model.TIMEPOINTS,
        initialize=PRR_TIMEPOINTS_init,
        doc=(
            "The sparse set of (prr, t) for which planning reserve "
            "requirements are enforced."
        ),
    )
# 参数：是否能提供储备
    model.gen_can_provide_cap_reserves = Param(
        model.GENERATION_PROJECTS,
        within=Boolean,
        default=True,
        doc="Indicates whether a generator can provide capacity reserves.",
    )
#########
    model.str_can_provide_cap_reserves = Param(
        model.STORAGE_GENS,
        within=Boolean,
        default=True,
        doc="Indicates whether a generator can provide capacity reserves.",
    )
    
# 在时间点t发电机g的装机容量有多少计入了要求里，对不提供储备的发电机是0，对可再生能源是capacity factor
    def gen_capacity_value_default(m, g, t):
        if not m.gen_can_provide_cap_reserves[g]:
            return 0.0
        elif g in m.VARIABLE_GENS:
            # This can be > 1 (Ex solar on partly cloudy days). Take a
            # conservative approach of capping at 100% of nameplate capacity.
            return min(1.0, m.gen_max_capacity_factor[g, t])
        else:
            return 1.0

    model.gen_capacity_value = Param(
        model.GEN_TPS,
        within=NonNegativeReals,
        default=gen_capacity_value_default,
        validate=lambda m, value, g, t: (
            value == 0.0 if not m.gen_can_provide_cap_reserves[g] else True
        ),
    )

# 就是选出要满足prr要求的区域z，这个规则之前写过了
    def zones_for_prr(m, prr):
        return [z for (_prr, z) in m.PRR_ZONES if _prr == prr]

# 输入应该要满足的要求和时间点，得到能够获得的容量，把所有约束的区域z上的g的容量都加起来了
# 每个prr只有一个z，这就可以理解了，其实就是计算一个区域上的。
    def AvailableReserveCapacity_rule(m, prr, t):
        reserve_cap = 0.0
# 得到约束prr应该满足的z
        ZONES = zones_for_prr(m, prr)
# g，z上的g，加上输入的时间，能在线且能够提供储备
        GENS = [
            g
            for z in ZONES
            for g in m.GENS_IN_ZONE[z]
            if (g, t) in m.GEN_TPS and m.gen_can_provide_cap_reserves[g]
        ]
# 针对存储项目，只能计算它当前输出，分布式项目就不考虑了，这里可能要改一下，
# 要不要把电动汽车和其他储能考虑进来呢
# ##############
        STORAGE_GENS = getattr(m, "STORAGE_GENS", set())
        for g in GENS:
            # Storage is only credited with its expected output
            if hasattr(m, "Distributed_Power_Injections") and m.gen_is_distributed[g]:
                pass 
            # If local_td is included with DER modeling, avoid allocating
            # distributed generation to central grid capacity because it will
            # be credited with adjusting load at the distribution node.
            else:
                reserve_cap += m.gen_capacity_value[g, t] * m.GenCapacityInTP[g, t]
        
        for g in STORAGE_GENS:
            # Storage is only credited with its expected output
            if hasattr(m, "Distributed_Power_Injections") and m.str_is_distributed[g]:
                pass 
            # If local_td is included with DER modeling, avoid allocating
            # distributed generation to central grid capacity because it will
            # be credited with adjusting load at the distribution node.
            elif m.str_is_reconnected[g]:
                reserve_cap += m.DischargeStorage[g, t] - m.ChargeStorage[g, t]
            else:
                reserve_cap += m.DischargeStorage[g, t] - m.ChargeStorage[g, t]
            
        return reserve_cap

    model.AvailableReserveCapacity = Expression(
        model.PRR_TIMEPOINTS, rule=AvailableReserveCapacity_rule
    )
    model.CAPACITY_FOR_RESERVES.append("AvailableReserveCapacity")
    
# 这个也是根据z和t设定的，z是prr约束的z，t是输入的t
    if "TXPowerNet" in model:
        model.CAPACITY_FOR_RESERVES.append("TXPowerNet")
        
# 需要的容量，这是以是否加那个local-td模块来设定的
    def CapacityRequirements_rule(m, prr, t):
        ZONES = zones_for_prr(m, prr)
        if hasattr(m, "WithdrawFromCentralGrid"):
            
            return sum(
                (1 + m.prr_cap_reserve_margin[prr]) *
                (m.WithdrawFromCentralGrid[z, t] + m.ChargeStorage[g,t] - m.DischargeStorage[g,t])
                for z in ZONES
                for g in m.STR_IN_ZONE[z] if m.str_is_distributed[g]
                
            )\
            + sum(
                (1 + m.prr_cap_reserve_margin[prr]) * 
                (m.ChargingPower[ev, t] )
                for z in ZONES
                for ev in m.EV_IN_ZONE[z]
            )
        else:
            return sum(
                (1 + m.prr_cap_reserve_margin[prr]) *
                (m.WithdrawFromCentralGrid[z, t] + m.ChargeStorage[g,t] - m.DischargeStorage[g,t])
                for z in ZONES
                for g in m.STR_IN_ZONE[z] if m.str_is_distributed[g]
                
            )\
            + sum(
                (1 + m.prr_cap_reserve_margin[prr]) * 
                (m.ChargingPower[ev, t])
                for z in ZONES
                for ev in m.EV_IN_ZONE[z]
            )

    model.CapacityRequirements = Expression(
        model.PRR_TIMEPOINTS, rule=CapacityRequirements_rule
    )
    model.REQUIREMENTS_FOR_CAPACITY_RESERVES.append("CapacityRequirements")

# 对于每一个约束prr，和输入的时间点t，计划的容量都应该大于计划容量。
def define_dynamic_components(model):
    """ """
    model.Enforce_Planning_Reserve_Margin = Constraint(
        model.PRR_TIMEPOINTS,
        rule=lambda m, prr, t: (
            sum(
                getattr(m, reserve_cap)[prr, t]
                for reserve_cap in m.CAPACITY_FOR_RESERVES
            )
            >= sum(
                getattr(m, cap_requirement)[prr, t]
                for cap_requirement in m.REQUIREMENTS_FOR_CAPACITY_RESERVES
            )
        ),
        doc=(
            "Ensures that the sum of CAPACITY_FOR_RESERVES satisfies the sum "
            "of REQUIREMENTS_FOR_CAPACITY_RESERVES for each of PRR_TIMEPOINTS."
        ),
    )
def load_inputs(model, switch_data, inputs_dir):

    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "reserve_capacity_value.csv"),
        optional=True,
        param=(model.gen_capacity_value),
    )
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "planning_reserve_requirements.csv"),
        optional=True,
        index=model.PLANNING_RESERVE_REQUIREMENTS,
        optional_params=["gen_can_provide_cap_reserves", "prr_enforcement_timescale"],
        param=(model.prr_cap_reserve_margin, model.prr_enforcement_timescale),
    )
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "gen_info.csv"),
        optional_params=["gen_can_provide_cap_reserves"],
        param=(model.gen_can_provide_cap_reserves),
    )
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "planning_reserve_requirement_zones.csv"),
        set=model.PRR_ZONES,
    )
