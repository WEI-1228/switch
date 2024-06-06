import os
import pandas as pd
import logging
from pyomo.environ import *
from switch_model.financials import capital_recovery_factor as crf
from switch_model.reporting import write_table
from switch_model.utilities import unique_list
from switch_model.utilities import unwrap

dependencies = (
    "switch_model.timescales",
    "switch_model.balancing.load_zones",
    "switch_model.financials",
    "switch_model.energy_sources.properties.properties",
)
def define_components(mod):
    
    # 这个在后面build gen的约束那里就用上了。作为buildgen的上限设定
    mod.GENERATION_PROJECTS = Set(dimen=1)
    mod.CAPACITY_LIMITED_GENS = Set(within=mod.GENERATION_PROJECTS, dimen=1)
    mod.gen_capacity_limit_mw = Param(
        mod.CAPACITY_LIMITED_GENS, within=NonNegativeReals
    )
        
    #这个代码中最核心的部分,关于buildgen的设定
    mod.PREDETERMINED_GEN_BLD_YRS = Set(dimen=2)
    
    
    # 这是一个gen和build year的合集，是具有输入的，
    # 筛选掉在决策期之外的g和bld-yr
    mod.GEN_BLD_YRS = Set(
        dimen=2,
        validate=lambda m, g, bld_yr: (
            (g, bld_yr) in m.PREDETERMINED_GEN_BLD_YRS
            or (g, bld_yr) in m.GENERATION_PROJECTS * m.PERIODS
        ),
    )
    # 得到一个没有预先增加容量的g和bld yr的集合。
    mod.NEW_GEN_BLD_YRS = Set(
        dimen=2, initialize=lambda m: m.GEN_BLD_YRS - m.PREDETERMINED_GEN_BLD_YRS
    )
    mod.build_gen_predetermined = Param(
        mod.PREDETERMINED_GEN_BLD_YRS, within=NonNegativeReals
    )
    mod.gen_is_distributed = Param(
        mod.GENERATION_PROJECTS, within=Boolean, default=False
    )
    mod.min_data_check("build_gen_predetermined")
    
    mod.gen_max_age = Param(mod.GENERATION_PROJECTS, within=PositiveIntegers)
    # 这是确定一个在哪个投资period里能用的规则，如果在这个period里上线，上线时间就算这个周期的开始时间
    def gen_build_can_operate_in_period(m, g, build_year, period):
        if build_year in m.PERIODS:
            online = m.period_start[build_year]
        else:
            online = build_year
        retirement = online + m.gen_max_age[g]
        return online <= m.period_start[period] < retirement
    
    #  输入对每一对g和period判断其中能够在这个period里有效的bld yr，且这个bld yr不重复
    # 一个g可能对应很多个bld yr，对于目前还没有建立的，对每一个投资周期的起始都有一个bld yr。
    # 对已经建立的项目，他的bld yr就是实际的那个bld yr。
    # 对所有的g和period的组合都确定它能在线的bld
    #对于已经建立的项目，只有0和1这种可能性，要么就有一个bld yr，要么就没有
    #对于每个没建立的项目，g和2037.-g，2023，g 2028，g，2032，g2037，g2040，
    # 这个bld yr可能就有2023，2028，2032，只要没退休就行
    mod.BLD_YRS_FOR_GEN_PERIOD = Set(
        mod.GENERATION_PROJECTS,
        mod.PERIODS,
        dimen=1,
        initialize=lambda m, g, period: unique_list(
            bld_yr
            for (gen, bld_yr) in m.GEN_BLD_YRS
            if gen == g and gen_build_can_operate_in_period(m, g, bld_yr, period)
        ),
    )
    # The set of periods when a generator is available to run
    
    # 对所有的g，循环period，其中能够有用的period集合
    # 针对所有的g，得到的能够在线的period
    # 跟上面那个其实差不多，上面那个感觉完全没必要，也没用上啊，挺奇怪的。
    mod.PERIODS_FOR_GEN = Set(
        mod.GENERATION_PROJECTS,
        dimen=1,
        initialize=lambda m, g: [
            p for p in m.PERIODS if len(m.BLD_YRS_FOR_GEN_PERIOD[g, p]) > 0
        ],
    )
    # gen和period，这个主要是用在后面dispatch里了
    mod.GEN_PERIODS = Set(
        dimen=2,
        initialize=lambda m: [
            (g, p) for g in m.GENERATION_PROJECTS for p in m.PERIODS_FOR_GEN[g]
        ],
    )

    def bounds_BuildGen(model, g, bld_yr):
        if (g, bld_yr) in model.PREDETERMINED_GEN_BLD_YRS:
            return (
                model.build_gen_predetermined[g, bld_yr],
                model.build_gen_predetermined[g, bld_yr],
            )
        elif g in model.CAPACITY_LIMITED_GENS:
            # This does not replace Max_Build_Potential because
            # Max_Build_Potential applies across all build years.
            return (0, model.gen_capacity_limit_mw[g])
        else:
            return (0, None)

    # 对每个g和bld-yr决策一个是否要建立新的容量。
    mod.BuildGen = Var(mod.GEN_BLD_YRS, within=NonNegativeReals, bounds=bounds_BuildGen)
    
    
    # 这个buildgen有一个初始值，就是原先建立的容量。
    def BuildGen_assign_default_value(m, g, bld_yr):
        m.BuildGen[g, bld_yr] = m.build_gen_predetermined[g, bld_yr]

    mod.BuildGen_assign_default_value = BuildAction(
        mod.PREDETERMINED_GEN_BLD_YRS, rule=BuildGen_assign_default_value
    )

    # 就是把默认值和新建的值加起来
    mod.GenCapacity = Expression(
        mod.GENERATION_PROJECTS,
        mod.PERIODS,
        rule=lambda m, g, period: sum(
            m.BuildGen[g, bld_yr] for bld_yr in m.BLD_YRS_FOR_GEN_PERIOD[g, period]
        ),
    )
    # 最大容量限制
    mod.Max_Build_Potential = Constraint(
        mod.CAPACITY_LIMITED_GENS,
        mod.PERIODS,
        rule=lambda m, g, p: (m.gen_capacity_limit_mw[g] >= m.GenCapacity[g, p]),
    )


    mod.gen_min_build_capacity = Param(
        mod.GENERATION_PROJECTS, within=NonNegativeReals, default=0
    )
    # 对于要决策新建的项目（g，bly-yr）这个bld yr应该都是要决策期的开始年份，限制一个下限，
    # 现在留下的是最小建造容量大于0的g和它的bld yr
    mod.NEW_GEN_WITH_MIN_BUILD_YEARS = Set(
        dimen=2,
        initialize=mod.NEW_GEN_BLD_YRS,
        filter=lambda m, g, p: (m.gen_min_build_capacity[g] > 0),
    )
    # 嘚对（g，bld-yr）这个bld-yr是每个决策期的开始年份，决策是否要新建容量
    mod.BuildMinGenCap = Var(mod.NEW_GEN_WITH_MIN_BUILD_YEARS, within=Binary)
    # 新建容量的下限，这里都是针对能够增加容量的设备。
    mod.Enforce_Min_Build_Lower = Constraint(
        mod.NEW_GEN_WITH_MIN_BUILD_YEARS,
        rule=lambda m, g, p: (
            m.BuildMinGenCap[g, p] * m.gen_min_build_capacity[g] <= m.BuildGen[g, p]
        ),
    )
    # buildgen的约束上限
    mod._gen_max_cap_for_binary_constraints = 10**5
    mod.Enforce_Min_Build_Upper = Constraint(
        mod.NEW_GEN_WITH_MIN_BUILD_YEARS,
        rule=lambda m, g, p: (
            m.BuildGen[g, p]
            <= m.BuildMinGenCap[g, p] * mod._gen_max_cap_for_binary_constraints
        ),
    )
    
    # def period_active_gen_rule(m, period):
    #     if not hasattr(m, "period_active_gen_dict"):
    #         m.period_active_gen_dict = dict()
    #         for (_g, _period) in m.GEN_PERIODS:
    #             m.period_active_gen_dict.setdefault(_period, []).append(_g)
    #     result = m.period_active_gen_dict.pop(period)
    #     if len(m.period_active_gen_dict) == 0:
    #         delattr(m, "period_active_gen_dict")
    #     return result
    
    def period_active_gen_rule(m, period):
        if not hasattr(m, "period_active_gen_dict"):
            m.period_active_gen_dict = dict()
            for (_g, _period) in m.GEN_PERIODS:
                m.period_active_gen_dict.setdefault(_period, []).append(_g)
        result = m.period_active_gen_dict.pop(period)
        if len(m.period_active_gen_dict) == 0:
            delattr(m, "period_active_gen_dict")
        return result

    #这是一个在给定的period里，能够使用的gen的合集
    mod.GENS_IN_PERIOD = Set(
        mod.PERIODS,
        dimen=1,
        initialize=period_active_gen_rule,
        doc="The set of projects active in a given period.",
    )

    ########################################  dispatch  ########################################
    #  到这进入到了dispatch模块里的dispatchgen参数设定的情况
    
    # 就是根据period for gen（给定一个g的所有可用period合集）细化到给定一个g的所有可用时间点的合集
    # 主要是为了后面集合的设定才设的这个集合
    # 这个tps in period是在timescale里就定义了的
    mod.TPS_FOR_GEN = Set(
        mod.GENERATION_PROJECTS,
        dimen=1,
        within=mod.TIMEPOINTS,
        initialize=lambda m, g: (
            tp for p in m.PERIODS_FOR_GEN[g] for tp in m.TPS_IN_PERIOD[p]
        ),
    )
    # 一个可用的g和时间点的集合（g,tp）
    mod.GEN_TPS = Set(
        dimen=2,
        initialize=lambda m: (
            (g, tp) for g in m.GENERATION_PROJECTS for tp in m.TPS_FOR_GEN[g]
        ),
    )

    # 对每个g和可用tp都决策调度情况，这是这个模块里最核心的东西。
    mod.DispatchGen = Var(mod.GEN_TPS, within=NonNegativeReals)
    #############

    # 到这里开始定义commitgen和启停容量，以及dispatchgen的约束
    
    # Commitment decision, bounds and associated slack variables
    # 每个（g,t），这个t是g在线的t。都决策一个commitgen
    mod.CommitGen = Var(mod.GEN_TPS, within=NonNegativeReals)
    
    # 这是个最大的commit系数
    mod.gen_max_commit_fraction = Param(
        mod.GEN_TPS, within=PercentFraction, default=lambda m, g, t: 1.0
    )
    # 最小的commit系数，对于基础负荷发电机来说是1，对别的发电机来说是0
    # 这个最早就是在operate里的那个参数输入的时候用到了，跟那个放到一起吧
    mod.gen_is_baseload = Param(mod.GENERATION_PROJECTS, within=Boolean, default=False)
    mod.BASELOAD_GENS = Set(
        dimen=1,
        initialize=mod.GENERATION_PROJECTS,
        filter=lambda m, g: m.gen_is_baseload[g],
    )
    mod.gen_min_commit_fraction = Param(
        mod.GEN_TPS,
        within=PercentFraction,
        default=lambda m, g, t: (
            m.gen_max_commit_fraction[g, t] if g in m.BASELOAD_GENS else 0.0
        ),
    )
    
    # 这一大串都是为了commit的上下限。
    mod.gen_scheduled_outage_rate = Param(
        mod.GENERATION_PROJECTS, within=PercentFraction, default=0
    )
    mod.gen_forced_outage_rate = Param(
        mod.GENERATION_PROJECTS, within=PercentFraction, default=0
    )
    # 强制停运率和计划停运率，在gen info里输入
    def init_gen_availability(m, g):
        if m.gen_is_baseload[g]:
            return (1 - m.gen_forced_outage_rate[g]) * (
                1 - m.gen_scheduled_outage_rate[g]
            )
        else:
            return 1 - m.gen_forced_outage_rate[g]

    mod.gen_availability = Param(
        mod.GENERATION_PROJECTS,
        within=NonNegativeReals,
        initialize=init_gen_availability,
    )
    
    mod.GenCapacityInTP = Expression(
        mod.GEN_TPS, rule=lambda m, g, t: m.GenCapacity[g, m.tp_period[t]]
    )    
    
    # 对于所有的（g，t），commit的约束下限，对非基础负荷发电机来说，下限是0
    mod.CommitLowerLimit = Expression(
        mod.GEN_TPS,
        rule=lambda m, g, t: (
            m.GenCapacityInTP[g, t]
            * m.gen_availability[g]
            * m.gen_min_commit_fraction[g, t]
        ),
    )
    # 对于所有的（g,t）,commit的约束上限
    mod.CommitUpperLimit = Expression(
        mod.GEN_TPS,
        rule=lambda m, g, t: (
            m.GenCapacityInTP[g, t]
            * m.gen_availability[g]
            * m.gen_max_commit_fraction[g, t]
        ),
    )
    ###### commit gen的上下限约束
    mod.Enforce_Commit_Lower_Limit = Constraint(
        mod.GEN_TPS,
        rule=lambda m, g, t: (m.CommitLowerLimit[g, t] <= m.CommitGen[g, t]),
    )
    mod.Enforce_Commit_Upper_Limit = Constraint(
        mod.GEN_TPS,
        rule=lambda m, g, t: (m.CommitGen[g, t] <= m.CommitUpperLimit[g, t]),
    )
    ######
    
    # 定义了启停容量，and commitgen和启停容量的那个约束
    # StartupGenCapacity & ShutdownGenCapacity (at start of each timepoint)
    mod.StartupGenCapacity = Var(mod.GEN_TPS, within=NonNegativeReals)
    mod.ShutdownGenCapacity = Var(mod.GEN_TPS, within=NonNegativeReals)
    mod.Commit_StartupGenCapacity_ShutdownGenCapacity_Consistency = Constraint(
        mod.GEN_TPS,
        rule=lambda m, g, t: m.CommitGen[g, m.tp_previous[t]]
        + m.StartupGenCapacity[g, t]
        - m.ShutdownGenCapacity[g, t]
        == m.CommitGen[g, t],
    )

    ### 这里描述的是关于dispatchgen的约束，可以写在那dispatch里面的。
    # Dispatch limits relative to committed capacity.
    # 针对每个g，判断这个值是0还是1
    mod.gen_min_load_fraction = Param(
        mod.GENERATION_PROJECTS,
        within=PercentFraction,
        default=lambda m, g: 1.0 if m.gen_is_baseload[g] else 0.0,
    )
    # 输入（g，t），判断这个值是0还是1
    mod.gen_min_load_fraction_TP = Param(
        mod.GEN_TPS,
        default=lambda m, g, t: m.gen_min_load_fraction[g],
        within=NonNegativeReals,
    )
    # dispatchgen的下限
    mod.DispatchLowerLimit = Expression(
        mod.GEN_TPS,
        rule=lambda m, g, t: (m.CommitGen[g, t] * m.gen_min_load_fraction_TP[g, t]),
    )
    
    mod.gen_is_variable = Param(mod.GENERATION_PROJECTS, within=Boolean)
    mod.VARIABLE_GENS = Set(
        dimen=1,
        initialize=mod.GENERATION_PROJECTS,
        filter=lambda m, g: m.gen_is_variable[g],
    )
    
    mod.VARIABLE_GEN_TPS = Set(
        dimen=2,
        initialize=lambda m: (
            (g, tp) for g in m.VARIABLE_GENS for tp in m.TPS_FOR_GEN[g]
        ),
    )
    
    # 这个集合更大，是所有时间点，前面的集合更小只是针对每个可再生能源项目g可用的时间点
    mod.VARIABLE_GEN_TPS_RAW = Set(dimen=2, within=mod.VARIABLE_GENS * mod.TIMEPOINTS)
    mod.gen_max_capacity_factor = Param(
        mod.VARIABLE_GEN_TPS_RAW,
        within=Reals,
        validate=lambda m, val, g, t: -1 < val < 2,
    )
    
    ######确保这个什么东西是有效的一个规则
    # Validate that a gen_max_capacity_factor has been defined for every
    # variable gen / timepoint that we need. Extra cap factors (like beyond an
    # existing plant's lifetime) shouldn't cause any problems.
    # This replaces: mod.min_data_check('gen_max_capacity_factor') from when
    # gen_max_capacity_factor was indexed by VARIABLE_GEN_TPS.
    # def ak(m, g, t):
    #     if (g, t) not in m.VARIABLE_GEN_TPS_RAW:
    #         for i in m.VARIABLE_GENS:
    #             print(i)
    #     return (g, t) in m.VARIABLE_GEN_TPS_RAW
        
    mod.have_minimal_gen_max_capacity_factors = BuildCheck(
        mod.VARIABLE_GEN_TPS, rule=lambda m, g, t: (g, t) in m.VARIABLE_GEN_TPS_RAW
    )

    if mod.logger.isEnabledFor(logging.INFO):
        # Tell user if the input files specify timeseries for renewable plant
        # capacity factors that extend beyond the lifetime of the plant.
        def rule(m):
            extra_indexes = m.VARIABLE_GEN_TPS_RAW - m.VARIABLE_GEN_TPS
            if extra_indexes:
                num_impacted_generators = len(set(g for g, t in extra_indexes))
                extraneous = {g: [] for (g, t) in extra_indexes}
                for (g, t) in extra_indexes:
                    extraneous[g].append(t)
                pprint = "\n".join(
                    "* {}: {} to {}".format(g, min(tps), max(tps))
                    for g, tps in extraneous.items()
                )
                # basic message for everyone at info level
                msg = unwrap(
                    """
                    {} generation project[s] have data in
                    variable_capacity_factors.csv for timepoints when they are
                    not operable, either before construction is possible or
                    after retirement.
                """.format(
                        num_impacted_generators
                    )
                )
                if m.logger.isEnabledFor(logging.DEBUG):
                    # more detailed message
                    msg += unwrap(
                        """
                         You can avoid this message by only placing data in
                        variable_capacity_factors.csv for active periods for
                        each project. If you expect these project[s] to be
                        operable during  all the timepoints currently in
                        variable_capacity_factors.csv, then they need to either
                        come online earlier, have longer lifetimes, or have
                        options to build new capacity when the old capacity
                        reaches its maximum age.
                    """
                    )
                    msg += " Plants with extra timepoints:\n{}".format(pprint)
                else:
                    msg += " Use --log-level debug for more details."
                m.logger.info(msg + "\n")

        mod.notify_on_extra_VARIABLE_GEN_TPS = BuildAction(rule=rule)
        
    ########################

    # dispatchgen的上限
    def DispatchUpperLimit_expr(m, g, t):
        if g in m.VARIABLE_GENS:
            return m.CommitGen[g, t] * m.gen_max_capacity_factor[g, t]
        else:
            return m.CommitGen[g, t]

    mod.DispatchUpperLimit = Expression(mod.GEN_TPS, rule=DispatchUpperLimit_expr)

    mod.Enforce_Dispatch_Lower_Limit = Constraint(
        mod.GEN_TPS,
        rule=lambda m, g, t: (m.DispatchLowerLimit[g, t] <= m.DispatchGen[g, t]),
    )
    mod.Enforce_Dispatch_Upper_Limit = Constraint(
        mod.GEN_TPS,
        rule=lambda m, g, t: (m.DispatchGen[g, t] <= m.DispatchUpperLimit[g, t]),
    )
    
    mod.DispatchSlackUp = Expression(
        mod.GEN_TPS,
        rule=lambda m, g, t: (m.DispatchUpperLimit[g, t] - m.DispatchGen[g, t]),
    )
    mod.DispatchSlackDown = Expression(
        mod.GEN_TPS,
        rule=lambda m, g, t: (m.DispatchGen[g, t] - m.DispatchLowerLimit[g, t]),
    )


    ####关于发电机组的设定和约束到此就结束了
    # 成本约束
    
    # 弃风弃光惩罚成本
    # TODO 还未加载
    # mod.variable_gen_cost = Param(mod.GENERATION_PROJECTS, within=NonNegativeReals)
    
    
    # mod.VariableCost = Expression(
    #     mod.TIMEPOINTS,
    #     rule=lambda m, t: sum(
    #         m.DispatchSlackUp[g, t] * m.variable_gen_cost[g]#/ m.tp_duration_hrs[t]
    #             for g in m.GENS_IN_PERIOD[m.tp_period[t]])
    # )
    
    # mod.Cost_Components_Per_TP.append("VariableCost")
    
    # Costs
    mod.gen_variable_om = Param(mod.GENERATION_PROJECTS, within=NonNegativeReals)
    mod.gen_connect_cost_per_mw = Param(
        mod.GENERATION_PROJECTS, within=NonNegativeReals
    )
    mod.min_data_check("gen_variable_om", "gen_connect_cost_per_mw")

    mod.gen_overnight_cost = Param(mod.GEN_BLD_YRS, within=NonNegativeReals)
    mod.gen_fixed_om = Param(mod.GEN_BLD_YRS, within=NonNegativeReals)
    mod.min_data_check("gen_overnight_cost", "gen_fixed_om")

    # Derived annual costs
    # 这个interest rate在financial里定义的
    mod.gen_capital_cost_annual = Param(
        mod.GEN_BLD_YRS,
        within=NonNegativeReals,
        initialize=lambda m, g, bld_yr: (
            (m.gen_overnight_cost[g, bld_yr] + m.gen_connect_cost_per_mw[g])
            * crf(m.interest_rate, m.gen_max_age[g])
        ),
    )
    
    # 资本成本
    mod.GenCapitalCosts = Expression(
        mod.GENERATION_PROJECTS,
        mod.PERIODS,
        rule=lambda m, g, p: sum(
            m.BuildGen[g, bld_yr] * m.gen_capital_cost_annual[g, bld_yr]
            for bld_yr in m.BLD_YRS_FOR_GEN_PERIOD[g, p]
        ),
    )
    
    # 固定运维成本
    mod.GenFixedOMCosts = Expression(
        mod.GENERATION_PROJECTS,
        mod.PERIODS,
        rule=lambda m, g, p: sum(
            m.BuildGen[g, bld_yr] * m.gen_fixed_om[g, bld_yr]
            for bld_yr in m.BLD_YRS_FOR_GEN_PERIOD[g, p]
        ),
    )
    # 总的固定成本：资本成本+固定运维成本
    mod.TotalGenFixedCosts = Expression(
        mod.PERIODS,
        rule=lambda m, p: sum(
            m.GenCapitalCosts[g, p] + m.GenFixedOMCosts[g, p]
            for g in m.GENERATION_PROJECTS
        ),
    )
    mod.Cost_Components_Per_Period.append("TotalGenFixedCosts")
    
    mod.GenVariableOMCostsInTP = Expression(
        mod.TIMEPOINTS,
        rule=lambda m, t: sum(
            m.DispatchGen[g, t] * m.gen_variable_om[g]
            for g in m.GENS_IN_PERIOD[m.tp_period[t]]
        ),
        doc="Summarize costs for the objective function",
    )
    mod.Cost_Components_Per_TP.append("GenVariableOMCostsInTP")
    
    mod.gen_startup_om = Param(
        mod.GENERATION_PROJECTS, default=0.0, within=NonNegativeReals
    )
    # Cost_Components_Per_TP.启动成本
    mod.Total_StartupGenCapacity_OM_Costs = Expression(
        mod.TIMEPOINTS,
        rule=lambda m, t: sum(
            m.gen_startup_om[g] * m.StartupGenCapacity[g, t] / m.tp_duration_hrs[t]
            for g in m.GENS_IN_PERIOD[m.tp_period[t]]
        ),
    )
    mod.Cost_Components_Per_TP.append("Total_StartupGenCapacity_OM_Costs")
    

    # 这一段属于平衡约束，到时候把所有的平衡约束放在一起
    ####这一大堆定义gen在z上的集合，在这并没有用上，计划储备，旋转储备，
    # 旋转储备advanced，和dispatch里计算调度
    mod.gen_load_zone = Param(mod.GENERATION_PROJECTS, within=mod.LOAD_ZONES)
    def GENS_IN_ZONE_init(m, z):
        if not hasattr(m, "GENS_IN_ZONE_dict"):
            m.GENS_IN_ZONE_dict = {_z: [] for _z in m.LOAD_ZONES}
            for g in m.GENERATION_PROJECTS:
                m.GENS_IN_ZONE_dict[m.gen_load_zone[g]].append(g)
        result = m.GENS_IN_ZONE_dict.pop(z)
        if not m.GENS_IN_ZONE_dict:
            del m.GENS_IN_ZONE_dict
        return result

    mod.GENS_IN_ZONE = Set(mod.LOAD_ZONES, dimen=1, initialize=GENS_IN_ZONE_init)
    
    mod.ZoneTotalCentralDispatch = Expression(
        mod.LOAD_ZONES,
        mod.TIMEPOINTS,
        rule=lambda m, z, t: sum(
            m.DispatchGen[g, t]
            for g in m.GENS_IN_ZONE[z]
            if (g, t) in m.GEN_TPS and not m.gen_is_distributed[g]
        )
    )
    mod.Zone_Power_Injections.append("ZoneTotalCentralDispatch")

    # Divide distributed generation into a separate expression so that we can
    # put it in the distributed node's power balance equations if local_td is
    # included.
    mod.ZoneTotalDistributedDispatch = Expression(
        mod.LOAD_ZONES,
        mod.TIMEPOINTS,
        rule=lambda m, z, t: sum(
            m.DispatchGen[g, t]
            for g in m.GENS_IN_ZONE[z]
            if (g, t) in m.GEN_TPS and m.gen_is_distributed[g]
        ),
        doc="Total power from distributed generation projects.",
    )
    try:
        mod.Distributed_Power_Injections.append("ZoneTotalDistributedDispatch")
    except AttributeError:
        mod.Zone_Power_Injections.append("ZoneTotalDistributedDispatch")


