from pyomo.environ import *
import os, collections
from switch_model.financials import capital_recovery_factor as crf
from switch_model.utilities import unique_list

dependencies = (
    "switch_model.timescales",
    "switch_model.balancing.load_zones",
    "switch_model.financials",
    "switch_model.energy_sources.properties",
    "switch_model.mymodel.merge",
)
# 关键是设定新建容量，调度情况，
def define_components(mod):

    # 储能设施集合，是根据储能效率来识别储能的g
    mod.STORAGE_GENS = Set(dimen=1)
    mod.str_storage_efficiency = Param(mod.STORAGE_GENS, within=PercentFraction) 
    mod.PREDETERMINED_STR_BLD_YRS = Set(dimen=2)

    #####
    mod.build_str_energy_predetermined = Param(
        mod.PREDETERMINED_STR_BLD_YRS, within=NonNegativeReals
    )
    # mod.min_data_check("build_str_predetermined")    
    mod.str_max_age = Param(mod.STORAGE_GENS, within=PositiveIntegers)
    
    mod.str_is_distributed = Param(
        mod.STORAGE_GENS, within=Boolean, default=False
    )
    mod.str_is_reconnected = Param(
        mod.STORAGE_GENS, within=Boolean, default=False
    )
    mod.str_is_grid_connected = Param(
        mod.STORAGE_GENS, within=Boolean, default=False
    )

    # 这是一个gen和build year的合集，是具有输入的，
    # 筛选掉在决策期之外的g和bld-yr
    mod.STR_BLD_YRS = Set(
        dimen=2,
        validate=lambda m, g, bld_yr: (
            (g, bld_yr) in m.PREDETERMINED_STR_BLD_YRS
            or (g, bld_yr) in m.STORAGE_GENS * m.PERIODS
        ),
    )
    # 就是mod.STORAGE_GEN_BLD_YRS 

    # 这是确定一个在哪个投资period里能用的规则，如果在这个period里上线，上线时间就算这个周期的开始时间
    def str_build_can_operate_in_period(m, g, build_year, period):
        if build_year in m.PERIODS:
            online = m.period_start[build_year]
        else:
            online = build_year
        retirement = online + m.str_max_age[g]
        return online <= m.period_start[period] < retirement

    #输入g，p得到项目在线的bld yr。要么就是真是建立的那年，要么就是决策的period年份，period开始年份
    mod.BLD_YRS_FOR_STR_PERIOD = Set(
        mod.STORAGE_GENS,
        mod.PERIODS,
        dimen=1,
        initialize=lambda m, g, period: unique_list(
            bld_yr
            for (gen, bld_yr) in m.STR_BLD_YRS
            if gen == g and str_build_can_operate_in_period(m, g, bld_yr, period)
        ),
    )

    # 储能新建容量的约束
    def bounds_BuildStorageEnergy(m, g, bld_yr):
        if (g, bld_yr) in m.build_str_energy_predetermined:
            return (
                m.build_str_energy_predetermined[g, bld_yr],
                m.build_str_energy_predetermined[g, bld_yr],
            )
        else:
            return (0, None)
        
    # 决策了新建的储能容量
    mod.BuildStorageEnergy = Var(
        mod.STR_BLD_YRS,
        within=NonNegativeReals,
        bounds=bounds_BuildStorageEnergy,
    )
    
    # 当前储能的累计容量
    mod.StorageEnergyCapacity = Expression(
        mod.STORAGE_GENS,
        mod.PERIODS,
        rule=lambda m, g, period: sum(
            m.BuildStorageEnergy[g, bld_yr]
            for bld_yr in m.BLD_YRS_FOR_STR_PERIOD[g, period]
        ),
    )
    #############到这里决策变量就设置完了

    # 对所有的g，循环period，其中能够有用的period集合
    # 针对所有的g，得到的能够在线的period
    mod.PERIODS_FOR_STR = Set(
        mod.STORAGE_GENS,
        dimen=1,
        initialize=lambda m, g: [
            p for p in m.PERIODS if len(m.BLD_YRS_FOR_STR_PERIOD[g, p]) > 0
        ],
    )
    # （g,p）,这个g和它所有在线p的集合
    mod.STR_PERIODS = Set(
        dimen=2,
        initialize=lambda m: [
            (g, p) for g in m.STORAGE_GENS for p in m.PERIODS_FOR_STR[g]
        ],
    )
    # 就是mod.STORAGE_GEN_PERIODS
    
    # 储能项目在线的所有时间点    
    mod.TPS_FOR_STR = Set(
        mod.STORAGE_GENS,
        dimen=1,
        within=mod.TIMEPOINTS,
        initialize=lambda m, g: (
            tp for p in m.PERIODS_FOR_STR[g] for tp in m.TPS_IN_PERIOD[p]
        ),
    )
    # 一个可用的g和时间点的集合（g,tp）
    mod.STR_TPS = Set(
        dimen=2,
        initialize=lambda m: (
            (g, tp) for g in m.STORAGE_GENS for tp in m.TPS_FOR_STR[g]
        ),
    )
    # 就是mod.STORAGE_GEN_TPS

    #####开始定义充放电量,和电池状态
    mod.ChargeStorage = Var(mod.STR_TPS, within=NonNegativeReals)
    mod.DischargeStorage=Var(mod.STR_TPS, within=NonNegativeReals)
    mod.StateOfCharge = Var(mod.STR_TPS, within=NonNegativeReals)
    
    mod.StorageCharge = Var(
        mod.STR_TPS,
        within=Binary
    )
    
    mod.StorageDischarge = Var(
        mod.STR_TPS,
        within=Binary
    )
    # 充电功率约束
    # 存储项目的最大充放电功率
    # mod.storage_max_power_mw = Param(
    #     mod.STORAGE_GENS, within=NonNegativeReals
    # )

    # def Charge_Storage_Upper_Limit_rule(m, g, t):
    #     return (
    #         m.ChargeStorage[g, t]
    #         <= m.storage_max_power_mw[g] * m.StorageCharge[g, t]
    #     )

    # mod.Charge_Storage_Upper_Limit = Constraint(
    #     mod.STR_TPS, rule=Charge_Storage_Upper_Limit_rule
    # )
    # def Discharge_Storage_Upper_Limit_rule(m, g, t):
    #     return (
    #         m.DischargeStorage[g, t]
    #         <= m.storage_max_power_mw[g] * m.StorageDischarge[g, t]
    #     )

    # mod.Discharge_Storage_Upper_Limit = Constraint(
    #     mod.STR_TPS, rule=Discharge_Storage_Upper_Limit_rule
    # )
    
    #####重新写一下这个存储的规则 
    
    # TODO
    mod.str_is_baseload = Param(mod.STORAGE_GENS, within=Boolean, default=False)
    mod.str_max_commit_fraction = Param(
        mod.STR_TPS, within=PercentFraction, default=lambda m, g, t: 1.0
    )
    mod.str_min_commit_fraction = Param(
        mod.STR_TPS, within=PercentFraction, default=lambda m, g, t: 0.0
    )
    # 这一大串都是为了commit的上下限。
    mod.str_scheduled_outage_rate = Param(
        mod.STORAGE_GENS, within=PercentFraction, default=0
    )
    mod.str_forced_outage_rate = Param(
        mod.STORAGE_GENS, within=PercentFraction, default=0
    )
    mod.StorageEnergyCapacityInTP = Expression(
        mod.STR_TPS, rule=lambda m, g, t: m.StorageEnergyCapacity[g, m.tp_period[t]]
    )      
    # 强制停运率和计划停运率，在gen info里输入
    def init_str_availability(m, g):
        if m.str_is_baseload[g]:
            return (1 - m.str_forced_outage_rate[g]) * (
                1 - m.str_scheduled_outage_rate[g]
            )
        else:
            return 1 - m.str_forced_outage_rate[g]

    mod.str_availability = Param(
        mod.STORAGE_GENS,
        within=NonNegativeReals,
        initialize=init_str_availability,
    )
        
    mod.CommitLowerLimit1 = Expression(
        mod.STR_TPS,
        rule=lambda m, g, t: (
            m.StorageEnergyCapacityInTP[g, t]
            * m.str_availability[g]
            * m.str_min_commit_fraction[g, t]
        ),
    )
    # 充放电最大功率按照，储能当前时间点累计容量的0.25设置
    mod.CommitUpperLimit2 = Expression(
        mod.STR_TPS,
        rule=lambda m, g, t: (
            m.StorageEnergyCapacityInTP[g, t]
            * m.str_availability[g]
            * m.str_max_commit_fraction[g, t]
            * 0.25
        ),
    )
    ###### 放电功率约束 大于0，小于累计容量*0.25，
    mod.Enforce_Dis_Lower_Limit1 = Constraint(
        mod.STR_TPS,
        rule=lambda m, g, t: (m.CommitLowerLimit1[g, t] <= m.DischargeStorage[g, t]),
    )
    mod.Enforce_Dis_Upper_Limit2 = Constraint(
        mod.STR_TPS,
        rule=lambda m, g, t: (m.DischargeStorage[g, t] <= m.CommitUpperLimit2[g, t]),
    ) 
    # 充电功率约束 同理
    mod.Enforce_Char_Lower_Limit1 = Constraint(
        mod.STR_TPS,
        rule=lambda m, g, t: (m.CommitLowerLimit1[g, t] <= m.ChargeStorage[g, t]),
    )
    mod.Enforce_Char_Upper_Limit2 = Constraint(
        mod.STR_TPS,
        rule=lambda m, g, t: (m.ChargeStorage[g, t] <= m.CommitUpperLimit2[g, t]),
    )
    
    # 是否充电 + 是否放电 >= 0，表示两个二进制变量可以都为0，也可以都不为0
    # 如果m.DischargeStorage[g, t]=0，则m.StorageDischarge[g, t]=0
    # 如果m.ChargeStorage[g, t]=0，则m.StorageCharge[g, t]=0
    
    def tmp_discharge_constraint(m, g, t):
        M = 1000000
        return m.DischargeStorage[g, t] <= M * m.StorageDischarge[g, t]
        
    mod.EnsureDischargeState_Constraint = Constraint(
        mod.STR_TPS, rule=tmp_discharge_constraint
    )
    
    def tmp_charge_constraint(m, g, t):
        M = 1000000
        return m.ChargeStorage[g, t] <= M * m.StorageCharge[g, t]
        
    mod.EnsureChargeState_Constraint = Constraint(
        mod.STR_TPS, rule=tmp_charge_constraint
    )
    
    mod.Charge_or_Discharge_Constraint_1 = Constraint(
        mod.STR_TPS,
        rule=lambda m, g, t: m.StorageCharge[g, t] + m.StorageDischarge[g, t] >= 0
    )
    
    # 是否充电 + 是否放电 <= 1，表示两个二进制变量只能有一个是1，不能同时为1
    mod.Charge_or_Discharge_Constraint_2 = Constraint(
        mod.STR_TPS,
        rule=lambda m, g, t: m.StorageCharge[g, t] + m.StorageDischarge[g, t] <= 1
    )
    
    ######
    # 这个是一个关键，就是状态跟踪
    def Track_State_Of_Charge_rule(m, g, t):
        return (
            m.StateOfCharge[g, t]
            == m.StateOfCharge[g, m.tp_previous[t]]
            + (
                m.ChargeStorage[g, t] * m.str_storage_efficiency[g]
                - m.DischargeStorage[g, t] / m.str_storage_efficiency[g]
            )
            * m.tp_duration_hrs[t]
        )

    mod.Track_State_Of_Charge = Constraint(
        mod.STR_TPS, rule=Track_State_Of_Charge_rule
    )
    # 这个约束很合理，就是电池状态不能超过累积容量
    def State_Of_Charge_Upper_Limit_rule(m, g, t):
        return m.StateOfCharge[g, t] <= m.StorageEnergyCapacity[g, m.tp_period[t]]

    mod.State_Of_Charge_Upper_Limit = Constraint(
        mod.STR_TPS, rule=State_Of_Charge_Upper_Limit_rule
    )

    ########
    # 三种电池的区别，gen is re- connected，gen is gird-connected，gen is distributed

    # 可再生能源强制配储：充电量不能超过当前可再生能源的发电量，平衡约束在中心节点上
    mod.str_load_zone = Param(mod.STORAGE_GENS, within=mod.LOAD_ZONES)
    def STR_IN_ZONE_init(m, z):
        if not hasattr(m, "STR_IN_ZONE_dict"):
            m.STR_IN_ZONE_dict = {_z: [] for _z in m.LOAD_ZONES}
            for g in m.STORAGE_GENS:
                m.STR_IN_ZONE_dict[m.str_load_zone[g]].append(g)
        result = m.STR_IN_ZONE_dict.pop(z)
        if not m.STR_IN_ZONE_dict:
            del m.STR_IN_ZONE_dict
        return result

    mod.STR_IN_ZONE = Set(mod.LOAD_ZONES, dimen=1, initialize=STR_IN_ZONE_init)
    
    mod.RESTORAGE = Set(
        initialize=mod.STORAGE_GENS,
        dimen=1,      
        filter=lambda m, g: m.str_is_reconnected[g]
    )
    mod.RESTORAGE_IN_ZONE = Set(
        mod.LOAD_ZONES,
        dimen=1,
        initialize=lambda m, z: [g for g in m.STR_IN_ZONE[z] if m.str_is_reconnected[g]],
    )
    mod.str_tech = Param(mod.STORAGE_GENS, within=Any)
    def battery_rule(m, z, t):
        # Construct and cache a set for summation as needed
        if not hasattr(m, 'Battery_Storage_Central_Charge_Summation_dict'):
            m.Battery_Storage_Central_Charge_Summation_dict = collections.defaultdict(set)
            for g, t2 in m.STR_TPS:
                if m.str_tech[g] == "Battery_Storage" and m.str_is_reconnected[g]:
                    z2 = m.str_load_zone[g]
                    m.Battery_Storage_Central_Charge_Summation_dict[z2, t2].add(g)
        # Use pop to free memory
        relevant_projects = m.Battery_Storage_Central_Charge_Summation_dict.pop((z, t), {})
        return sum(m.ChargeStorage[g, t] for g in relevant_projects)
    mod.REBatteryCentralCharge = Expression(mod.LOAD_ZONES, mod.TIMEPOINTS, rule=battery_rule)   

    mod.Renewable_GEN_TPS = Set(
        dimen=2,
        initialize=lambda m: (
            (g, tp)
                for g in m.VARIABLE_GENS
                    for tp in m.TPS_FOR_GEN[g]))

    def rule(m, z, t):
        if not hasattr(m, 'Renewable_Gen_Summation_dict'):
            m.Renewable_Gen_Summation_dict = collections.defaultdict(set)
            for g, t2 in m.Renewable_GEN_TPS:
                z2 = m.gen_load_zone[g]
                m.Renewable_Gen_Summation_dict[z2, t2].add(g)
        # Use pop to free memory
        relevant_projects = m.Renewable_Gen_Summation_dict.pop((z, t), {})
        return sum(m.DispatchGen[g, t] for g in relevant_projects)
    mod.RenewableDispatchZone = Expression(mod.LOAD_ZONES, mod.TIMEPOINTS, rule=rule)

    mod.Charge_Storage_Upper_Limit_Zone = Constraint(
        mod.ZONE_TIMEPOINTS,
        rule=lambda m, z, t:
            m.REBatteryCentralCharge[z, t] <= m.RenewableDispatchZone[z, t] 
    )
    
    # 按照可再生能源建造量的0.05来建立新能源配储，其实wind和solar就是variablegen
    def RE_Constraint(m, str, bld_yr):
        if m.str_is_reconnected[str]:
            z = m.str_load_zone[str]
            s = 0
            for g, bld_yr_g in m.NEW_GEN_BLD_YRS:
                if bld_yr == bld_yr_g and m.gen_load_zone[g] == z and m.gen_energy_source[g] in ['Solar', 'Wind']:
                    s += m.BuildGen[g, bld_yr]
            return m.BuildStorageEnergy[str, bld_yr] == s * 0.05
        else:
            return Constraint.Skip

    mod.RE_Build_Capacity_Constraint = Constraint(
        mod.STR_BLD_YRS, rule=RE_Constraint
    )
    
    # 电网侧储能：能够提供旋转储备，平衡约束在中心节点上
    mod.GRIDSTORAGE = Set(
        initialize=mod.STORAGE_GENS,
        dimen=1,
        filter=lambda m, g: m.str_is_grid_connected[g]
    )
    # 输入z得到z上的电网侧储能
    mod.GRIDSTORAGE_IN_ZONE = Set(
        mod.LOAD_ZONES,
        dimen=1,
        initialize=lambda m, z: [g for g in m.STR_IN_ZONE[z] if m.str_is_grid_connected[g]],
    )
    # 一个可用的g和时间点的集合（g,tp）
    mod.GRIDSTORAGE_TPS = Set(
        dimen=2,
        initialize=lambda m: (
            (g, tp) for g in m.GRIDSTORAGE for tp in m.TPS_FOR_STR[g]
        ),
    )   
    # 新设置一个非需求端储能的集合，即源网侧储能集合
    mod.RE_WITH_GRIDSTORAGE=Set(
        initialize=mod.STORAGE_GENS,
        dimen=1,
        filter=lambda m, g : not m.str_is_distributed[g]
    )
    # 输入z得到z上的源网侧储能
    mod.RE_WITH_GRIDSTORAGE_IN_ZONE = Set(
        mod.LOAD_ZONES,
        dimen=1,
        initialize=lambda m, z: [g for g in m.STR_IN_ZONE[z] if not m.str_is_distributed[g]],
    )    
    # 一个可用的g和时间点的集合（g,tp）
    mod.RE_WITH_GRIDSTORAGE_TPS = Set(
        dimen=2,
        initialize=lambda m: (
            (g, tp) for g in m.RE_WITH_GRIDSTORAGE for tp in m.TPS_FOR_STR[g]
        ),
    ) 

    
    def init_gen_zone_timepoint(m):
        candidate = []
        for zone_from, zone_to in m.DIRECTIONAL_TX:
            for g in m.RE_WITH_GRIDSTORAGE_IN_ZONE[zone_from]:
                for t in m.TIMEPOINTS:
                    candidate.append((g, zone_to, t))
        return candidate
        
    mod.RE_WITH_GRIDGEN_ZONE_TIMEPOINTS = Set(
        initialize=init_gen_zone_timepoint,
        dimen=3
    )
    
    # 是不是用源网侧储能集合代替电网侧储能集合mod.RE_WITH_GRIDSTORAGE
    mod.GenDispatchStorage = Var(
        mod.RE_WITH_GRIDGEN_ZONE_TIMEPOINTS,
        within=NonNegativeReals
    )
    
    # mod.RE_WITH_GRIDSTORAGE_IN_ZONE,mod.RE_WITH_GRIDSTORAGE_TPS
    def exp111(m, zone_from, zone_to, tps):
        s = 0
        for g in m.RE_WITH_GRIDSTORAGE_IN_ZONE[zone_from]:
            if tps in m.TPS_FOR_STR[g]:
                s += m.GenDispatchStorage[g, zone_to, tps]
        return s
    
    # jiangxi -> anhui
    # g1 g2
    # dispatch[t] = dis[g1][anhui][t] + dis[g2][anhui][t]
    mod.DispatchStorage = Expression(
        mod.TRANS_TIMEPOINTS,
        rule=exp111
    )
    
    def rule138(m, z, t):
        sum_dispatch = 0
        sum_discharge = 0
        for zone_from, zone_to in m.DIRECTIONAL_TX:
            if zone_from == z:
                sum_dispatch += m.DispatchStorage[zone_from, zone_to, t]
        # mod.RE_WITH_GRIDSTORAGE_IN_ZONE
        for g in m.RE_WITH_GRIDSTORAGE_IN_ZONE[z]:
            if t in m.TPS_FOR_STR[g]:
                sum_discharge += m.DischargeStorage[g, t]
        return sum_dispatch <= sum_discharge
    
    mod.Constraint138=Constraint(
        mod.LOAD_ZONES,
        mod.TIMEPOINTS,
        rule=rule138
    )
    
    # 调度至其他区域的电量应该小于传输线路的容量
    mod.Maximum_DispatchStorage1 = Constraint(
        mod.TRANS_TIMEPOINTS,
        rule=lambda m, zone_from, zone_to, tp: (
            m.DispatchStorage[zone_from, zone_to, tp]+ m.DispatchTx[zone_from, zone_to, tp]
            <= m.TxCapacityNameplateAvailable[
                m.trans_d_line[zone_from, zone_to], m.tp_period[tp]
            ]
        ),
    )

    # 输入zone from和zone to，得到传输出去的量
    mod.StoragePowerSent = Expression(
        mod.TRANS_TIMEPOINTS,
        rule=lambda m, zone_from, zone_to, tp: (m.DispatchStorage[zone_from, zone_to, tp]),
    )
    # 收到的调度量等于传输的量还要x传输效率
    mod.StoragePowerReceived = Expression(
        mod.TRANS_TIMEPOINTS,
        rule=lambda m, zone_from, zone_to, tp: (
            m.DispatchStorage[zone_from, zone_to, tp]
            * m.trans_efficiency[m.trans_d_line[zone_from, zone_to]]
        ),
    )
    # 计算净传输到区域z的储能容量，等于所有从别的区域收到的传输量，减去区域z传输出去的量
    def StoragePowerNet_calculation(m, z, tp):
        return sum(
            m.StoragePowerReceived[zone_from, z, tp]
            for zone_from in m.TX_CONNECTIONS_TO_ZONE[z]
        ) - sum(
            m.StoragePowerSent[z, zone_to, tp] for zone_to in m.TX_CONNECTIONS_TO_ZONE[z]
        )

    mod.StoragePowerNet = Expression(
        mod.LOAD_ZONES, mod.TIMEPOINTS, rule=StoragePowerNet_calculation
    )
    mod.Zone_Power_Injections.append("StoragePowerNet") 

    # TODO 平衡约束还嘚改        
    ##########平衡约束
    # 区域z和时间点t上的储能净充电量，添加到区域平衡约束中，添加到中心节点的提取
    def rule1(m, z, t):
        # Construct and cache a set for summation as needed
        if not hasattr(m, "Storage_Charge_Summation_dict"):
            m.Storage_Charge_Summation_dict = collections.defaultdict(set)
            for g, t2 in m.STR_TPS:
                z2 = m.str_load_zone[g]
                m.Storage_Charge_Summation_dict[z2, t2].add(g)
        # Use pop to free memory
        relevant_projects = m.Storage_Charge_Summation_dict.pop((z, t), {})
        return sum(m.ChargeStorage[g, t] for g in relevant_projects if not m.str_is_distributed[g])

    mod.StorageNetCharge = Expression(mod.LOAD_ZONES, mod.TIMEPOINTS, rule=rule1)
    # Register net charging with zonal energy balance. Discharging is already
    # covered by DispatchGen.
    mod.Zone_Power_Withdrawals.append("StorageNetCharge")

    ################平衡约束
    # 区域z和时间点t上的储能净放电量，添加到中心节点的注入
    # def rule2(m, z, t):
    #     # Construct and cache a set for summation as needed
    #     if not hasattr(m, "Storage_DisCharge_Summation_dict"):
    #         m.Storage_DisCharge_Summation_dict = collections.defaultdict(set)
    #         for g, t2 in m.STR_TPS:
    #             z2 = m.str_load_zone[g]
    #             m.Storage_DisCharge_Summation_dict[z2, t2].add(g)
    #     relevant_projects = m.Storage_DisCharge_Summation_dict.pop((z, t), {})
    #     return sum(m.DischargeStorage[g, t] for g in relevant_projects if not m.str_is_distributed[g])

    # mod.StorageNetDisCharge = Expression(mod.LOAD_ZONES, mod.TIMEPOINTS, rule=rule2)
    # # Register net charging with zonal energy balance. Discharging is already
    # # covered by DispatchGen.
    # mod.Zone_Power_Injections.append("StorageNetDisCharge") 
