from pyomo.environ import *
import os, collections

dependencies = (
    "switch_model.generators.core.build",
    "switch_model.timescales"
    "switch_model.balancing.load_zones",
    "switch_model.generators.extensions.storage",
    "switch_model.financials",
)
def define_components(mod):
    ###########################   电动汽车模块目标、参数、变量定义   #######################
    mod.ELECRRIC_VEHICLE=Set(dimen=1)
    # 定义一个电动汽车和时间点的集合
    mod.ELECRRIC_VEHICLE_TIMEPOINTS = Set(
        dimen=2,
        initialize=lambda m: m.ELECRRIC_VEHICLE * m.TIMEPOINTS,
        doc="The cross product of evs and timepoints, used for indexing.",
    )
    
    # 它是一组参数，这个最大充放电功率
    mod.ev_max_power_mw=Param(
        mod.ELECRRIC_VEHICLE_TIMEPOINTS,
        within=NonNegativeReals,
    )
    # 这个是电池soc的参数
    mod.ev_min_soc=Param(
        mod.ELECRRIC_VEHICLE,
        within=NonNegativeReals,
        default=0.2  
    )
    mod.ev_max_soc=Param(
        mod.ELECRRIC_VEHICLE,
        within=NonNegativeReals,
        default=1  
    )
    mod.ev_capacity_limit_mw = Param(
        mod.ELECRRIC_VEHICLE, within=NonNegativeReals
    )
    mod.ev_storage_efficiency = Param(mod.ELECRRIC_VEHICLE, within=PercentFraction)
    # 实时电价
    mod.electricity_price=Param(
        mod.TIMEPOINTS,
        within=NonNegativeReals
    )
    # 行驶功率
    mod.ev_driving_power=Param(
        mod.ELECRRIC_VEHICLE_TIMEPOINTS,
        within=NonNegativeReals,
    )
    
    mod.initial_state_of_ev=Param(
        mod.ELECRRIC_VEHICLE,
        within=NonNegativeReals
    )
    
    # 二进制变量约束电动汽车是否充放电
    mod.EvCharge = Var(
        mod.ELECRRIC_VEHICLE_TIMEPOINTS,
        within=Binary
    )
    
    mod.EvDischarge = Var(
        mod.ELECRRIC_VEHICLE_TIMEPOINTS,
        within=Binary
    )
    # 电动汽车在每个时间点的充放电功率
    mod.ChargingPower=Var(
        mod.ELECRRIC_VEHICLE_TIMEPOINTS,
        within=NonNegativeReals
    )
    
    mod.DischargingPower=Var(
        mod.ELECRRIC_VEHICLE_TIMEPOINTS,
        within=NonNegativeReals
    )
    # # 定义每个省电动汽车充电桩集合，需要age、zone、建立限制
    # mod.CHARGING_STATION=Set(dimen=1)
    # # TODO 输入参数 limit
    # mod.sta_num_limit=Param(mod.CHARGING_STATION, within=PositiveIntegers)    
    # # TODO 输入参数 age
    # mod.sta_max_age = Param(mod.CHARGING_STATION, within=PositiveIntegers)    
    # # TODO 输入参数 load zone
    # mod.sta_load_zone = Param(mod.CHARGING_STATION, within=mod.LOAD_ZONES)
    
    # #  TODO，这个集合需要输入，成本
    # mod.STA_BLD_YRS = Set(
    #     dimen=2,
    #     validate=lambda m, g, bld_yr: (
    #     (g, bld_yr) in m.CHARGING_STATION * m.PERIODS
    #     ),
    # )
    # #
    # def sta_build_can_operate_in_period(m, g, build_year, period):
    #     if build_year in m.PERIODS:
    #         online = m.period_start[build_year]
    #     else:
    #         online = build_year
    #     retirement = online + m.sta_max_age[g]
    #     return online <= m.period_start[period] < retirement

    # mod.BLD_YRS_FOR_STA_PERIOD = Set(
    #     mod.CHARGING_STATION,
    #     mod.PERIODS,
    #     dimen=1,
    #     initialize=lambda m, g, period: unique_list(
    #         bld_yr
    #         for (gen, bld_yr) in m.STA_BLD_YRS
    #         if gen == g and sta_build_can_operate_in_period(m, g, bld_yr, period)
    #     ),
    # )    
    # # 对每个g和bld-yr决策一个是否要建立新的容量。TODO 这东西嘚是整数
    # mod.BuildStation = Var(mod.STA_BLD_YRS, within=PositiveIntegers)
    # # 累计充电桩数量
    # mod.StaNum = Expression(
    #     mod.CHARGING_STATION,
    #     mod.PERIODS,
    #     rule=lambda m, g, period: sum(
    #         m.BuildStation[g, bld_yr] for bld_yr in m.BLD_YRS_FOR_STA_PERIOD[g, period]
    #     ),
    # )
    # mod.Max_Build_Potential_For_Station = Constraint(
    #     mod.CHARGING_STATION,
    #     mod.PERIODS,
    #     rule=lambda m, g, p: (m.sta_num_limit[g] >= m.StaNum[g, p]),
    # )
    # # 电动汽车可以使用v2g的容量
    # mod.V2gNum=Expression(
    #     mod.CHARGING_STATION,
    #     mod.PERIODS,
    #     rule=lambda m, g, period: ( m.StaNum[g,period]*70*3/1000),
    #     )
    # # 电动汽车最大充放电功率，还要在这个基础上x当前的ev status
    

    #############################################################################

    # TODO
    mod.ev_load_zone = Param(mod.ELECRRIC_VEHICLE, within=mod.LOAD_ZONES)
    def EV_IN_ZONE_init(m, z):
        if not hasattr(m, "EV_IN_ZONE_dict"):
            m.EV_IN_ZONE_dict = {_z: [] for _z in m.LOAD_ZONES}
            for g in m.ELECRRIC_VEHICLE:
                m.EV_IN_ZONE_dict[m.ev_load_zone[g]].append(g)
        result = m.EV_IN_ZONE_dict.pop(z)
        if not m.EV_IN_ZONE_dict:
            del m.EV_IN_ZONE_dict
        return result
    
    # 输入z可以得到上面所有的ev
    mod.EV_IN_ZONE = Set(mod.LOAD_ZONES, dimen=1, initialize=EV_IN_ZONE_init)
    
    #######################    电网购电成本优化目标    ########################
    # def r(m, t):
    #     # 在每个时间点计算所有车的price * DischargingPower * mod.tp_duration_hrs
    #     # 只有EvDischarge为1的时候，DischargingPower才不是0，所以可以直接全部加起来
    #     return sum([m.electricity_price[t] * m.DischargingPower[g, t] * m.tp_duration_hrs[t] * 1000
    #                 for g in m.ELECRRIC_VEHICLE])
    
    # mod.ElectricityPurchasingCost=Expression(mod.TIMEPOINTS, rule=r)
    # mod.Cost_Components_Per_TP.append("ElectricityPurchasingCost")
    #####################################################################
    
    
    ########################    分布式节点功率平衡约束   #########################
    # 把想要的时间点和区域的电动汽车的功率挑出来，做了个累加，计入分布式注入
    def rule(m, z, t):
        if not hasattr(m, "Ev_Charge_Summation_dict"):
            m.Ev_Charge_Summation_dict = collections.defaultdict(set)
            for g ,t2 in m.ELECRRIC_VEHICLE_TIMEPOINTS:
                z2 = m.ev_load_zone[g]
                m.Ev_Charge_Summation_dict[z2,t2].add(g)
        # Use pop to free memory
        relevant_projects = m.Ev_Charge_Summation_dict.pop((z, t), {})
        return sum(m.ChargingPower[g, t] for g in relevant_projects)

    mod.EvChargePower = Expression(mod.LOAD_ZONES, mod.TIMEPOINTS, rule=rule)
    mod.Distributed_Power_Withdrawals.append("EvChargePower") 
    #####################################################################
    
    
    
    
    
    #######################    功率平衡约束    ########################
    def rule1(m, z, t):
        if not hasattr(m, "Ev_Discharge_Summation_dict"):
            m.Ev_Discharge_Summation_dict = collections.defaultdict(set)
            for g ,t2 in m.ELECRRIC_VEHICLE_TIMEPOINTS:
                z2 = m.ev_load_zone[g]
                m.Ev_Discharge_Summation_dict[z2,t2].add(g)
        # Use pop to free memory
        relevant_projects = m.Ev_Discharge_Summation_dict.pop((z, t), {})
        return sum(m.DischargingPower[g, t] for g in relevant_projects)

    mod.EvDischargePower = Expression(mod.LOAD_ZONES, mod.TIMEPOINTS, rule=rule1)
    mod.Distributed_Power_Injections.append("EvDischargePower")
    #####################################################################
    
    
    
    
    
    #######################      电池状态约束      #######################
    mod.StateOfChargeOfEV = Var(mod.ELECRRIC_VEHICLE_TIMEPOINTS, within=NonNegativeReals)
    # TODO
    # 电动汽车的电量需要 小于 电池最大容量
    mod.State_Of_Charge_Upper_Limit_of_Ev_A = Constraint(
        mod.ELECRRIC_VEHICLE_TIMEPOINTS, 
        rule=lambda m, g, t: m.StateOfChargeOfEV[g, t] <= m.ev_capacity_limit_mw[g] * m.ev_max_soc[g]
    )
    
    # 电动汽车的电量需要 大于 最小值
    mod.State_Of_Charge_Upper_Limit_of_Ev_B = Constraint(
        mod.ELECRRIC_VEHICLE_TIMEPOINTS, 
        rule=lambda m, g, t: m.StateOfChargeOfEV[g, t] >= m.ev_capacity_limit_mw[g] * m.ev_min_soc[g]
    )
    #####################################################################
    
    
    
    
    #######################   电动汽车充电功率约束   #######################
    # 电动汽车充电功率需要小于最大充电功率 * 是否在充电
    #   如果正在充电，那么就 <= [最大充电功率]
    #   如果不在充电，就会 <= [最大充电功率 * 0]，也就是 <= 0，但是充电功率定义的是非负值，因此就等于0
    mod.Charging_Power_Constraint = Constraint(
        mod.ELECRRIC_VEHICLE_TIMEPOINTS,
        rule=lambda m, g, t:m.ChargingPower[g, t] <= m.ev_max_power_mw[g, t] * m.EvCharge[g, t]
    )
    #####################################################################
    
    
    
    
    #######################   电动汽车放电功率约束   #######################
    # 电动汽车充电功率需要小于最大放电功率 * 是否在放电
    #   如果正在放电，那么就 <= [最大放电功率]
    #   如果不在放电，就会 <= [最大放电功率 * 0]，也就是 <= 0，但是放电功率定义的是非负值，因此就等于0
    def Discharging_Power_Constraint_rule(m, g, t):
        return m.DischargingPower[g, t] <= m.ev_max_power_mw[g, t] * m.EvDischarge[g, t]
    
    mod.Discharging_Power_Constraint = Constraint(
        mod.ELECRRIC_VEHICLE_TIMEPOINTS,
        rule=Discharging_Power_Constraint_rule
    )
    #####################################################################
    
    
    ####################### 充放电约束（二进制变量）#######################
    # 电动汽车只能处于三个状态，充电、放电、不充不放
    
    # 是否充电 + 是否放电 >= 0，表示两个二进制变量可以都为0，也可以都不为0
    mod.Charge_or_Discharge_Constraint_A = Constraint(
        mod.ELECRRIC_VEHICLE_TIMEPOINTS,
        rule=lambda m, g, t: m.EvCharge[g, t] + m.EvDischarge[g, t] >= 0
    )
    
    # 是否充电 + 是否放电 <= 1，表示两个二进制变量只能有一个是1，不能同时为1
    mod.Charge_or_Discharge_Constraint_B = Constraint(
        mod.ELECRRIC_VEHICLE_TIMEPOINTS,
        rule=lambda m, g, t: m.EvCharge[g, t] + m.EvDischarge[g, t] <= 1
    )
    #####################################################################
    
    
    ############################    其他   #############################
    """
    在"switch_model.generators.extensions.storage"中，一些约束不适用于电动汽车，
    因此从该模块中的所有约束目标中，将电动汽车直接排除了。
    
    但是下面这个约束适用于电动汽车，因此这里需要单独为电动汽车重新写一遍这个约束。
    """
    
    def Track_State_Of_Charge_rule_of_EV(m, g, t):
        # if t == "2025.01.22.00":
        # # 设置为初始状态
        #     return m.StateOfChargeOfEV[g, t] == m.initial_state_of_ev[g] + (
        #         m.ChargingPower[g, t] * m.ev_storage_efficiency[g]
        #         - m.DischargingPower[g, t] - m.ev_driving_power[g, t]
        #     )* m.tp_duration_hrs[t]

        return (
            m.StateOfChargeOfEV[g, t]                                                                                                                                                                                                                                                                       
            == m.StateOfChargeOfEV[g, m.tp_previous[t]]
            + (
                m.ChargingPower[g, t] * m.ev_storage_efficiency[g]
                - m.DischargingPower[g, t] - m.ev_driving_power[g, t]
            )
            * m.tp_duration_hrs[t]
        )

    mod.Track_State_Of_Charge_Of_EV = Constraint(
        mod.ELECRRIC_VEHICLE_TIMEPOINTS, rule=Track_State_Of_Charge_rule_of_EV
    )
    
    ###收益约束
    def Revenue_Requirements_rule(m, z):
        discharge_sum = 0
        charge_sum = 0
        for t in m.TIMEPOINTS:
            for g in m.DISSTORAGE_IN_ZONE[z]:
                discharge_sum += m.DischargeStorage[g, t] * m.electricity_price[t]
            for ev in m.EV_IN_ZONE[z]:
                discharge_sum += m.DischargingPower[ev, t] * m.electricity_price[t]
        
        for t in m.TIMEPOINTS:
            for g in m.DISSTORAGE_IN_ZONE[z]:
                charge_sum += m.ChargeStorage[g, t] * m.electricity_price[t]
            for ev in m.EV_IN_ZONE[z]:
                charge_sum += m.ChargingPower[ev, t] * m.electricity_price[t]
        return discharge_sum >= charge_sum
    
    mod.Revenue_Requirements_constraint = Constraint(
        mod.LOAD_ZONES, rule=Revenue_Requirements_rule
    )
    
    #####################################################################

    
