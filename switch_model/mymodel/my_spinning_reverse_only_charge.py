import os
from pyomo.environ import *

dependencies = (
    "switch_model.timescales",
    "switch_model.balancing.load_zones",
    "switch_model.balancing.operating_reserves.areas",
    "switch_model.financials",
    "switch_model.energy_sources.properties",
)
# 后面三个模块合并成一个模块了
def define_dynamic_lists(m):
    m.Spinning_Reserve_Up_Requirements = []
    m.Spinning_Reserve_Down_Requirements = []
    m.Spinning_Reserve_Up_Provisions = []
    m.Spinning_Reserve_Down_Provisions = []


def define_components(m):
    
    # 可以提供旋转储备的g
    m.gen_can_provide_spinning_reserves = Param(
        m.GENERATION_PROJECTS, within=Boolean, default=True
    )

    m.str_can_provide_spinning_reserves = Param(
        m.STORAGE_GENS, within=Boolean, default=True
    )    
    # 可以提供旋转储备的g的集合
    m.SPINNING_RESERVE_GEN_TPS = Set(
        dimen=2,
        initialize=m.GEN_TPS,
        filter=lambda m, g, t: m.gen_can_provide_spinning_reserves[g],
    )
    # 可以提供旋转储备的g的集合
    m.SPINNING_RESERVE_STR_TPS = Set(
        dimen=2,
        initialize=m.STR_TPS,
        filter=lambda m, g, t: m.str_can_provide_spinning_reserves[g],
    )
    # 承诺提供的向上旋转储备
    m.CommitGenSpinningReservesUp = Var(
        m.SPINNING_RESERVE_GEN_TPS, within=NonNegativeReals
    )
    # 承诺提供的向下旋转储备
    # m.CommitGenSpinningReservesDown = Var(
    #     m.SPINNING_RESERVE_GEN_TPS, within=NonNegativeReals
    # )

    # 承诺的向上旋转储备的约束，所有能提供旋转储备的设备和时间点
    # 通过减少充电量可以减少准备的向上旋转储备的量,+放电
    m.CommitGenSpinningReservesUp_Limit = Constraint(
        m.SPINNING_RESERVE_GEN_TPS,
        rule=lambda m, g, t: (
            m.CommitGenSpinningReservesUp[g, t]
            <= m.DispatchSlackUp[g, t]
        ),
    )
    # 调度量的向下松弛+当前储能项目g在时间点净放电量。
    # 通过增加充电量来减少下调的旋转储备， +充电
    # m.CommitGenSpinningReservesDown_Limit = Constraint(
    #     m.SPINNING_RESERVE_GEN_TPS,
    #     rule=lambda m, g, t: m.CommitGenSpinningReservesDown[g, t]
    #     <= m.DispatchSlackDown[g, t]
    # )