#############   


    # 需求侧储能：削峰填谷，平衡约束在分布式节点上
    mod.DISSTORAGE = Set(
        initialize=mod.STORAGE_GENS,
        dimen=1,        
        filter=lambda m, g: m.str_is_distributed[g]
    )
    mod.DISSTORAGE_IN_ZONE = Set(
        mod.LOAD_ZONES,
        dimen=1,
        initialize=lambda m, z: [g for g in m.STR_IN_ZONE[z] if m.str_is_distributed[g]],
    )

    # 区域z和时间点t上的储能净充电量，添加到区域平衡约束中
    def rule3(m, z, t):
        # Construct and cache a set for summation as needed
        if not hasattr(m, "Storage_Charge_Summation_dict_1"):
            m.Storage_Charge_Summation_dict_1 = collections.defaultdict(set)
            for g, t2 in m.STR_TPS:
                z2 = m.str_load_zone[g]
                m.Storage_Charge_Summation_dict_1[z2, t2].add(g)
        # Use pop to free memory
        relevant_projects = m.Storage_Charge_Summation_dict_1.pop((z, t), {})
        return sum(m.ChargeStorage[g, t] for g in relevant_projects if  m.str_is_distributed[g])

    mod.StorageNetChargeforDis = Expression(mod.LOAD_ZONES, mod.TIMEPOINTS, rule=rule3)
    # Register net charging with zonal energy balance. Discharging is already
    # covered by DispatchGen.
    mod.Distributed_Power_Withdrawals.append("StorageNetChargeforDis")

    ################平衡约束
    # 区域z和时间点t上的储能净充电量，添加到区域平衡约束中
    def rule4(m, z, t):
        # Construct and cache a set for summation as needed
        if not hasattr(m, "Storage_DisCharge_Summation_dict_1"):
            m.Storage_DisCharge_Summation_dict_1 = collections.defaultdict(set)
            for g, t2 in m.STR_TPS:
                z2 = m.str_load_zone[g]
                m.Storage_DisCharge_Summation_dict_1[z2, t2].add(g)
        relevant_projects = m.Storage_DisCharge_Summation_dict_1.pop((z, t), {})
        return sum(m.DischargeStorage[g, t] for g in relevant_projects if m.str_is_distributed[g])

    mod.StorageNetDisChargeforDis = Expression(mod.LOAD_ZONES, mod.TIMEPOINTS, rule=rule4)
    # Register net charging with zonal energy balance. Discharging is already
    # covered by DispatchGen.
    mod.Distributed_Power_Injections.append("StorageNetDisChargeforDis")


    
    #############
    # 储能资本成本
    mod.str_overnight_cost = Param(
        mod.STR_BLD_YRS, within=NonNegativeReals
    )
    mod.str_connect_cost_per_mw = Param(
        mod.STORAGE_GENS, within=NonNegativeReals
    )    
    mod.min_data_check("str_overnight_cost")
        
    # 固定资本成本，这里有必要算上这个利率吗，还是目标函数里已经考虑了这种
    mod.StorageEnergyCapitalCost = Expression(
        mod.STORAGE_GENS,
        mod.PERIODS,
        rule=lambda m, g, p: sum(
            m.BuildStorageEnergy[g, bld_yr]
            * (m.str_overnight_cost[g, bld_yr] + m.str_connect_cost_per_mw[g])
            * crf(m.interest_rate, m.str_max_age[g])
            for bld_yr in m.BLD_YRS_FOR_STR_PERIOD[g, p]
        ),
    )
    mod.StorageEnergyFixedCost = Expression(
        mod.PERIODS,
        rule=lambda m, p: sum(m.StorageEnergyCapitalCost[g, p] for g in m.STORAGE_GENS),
    )
    mod.Cost_Components_Per_Period.append("StorageEnergyFixedCost")  

    # 固定运维成本
    mod.str_fixed_om = Param(mod.STR_BLD_YRS, within=NonNegativeReals)
    mod.StrOMCosts = Expression(
        mod.STORAGE_GENS,
        mod.PERIODS,
        rule=lambda m, g, p: sum(
            m.BuildStorageEnergy[g, bld_yr] * m.str_fixed_om[g, bld_yr]
            for bld_yr in m.BLD_YRS_FOR_STR_PERIOD[g, p]
        ),
    )  
    mod.StrFixedOMCosts = Expression(
        mod.PERIODS,
        rule=lambda m, p: sum(
            m.StrOMCosts[g, p] for g in m.STORAGE_GENS
        ),
    )   

    mod.Cost_Components_Per_Period.append("StrFixedOMCosts")    

    # 储能的可变运维成本，暂时不用管
    def period_active_str_rule(m, period):
        if not hasattr(m, "period_active_str_dict"):
            m.period_active_str_dict = dict()
            for (_g, _period) in m.STR_PERIODS :
                m.period_active_str_dict.setdefault(_period, []).append(_g)
        result = m.period_active_str_dict.pop(period)
        if len(m.period_active_str_dict) == 0:
            delattr(m, "period_active_str_dict")
        return result

    #这是一个在给定的period里，能够使用的gen的合集
    mod.STR_IN_PERIOD = Set(
        mod.PERIODS,
        dimen=1,
        initialize=period_active_str_rule,
        doc="The set of projects active in a given period.",
    )   

    mod.str_variable_om = Param(mod.STORAGE_GENS, within=NonNegativeReals)
    mod.StrVariableOMCostsInTP = Expression(
        mod.TIMEPOINTS,
        rule=lambda m, t: sum(
            m.DischargeStorage[g, t] * m.str_variable_om[g]
            for g in m.STR_IN_PERIOD[m.tp_period[t]]
        ),
        doc="Summarize costs for the objective function",
    )
    mod.Cost_Components_Per_TP.append("StrVariableOMCostsInTP")


