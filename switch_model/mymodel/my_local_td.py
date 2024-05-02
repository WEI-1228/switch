from __future__ import division

import os

import pandas as pd
from pyomo.environ import *

dependencies = (
    "switch_model.timescales",
    "switch_model.balancing.load_zones",
    "switch_model.financials",
)


def define_dynamic_lists(mod):
    mod.Distributed_Power_Injections = []
    mod.Distributed_Power_Withdrawals = []


def define_components(mod):

    # Local T&D
    mod.existing_local_td = Param(mod.LOAD_ZONES, within=NonNegativeReals, default=0.0)
    # 这个是针对每个load zone 和period设置的
    mod.BuildLocalTD = Var(mod.LOAD_ZONES, mod.PERIODS, within=NonNegativeReals)
    
    # 就是每个区域z的已经存在的容量加上当前period以及以前period决策建立的容量，根据z和p索引
    mod.LocalTDCapacity = Expression(
        mod.LOAD_ZONES,
        mod.PERIODS,
        rule=lambda m, z, period: m.existing_local_td[z]
        + sum(
            m.BuildLocalTD[z, bld_yr]
            for bld_yr in m.CURRENT_AND_PRIOR_PERIODS_FOR_PERIOD[period]
        ),
    )
    # 传输损耗率
    mod.local_td_loss_rate = Param(
        mod.LOAD_ZONES, within=NonNegativeReals, default=0.053
    )
    # 约束，除掉损耗的localtd容量必须大于当前period和z的尖峰负荷
    # zone_expected_coincident_peak_demand在load zone里输入
    mod.Meet_Local_TD = Constraint(
        mod.EXTERNAL_COINCIDENT_PEAK_DEMAND_ZONE_PERIODS,
        rule=lambda m, z, period: (
            m.LocalTDCapacity[z, period] * (1 - m.local_td_loss_rate[z])
            >= m.zone_expected_coincident_peak_demand[z, period]
        ),
    )

    ####分布式节点的设定
    # DISTRIBUTED NODE
    mod.WithdrawFromCentralGrid = Var(
        mod.ZONE_TIMEPOINTS,
        within=NonNegativeReals,
        doc="Power withdrawn from a zone's central node sent over local T&D.",
    )
    # 从中心节点的提取量不能超过当前时间点的累积容量
    mod.Enforce_Local_TD_Capacity_Limit = Constraint(
        mod.ZONE_TIMEPOINTS,
        rule=lambda m, z, t: m.WithdrawFromCentralGrid[z, t]
        <= m.LocalTDCapacity[z, m.tp_period[t]],
    )
    # 注入到分布式节点的量
    mod.InjectIntoDistributedGrid = Expression(
        mod.ZONE_TIMEPOINTS,
        doc="Describes WithdrawFromCentralGrid after line losses.",
        rule=lambda m, z, t: (
            m.WithdrawFromCentralGrid[z, t] * (1 - m.local_td_loss_rate[z])
        ),
    )

    # Register energy injections & withdrawals
    mod.Zone_Power_Withdrawals.append("WithdrawFromCentralGrid")
    mod.Distributed_Power_Injections.append("InjectIntoDistributedGrid")
    
    ####### 成本计算，注意这个参数的设定值
    mod.local_td_annual_cost_per_mw = Param(
        mod.LOAD_ZONES, within=NonNegativeReals, default=0.0
    )
    mod.min_data_check("local_td_annual_cost_per_mw")
    # 计算每个period所有zone的localtd固定成本
    mod.LocalTDFixedCosts = Expression(
        mod.PERIODS,
        doc="Summarize annual local T&D costs for the objective function.",
        rule=lambda m, p: sum(
            m.LocalTDCapacity[z, p] * m.local_td_annual_cost_per_mw[z]
            for z in m.LOAD_ZONES
        ),
    )
    mod.Cost_Components_Per_Period.append("LocalTDFixedCosts")


def define_dynamic_components(mod):

# 分布式节点的供需平衡约束
    mod.Distributed_Energy_Balance = Constraint(
        mod.ZONE_TIMEPOINTS,
        rule=lambda m, z, t: (
            sum(
                getattr(m, component)[z, t]
                for component in m.Distributed_Power_Injections
            )
            == sum(
                getattr(m, component)[z, t]
                for component in m.Distributed_Power_Withdrawals
            )
        ),
    )

def load_inputs(mod, switch_data, inputs_dir):
    """

    Import local transmission & distribution data. The following file is
    expected in the input directory. Optional columns are marked with *.
    load_zones.csv will contain additional columns that are used by the
    load_zones module.

    load_zones.csv
        load_zone, ..., existing_local_td, local_td_annual_cost_per_mw, local_td_loss_rate*

    """

    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "load_zones.csv"),
        optional_params=["local_td_loss_rate"],
        param=(
            mod.existing_local_td,
            mod.local_td_annual_cost_per_mw,
            mod.local_td_loss_rate,
        ),
    )


def post_solve(instance, outdir):
    """
    Export results.

    local_td_energy_balance_wide.csv is a wide table of energy balance
    components for every zone and timepoint. Each component registered with
    Distributed_Power_Injections and Distributed_Power_Withdrawals will become
    a column. Values of Distributed_Power_Withdrawals will be multiplied by -1
    during export. The columns in this file can vary based on which modules
    are included in your model.

    local_td_energy_balance.csv is the same data in "tidy" form with a constant
    number of columns.

    """
    wide_dat = []
    for z, t in instance.ZONE_TIMEPOINTS:
        record = {"load_zone": z, "timestamp": t}
        for component in instance.Distributed_Power_Injections:
            record[component] = value(getattr(instance, component)[z, t])
        for component in instance.Distributed_Power_Withdrawals:
            record[component] = value(-1.0 * getattr(instance, component)[z, t])
        wide_dat.append(record)
    wide_df = pd.DataFrame(wide_dat)
    wide_df.set_index(["load_zone", "timestamp"], inplace=True)
    if instance.options.sorted_output:
        wide_df.sort_index(inplace=True)
    wide_df.to_csv(os.path.join(outdir, "local_td_energy_balance_wide.csv"))

    normalized_dat = []
    for z, t in instance.ZONE_TIMEPOINTS:
        for component in instance.Distributed_Power_Injections:
            record = {
                "load_zone": z,
                "timestamp": t,
                "component": component,
                "injects_or_withdraws": "injects",
                "value": value(getattr(instance, component)[z, t]),
            }
            normalized_dat.append(record)
        for component in instance.Distributed_Power_Withdrawals:
            record = {
                "load_zone": z,
                "timestamp": t,
                "component": component,
                "injects_or_withdraws": "withdraws",
                "value": value(-1.0 * getattr(instance, component)[z, t]),
            }
            normalized_dat.append(record)
    df = pd.DataFrame(normalized_dat)
    df.set_index(["load_zone", "timestamp", "component"], inplace=True)
    if instance.options.sorted_output:
        df.sort_index(inplace=True)
    df.to_csv(os.path.join(outdir, "local_td_energy_balance.csv"))