# 能够提供的向上和向下的旋转储备容量
    # m.CommittedSpinningReserveUp = Expression(
    #     m.ZONE_TIMEPOINTS,
    #     rule=lambda m, z, t: sum(
    #         m.CommitGenSpinningReservesUp[g, t]
    #         for g in m.GENS_IN_ZONE[z]
    #         if (g, t) in m.SPINNING_RESERVE_GEN_TPS
    #     ) + sum(
    #         m.DischargeStorage[g,t]
    #         for g in m.STR_IN_ZONE[z]
    #         if (g, t) in m.SPINNING_RESERVE_STR_TPS
    #         )
    #     )
    # m.Spinning_Reserve_Up_Provisions.append("CommittedSpinningReserveUp")
    
    # m.CommittedSpinningReserveDown = Expression(
    #     m.ZONE_TIMEPOINTS,
    #     rule=lambda m, z, t: sum(
    #         m.CommitGenSpinningReservesDown[g, t]
    #         for g in m.GENS_IN_ZONE[z]
    #         if (g, t) in m.SPINNING_RESERVE_GEN_TPS
    #     ) + sum(
    #         m.ChargeStorage[g,t]
    #         for g in m.STR_IN_ZONE[z]
    #         if (g, t) in m.SPINNING_RESERVE_STR_TPS
    #         )
    #     )
    # m.Spinning_Reserve_Down_Provisions.append("CommittedSpinningReserveDown")  
    

    # m.VARIABLE_GENS_IN_ZONE = Set(
    #     m.LOAD_ZONES,
    #     dimen=1,
    #     initialize=lambda m, z: [g for g in m.GENS_IN_ZONE[z] if m.gen_is_variable[g]],
    # )

    # def NREL35VarGenSpinningReserveRequirement_rule(m, z, t):
    #     try:
    #         load = m.WithdrawFromCentralGrid
    #     except AttributeError:
    #         load = m.lz_demand_mw
    #     return 0.03 * sum(load[z, t] for z in m.LOAD_ZONES )\
    #     + 0.05 * sum(
    #         m.DispatchGen[g, t]
    #         for g in m.VARIABLE_GENS_IN_ZONE[z]
    #         if (g, t) in m.VARIABLE_GEN_TPS
    #     )\
    #     + 0.03 * sum(
    #         (m.ChargingPower[ev, t] - m.DischargingPower[ev, t])
    #         for ev in m.EV_IN_ZONE[z]
    #     )

    # m.NREL35VarGenSpinningReserveRequirement = Expression(
    #     m.ZONE_TIMEPOINTS, rule=NREL35VarGenSpinningReserveRequirement_rule
    # )
    # m.Spinning_Reserve_Up_Requirements.append("NREL35VarGenSpinningReserveRequirement")
    # m.Spinning_Reserve_Down_Requirements.append(
    #     "NREL35VarGenSpinningReserveRequirement"
    # )    

    # Sum of spinning reserve capacity per balancing area and timepoint..
    m.CommittedSpinningReserveUp = Expression(
        m.BALANCING_AREA_TIMEPOINTS,
        rule=lambda m, b, t: sum(
            m.CommitGenSpinningReservesUp[g, t]
            for z in m.ZONES_IN_BALANCING_AREA[b]
            for g in m.GENS_IN_ZONE[z]
            if (g, t) in m.SPINNING_RESERVE_GEN_TPS
        ) + sum(
            m.DischargeStorage[g,t]
            for z in m.ZONES_IN_BALANCING_AREA[b]
            for g in m.STR_IN_ZONE[z]
            if (g, t) in m.SPINNING_RESERVE_STR_TPS
            )
        )
    m.Spinning_Reserve_Up_Provisions.append("CommittedSpinningReserveUp")
    # m.CommittedSpinningReserveDown = Expression(
    #     m.BALANCING_AREA_TIMEPOINTS,
    #     rule=lambda m, b, t: sum(
    #         m.CommitGenSpinningReservesDown[g, t]
    #         for z in m.ZONES_IN_BALANCING_AREA[b]
    #         for g in m.GENS_IN_ZONE[z]
    #         if (g, t) in m.SPINNING_RESERVE_GEN_TPS
    #     ) + sum(
    #         m.ChargeStorage[g,t]
    #         for z in m.ZONES_IN_BALANCING_AREA[b]
    #         for g in m.STR_IN_ZONE[z]
    #         if (g, t) in m.SPINNING_RESERVE_STR_TPS
    #         )
    #     )
    # m.Spinning_Reserve_Down_Provisions.append("CommittedSpinningReserveDown")

    # # 应该满足的向上旋转储备和向下旋转储备的要求，TODO，糟糕了这个约束针对每个平衡区域b的，而不是每个z
    # # 更改了系数,TODO，记得改回来
    def NREL35VarGenSpinningReserveRequirement_rule(m, b, t):
        try:
            load = m.WithdrawFromCentralGrid
        except AttributeError:
            load = m.lz_demand_mw
        return 0.03 * sum(load[z, t] for z in m.LOAD_ZONES if b == m.zone_balancing_area[z])\
        + 0.05 * sum(
            m.DispatchGen[g, t]
            for g in m.VARIABLE_GENS
            if (g, t) in m.VARIABLE_GEN_TPS and b == m.zone_balancing_area[m.gen_load_zone[g]]
        )\
        + 0.03 * sum(
            (m.ChargingPower[ev, t])
            for z in m.LOAD_ZONES if b == m.zone_balancing_area[z]
            for ev in m.EV_IN_ZONE[z]
        )

    m.NREL35VarGenSpinningReserveRequirement = Expression(
        m.BALANCING_AREA_TIMEPOINTS, rule=NREL35VarGenSpinningReserveRequirement_rule
    )
    m.Spinning_Reserve_Up_Requirements.append("NREL35VarGenSpinningReserveRequirement")
    # m.Spinning_Reserve_Down_Requirements.append(
    #     "NREL35VarGenSpinningReserveRequirement"
    # )
    
    #######能够提供的储备大于储备的要求
    # m.Satisfy_Spinning_Reserve_Up_Requirement = Constraint(
    #     m.ZONE_TIMEPOINTS,
    #     rule=lambda m, z, t: sum(
    #         getattr(m, requirement)[z, t]
    #         for requirement in m.Spinning_Reserve_Up_Requirements
    #     )
    #     <= sum(
    #         getattr(m, provision)[z, t]
    #         for provision in m.Spinning_Reserve_Up_Provisions
    #     ),
    # )
    m.Satisfy_Spinning_Reserve_Up_Requirement = Constraint(
        m.BALANCING_AREA_TIMEPOINTS,
        rule=lambda m, b, t: sum(
            getattr(m, requirement)[b, t]
            for requirement in m.Spinning_Reserve_Up_Requirements
        )
        <= sum(
            getattr(m, provision)[b, t]
            for provision in m.Spinning_Reserve_Up_Provisions
        ),
    )
    
    # m.Satisfy_Spinning_Reserve_Down_Requirement = Constraint(
    #     m.BALANCING_AREA_TIMEPOINTS,
    #     rule=lambda m, b, t: sum(
    #         getattr(m, requirement)[b, t]
    #         for requirement in m.Spinning_Reserve_Down_Requirements
    #     )
    #     <= sum(
    #         getattr(m, provision)[b, t]
    #         for provision in m.Spinning_Reserve_Down_Provisions
    #     ),
    # )

def load_inputs(m, switch_data, inputs_dir):
    """
    All files & columns are optional.

    gen_info.csv
        GENERATION_PROJECTS, ... gen_can_provide_spinning_reserves

    spinning_reserve_params.csv may override the default value of
    contingency_safety_factor. Note that this only contains one
    header row and one data row.
    """
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "gen_info.csv"),
        optional_params=["gen_can_provide_spinning_reserves"],
        param=(m.gen_can_provide_spinning_reserves),
    )
    
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "str_info.csv"),
        optional_params=["str_can_provide_spinning_reserves"],
        param=(m.str_can_provide_spinning_reserves),
    )