def load_inputs(mod, switch_data, inputs_dir):
    ######  build load inputs  ######
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "gen_info.csv"),
        optional_params=[
            "gen_is_baseload",
            "gen_scheduled_outage_rate",
            "gen_forced_outage_rate",
            "gen_capacity_limit_mw",
            "gen_min_build_capacity",
            "gen_is_distributed",
        ],
        index=mod.GENERATION_PROJECTS,
        param=(
            mod.gen_load_zone,
            mod.gen_max_age,
            mod.gen_is_variable,
            mod.gen_is_baseload,
            mod.gen_scheduled_outage_rate,
            mod.gen_forced_outage_rate,
            mod.gen_capacity_limit_mw,
            mod.gen_variable_om,
            mod.gen_min_build_capacity,
            mod.gen_connect_cost_per_mw,
            mod.gen_is_distributed,
            #mod.variable_gen_cost
        ),
    )
    
    if "gen_capacity_limit_mw" in switch_data.data():
        switch_data.data()["CAPACITY_LIMITED_GENS"] = {
            None: list(switch_data.data(name="gen_capacity_limit_mw").keys())
        }
        
    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, "gen_build_predetermined.csv"),
        index=mod.PREDETERMINED_GEN_BLD_YRS,
        param=(mod.build_gen_predetermined),
    )
    
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "gen_build_costs.csv"),
        index=mod.GEN_BLD_YRS,
        param=(mod.gen_overnight_cost, mod.gen_fixed_om),
    )
    
    ######  dispatch load inputs  ######
    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, "variable_capacity_factors.csv"),
        index=mod.VARIABLE_GEN_TPS_RAW,
        param=(mod.gen_max_capacity_factor,),
    )
    
    ######  operate load inputs  ######
    
    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, "gen_info.csv"),
        param=(
            mod.gen_min_load_fraction,
            mod.gen_startup_om,
        ),
    )
    switch_data.load_aug(
        optional=True,
        filename=os.path.join(inputs_dir, "gen_timepoint_commit_bounds.csv"),
        param=(
            mod.gen_min_commit_fraction,
            mod.gen_max_commit_fraction,
            mod.gen_min_load_fraction_TP,
        ),
    )
    

def post_solve(m, outdir):
    # report generator and storage additions in each period and and total
    # capital outlay for those (up-front capital outlay is not treated as a
    # direct cost by Switch, but is often interesting to users)
    write_table(
        m,
        m.GEN_TPS,
        output_file=os.path.join(outdir, "DispatchSlackUp.csv"),
        headings=(
            "GENERATION_PROJECT",
            "timepoints",
            "dispatch_slack_up",
        ),
        values=lambda m, g, t: (
            g,
            t,
            m.DispatchSlackUp[g, t]
        ),
    )

    
    # write_table(
    #     m,
    #     m.TIMEPOINTS,
    #     output_file=os.path.join(outdir, "VariableCost.csv"),
    #     headings=(
    #         "timepoints",
    #         "variable_cost",
    #     ),
    #     values=lambda m, t: (
    #         t,
    #         m.VariableCost[t]
    #     ),
    # )
    