def load_inputs(mod, switch_data, inputs_dir):    
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "ev_info.csv"),
        index=mod.ELECRRIC_VEHICLE,
        param=(
            mod.ev_load_zone,
            mod.ev_capacity_limit_mw,
            mod.ev_storage_efficiency
            )
    )
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "ev_power_parameters.csv"),
        param=(
            mod.ev_max_power_mw,
            mod.ev_driving_power
        )
    )
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "ev_init_soc.csv"),
        param=mod.initial_state_of_ev
    )
    
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "ev_electricity_price.csv"),
        param=mod.electricity_price
    )
    
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "ev_min_max_soc.csv"),
        param=(
            mod.ev_min_soc,
            mod.ev_max_soc
        )
    )

def post_solve(instance, outdir):
    """
    Export storage dispatch info to storage_dispatch.csv

    Note that construction information is reported by the generators.core.build
    module, so is not reported here.
    """
    import switch_model.reporting as reporting

    reporting.write_table(
        instance,
        instance.ELECRRIC_VEHICLE_TIMEPOINTS,
        output_file=os.path.join(outdir, "ev_result.csv"),
        headings=(
            "ev_project",
            "timepoint",
            "load_zone",
            "ev_charge",
            "charging_power",
            "ev_discharge",
            "discharging_power",
            "state_charge_of_ev"
        ),
        values=lambda m, g, t: (
            g,
            m.tp_timestamp[t],
            m.ev_load_zone[g],
            m.EvCharge[g, t],
            m.ChargingPower[g, t],
            m.EvDischarge[g, t],
            m.DischargingPower[g, t],
            m.StateOfChargeOfEV[g, t]
        ),
    )