def load_inputs(mod, switch_data, inputs_dir):
    """

    Import storage parameters. Optional columns are noted with a *.

    gen_info.csv
        GENERATION_PROJECT, ...
        str_storage_efficiency, gen_store_to_release_ratio*,
        gen_storage_energy_to_power_ratio*, gen_storage_max_cycles_per_year*

    gen_build_costs.csv
        GENERATION_PROJECT, build_year, ...
        str_overnight_cost

    gen_build_predetermined.csv
        GENERATION_PROJECT, build_year, ...,
        build_gen_energy_predetermined*

    """

    # TODO: maybe move these columns to a storage_gen_info file to avoid the weird index
    # reading and avoid having to create these extra columns for all projects;
    # Alternatively, say that these values are specified for _all_ projects (maybe with None
    # as default) and then define STORAGE_GENS as the subset of projects for which
    # str_storage_efficiency has been specified, then require valid settings for all
    # STORAGE_GENS.
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "str_info.csv"),
        index=mod.STORAGE_GENS,
        param=(
            mod.str_storage_efficiency,
            mod.str_max_age,
            mod.str_load_zone,
            mod.str_tech,
            mod.str_variable_om,
            # mod.storage_max_power_mw,
            mod.str_is_distributed,
            mod.str_is_grid_connected,
            mod.str_is_reconnected,
            mod.str_connect_cost_per_mw,
            mod.str_is_baseload,
            mod.str_forced_outage_rate,
            mod.str_scheduled_outage_rate,
            mod.str_min_commit_fraction
        ),
    )

    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "str_build_costs.csv"),
        index=mod.STR_BLD_YRS,
        param=(
            mod.str_overnight_cost,
            mod.str_fixed_om
            ),
    )
    
    # switch_data.load_aug(
    #     optional=True,
    #     filename=os.path.join(inputs_dir, "gen_build_predetermined.csv"),
    #     param=(mod.build_gen_energy_predetermined,),
    # )
    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, "str_build_predetermined.csv"),
        index=mod.PREDETERMINED_STR_BLD_YRS,
        param=(mod.build_str_energy_predetermined),
    )    