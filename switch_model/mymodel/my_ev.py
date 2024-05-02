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
    mod.ELECRRIC_VEHICLE=Set(
        initialize=mod.GENERATION_PROJECTS,
        dimen=1,
        filter=lambda m, g: m.gen_is_distributed[g]
    )
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
                z2 = m.gen_load_zone[g]
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
                z2 = m.gen_load_zone[g]
                m.Ev_Discharge_Summation_dict[z2,t2].add(g)
        # Use pop to free memory
        relevant_projects = m.Ev_Discharge_Summation_dict.pop((z, t), {})
        return sum(m.DischargingPower[g, t] for g in relevant_projects)

    mod.EvDischargePower = Expression(mod.LOAD_ZONES, mod.TIMEPOINTS, rule=rule1)
    mod.Distributed_Power_Injections.append("EvDischargePower")
    #####################################################################
    
    
    
    
    
    #######################      电池状态约束      #######################
    mod.StateOfChargeOfEV = Var(mod.ELECRRIC_VEHICLE_TIMEPOINTS, within=NonNegativeReals)
    
    # 电动汽车的电量需要 小于 电池最大容量
    mod.State_Of_Charge_Upper_Limit_of_Ev_A = Constraint(
        mod.ELECRRIC_VEHICLE_TIMEPOINTS, 
        rule=lambda m, g, t: m.StateOfChargeOfEV[g, t] <= m.gen_capacity_limit_mw[g] * m.ev_max_soc[g]
    )
    
    # 电动汽车的电量需要 大于 最小值
    mod.State_Of_Charge_Upper_Limit_of_Ev_B = Constraint(
        mod.ELECRRIC_VEHICLE_TIMEPOINTS, 
        rule=lambda m, g, t: m.StateOfChargeOfEV[g, t] >= m.gen_capacity_limit_mw[g] * m.ev_min_soc[g]
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
        if t == "2025.01.22.00":
        # 设置为初始状态
            return m.StateOfChargeOfEV[g, t] == m.initial_state_of_ev[g] + (
                m.ChargingPower[g, t] * m.gen_storage_efficiency[g]
                - m.DischargingPower[g, t] - m.ev_driving_power[g, t]
            )* m.tp_duration_hrs[t]

        return (
            m.StateOfChargeOfEV[g, t]                                                                                                                                                                                                                                                                       
            == m.StateOfChargeOfEV[g, m.tp_previous[t]]
            + (
                m.ChargingPower[g, t] * m.gen_storage_efficiency[g]
                - m.DischargingPower[g, t] - m.ev_driving_power[g, t]
            )
            * m.tp_duration_hrs[t]
        )

    mod.Track_State_Of_Charge_Of_EV = Constraint(
        mod.ELECRRIC_VEHICLE_TIMEPOINTS, rule=Track_State_Of_Charge_rule_of_EV
    )
    #####################################################################

    
def load_inputs(mod, switch_data, inputs_dir):    
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "ev_power_parameters.csv"),
        param=(
            mod.ev_max_power_mw,
            mod.ev_driving_power
        )
    )
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "ev_initialize_soc.csv"),
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
            m.gen_load_zone[g],
            m.EvCharge[g, t],
            m.ChargingPower[g, t],
            m.EvDischarge[g, t],
            m.DischargingPower[g, t],
            m.StateOfChargeOfEV[g, t]
        ),
    )