import logging
import os

import pandas as pd
from pyomo.environ import *

from switch_model.financials import capital_recovery_factor as crf
from switch_model.utilities import unique_list

dependencies = (
    "switch_model.timescales",
    "switch_model.balancing.load_zones",
    "switch_model.financials",
)


def define_components(mod):


    # 传输线路集合
    mod.TRANSMISSION_LINES = Set(dimen=1)
    mod.trans_lz1 = Param(mod.TRANSMISSION_LINES, within=mod.LOAD_ZONES)
    mod.trans_lz2 = Param(mod.TRANSMISSION_LINES, within=mod.LOAD_ZONES)
    # we don't do a min_data_check for TRANSMISSION_LINES, because it may be empty for model
    # configurations that are sometimes run with interzonal transmission and sometimes not
    # (e.g., island interconnect scenarios). However, presence of this column will still be
    # checked by load_data_aug.
    mod.min_data_check("trans_lz1", "trans_lz2")
    
    # 除掉重复的线路，比如湖南-江西和江西-湖南只需要存在一个就可以了。
    def _check_tx_duplicate_paths(m):
        # 如果同时存在A-B和B-A
        # 湖南-江西，江西-湖南
        forward_paths = set(
            [(m.trans_lz1[tx], m.trans_lz2[tx]) for tx in m.TRANSMISSION_LINES]
        )
        # 江西-湖南，湖南-江西
        reverse_paths = set(
            [(m.trans_lz2[tx], m.trans_lz1[tx]) for tx in m.TRANSMISSION_LINES]
        )
        # 去交集的话，江西-湖南，湖南-江西就会被挑出来，就报错了
        overlap = forward_paths.intersection(reverse_paths)
        if overlap:
            logging.error(
                "Transmission lines have bi-directional paths specified "
                "in input files. They are expected to specify a single path "
                "per pair of connected load zones. "
                "(Ex: either A->B or B->A, but not both). "
                "Over-specified lines: {}".format(overlap)
            )
            return False
        else:
            return True
    # 使用防止是双向传输线路的规则
    mod.check_tx_duplicate_paths = BuildCheck(rule=_check_tx_duplicate_paths)
    # 可以选择的参数，外生的来区分传输线路的数字
    mod.trans_dbid = Param(mod.TRANSMISSION_LINES, default=lambda m, tx: tx, within=Any)
    mod.trans_length_km = Param(mod.TRANSMISSION_LINES, within=NonNegativeReals)
    mod.trans_efficiency = Param(mod.TRANSMISSION_LINES, within=PercentFraction)
    # 已经存在的容量
    mod.existing_trans_cap = Param(mod.TRANSMISSION_LINES, within=NonNegativeReals)
    mod.min_data_check("trans_length_km", "trans_efficiency", "existing_trans_cap")
    # 允许新建容量的传输线路
    mod.trans_new_build_allowed = Param(
        mod.TRANSMISSION_LINES, within=Boolean, default=True
    )
    # 把允许新建容量的传输线路挑出来
    # 能够新建容量的tx和所有period的集合
    mod.TRANS_BLD_YRS = Set(
        dimen=2,
        initialize=mod.TRANSMISSION_LINES * mod.PERIODS,
        filter=lambda m, tx, p: m.trans_new_build_allowed[tx],
    )
    # 新建传输线路的容量，针对可以新建容量的传输线路和决策的周期
    mod.BuildTx = Var(mod.TRANS_BLD_YRS, within=NonNegativeReals)
    
    # 针对输入的tx和period计算一个总的容量
    # 假如所有的决策period包括2023、2028、2033、2038
    # 当前输入的period是2033
    mod.TxCapacityNameplate = Expression(
        mod.TRANSMISSION_LINES,
        mod.PERIODS,
        rule=lambda m, tx, period: sum(
            m.BuildTx[tx, bld_yr]
            # 这个集合应该包括（tx，2023）（tx，2028）（tx，2033）（tx，2038）
            for bld_yr in m.PERIODS
            # 通过这个if筛选过后，剩下（tx，2023）（tx，2028）（tx，2033）累加
            if bld_yr <= period and (tx, bld_yr) in m.TRANS_BLD_YRS
        )
        # 再加上已经存在的容量
        + m.existing_trans_cap[tx],
    )

    #输电走廊的总体降额因子，可以反映强制停电率、稳定性或意外限制。当前输入就默认它是1
    mod.trans_derating_factor = Param(
        mod.TRANSMISSION_LINES, within=PercentFraction, default=1
    )
    # 实际容量中能够获得的容量，在这里x1，就是实际容量
    mod.TxCapacityNameplateAvailable = Expression(
        mod.TRANSMISSION_LINES,
        mod.PERIODS,
        rule=lambda m, tx, period: (
            m.TxCapacityNameplate[tx, period] * m.trans_derating_factor[tx]
        ),
    )
    # 当前输入没有管这个参数，就是默认它是1。扩大特定走廊容量的成本乘数
    mod.trans_terrain_multiplier = Param(
        mod.TRANSMISSION_LINES, within=NonNegativeReals, default=1
    )

    # 如果只存在，江西-湖南这一条线路，实际上表示这个两个区域可以相互联系
    # 那么这个集合存进来的是，江西-湖南，湖南-江西
    def init_DIRECTIONAL_TX(model):
        tx_dir = []
        for tx in model.TRANSMISSION_LINES:
            tx_dir.append((model.trans_lz1[tx], model.trans_lz2[tx]))
            tx_dir.append((model.trans_lz2[tx], model.trans_lz1[tx]))
        return tx_dir

    mod.DIRECTIONAL_TX = Set(dimen=2, initialize=init_DIRECTIONAL_TX)

    # 输入一个lz，其实就是load zones里的每一个z，
    # 然后再对load zone里所有的z进行循环，取出与lz有联系的z
    mod.TX_CONNECTIONS_TO_ZONE = Set(
        mod.LOAD_ZONES,
        dimen=1,
        initialize=lambda m, lz: [
            z for z in m.LOAD_ZONES if (z, lz) in m.DIRECTIONAL_TX
        ],
    )

    def init_trans_d_line(m, zone_from, zone_to):
        for tx in m.TRANSMISSION_LINES:
            if (m.trans_lz1[tx] == zone_from and m.trans_lz2[tx] == zone_to) or (
                m.trans_lz2[tx] == zone_from and m.trans_lz1[tx] == zone_to
            ):
                return tx

    # 针对集合DIRECTIONAL_TX，得到他们之间联系的传输线路tx。可以输入zone from和zone to来得到
    mod.trans_d_line = Param(
        mod.DIRECTIONAL_TX, within=mod.TRANSMISSION_LINES, initialize=init_trans_d_line
    )   

    # dispatch部分 
    # 之所以这样定义，是因为可以双向传输。
    mod.TRANS_TIMEPOINTS = Set(
        dimen=3, initialize=lambda m: m.DIRECTIONAL_TX * m.TIMEPOINTS
    )
    # 虽然只有一条线路江西-湖南，但是调度是双向的，可能从江西到湖南，也可能从湖南到江西
    mod.DispatchTx = Var(mod.TRANS_TIMEPOINTS, within=NonNegativeReals)

    # ###调度约束，上限不能超过当前可调度的容量
    mod.Maximum_DispatchTx = Constraint(
        mod.TRANS_TIMEPOINTS,
        rule=lambda m, zone_from, zone_to, tp: (
            m.DispatchTx[zone_from, zone_to, tp]
            <= m.TxCapacityNameplateAvailable[
                m.trans_d_line[zone_from, zone_to], m.tp_period[tp]
            ]
        ),
    )
    
    #####容量计算部分
    # 输入zone from和zone to，得到传输出去的量
    mod.TxPowerSent = Expression(
        mod.TRANS_TIMEPOINTS,
        rule=lambda m, zone_from, zone_to, tp: (m.DispatchTx[zone_from, zone_to, tp]),
    )
    # 收到的调度量等于传输的量还要x传输效率
    mod.TxPowerReceived = Expression(
        mod.TRANS_TIMEPOINTS,
        rule=lambda m, zone_from, zone_to, tp: (
            m.DispatchTx[zone_from, zone_to, tp]
            * m.trans_efficiency[m.trans_d_line[zone_from, zone_to]]
        ),
    )
    # 计算净传输到区域z的容量，等于所有从别的区域收到的传输量，减去区域z传输出去的量
    def TXPowerNet_calculation(m, z, tp):
        return sum(
            m.TxPowerReceived[zone_from, z, tp]
            for zone_from in m.TX_CONNECTIONS_TO_ZONE[z]
        ) - sum(
            m.TxPowerSent[z, zone_to, tp] for zone_to in m.TX_CONNECTIONS_TO_ZONE[z]
        )

    mod.TXPowerNet = Expression(
        mod.LOAD_ZONES, mod.TIMEPOINTS, rule=TXPowerNet_calculation
    )
    # Register net transmission as contributing to zonal energy balance
    mod.Zone_Power_Injections.append("TXPowerNet")
    
    
    # ######资本成本
    mod.trans_capital_cost_per_mw_km = Param(within=NonNegativeReals, default=1000)
    
    # 传输线路的寿命，好像也没有设置传输线路建成的年份，主要是用来算资本成本的
    mod.trans_lifetime_yrs = Param(within=NonNegativeReals, default=20)
    # 将每年的固定O & M成本描述为资本成本的一小部分。
    mod.trans_fixed_om_fraction = Param(within=NonNegativeReals, default=0.03)
    # Total annual fixed costs for building new transmission lines...
    # Multiply capital costs by capital recover factor to get annual
    # payments. Add annual fixed O&M that are expressed as a fraction of
    # overnight costs.
    
    # 考虑了资本成本和运维成本，计算一个年度成本系数
    mod.trans_cost_annual = Param(
        mod.TRANSMISSION_LINES,
        within=NonNegativeReals,
        initialize=lambda m, tx: (
            m.trans_capital_cost_per_mw_km
            * m.trans_terrain_multiplier[tx]
            * m.trans_length_km[tx]
            * (crf(m.interest_rate, m.trans_lifetime_yrs) + m.trans_fixed_om_fraction)
        ),
    )
    # An expression to summarize annual costs for the objective
    # function. Units should be total annual future costs in $base_year
    # real dollars. The objective function will convert these to
    # base_year Net Present Value in $base_year real dollars.
    
    # 针对每个period计算所有传输线路的固定成本。用tx的总容量x成本系数
    mod.TxFixedCosts = Expression(
        mod.PERIODS,
        rule=lambda m, p: sum(
            m.TxCapacityNameplate[tx, p] * m.trans_cost_annual[tx]
            for tx in m.TRANSMISSION_LINES
        ),
    )
    mod.Cost_Components_Per_Period.append("TxFixedCosts")

def load_inputs(mod, switch_data, inputs_dir):
    """
    Import data related to transmission builds. The following files are
    expected in the input directory. Optional files & columns are marked with
    a *.

    transmission_lines.csv
        TRANSMISSION_LINE, trans_lz1, trans_lz2, trans_length_km,
        trans_efficiency, existing_trans_cap, trans_dbid*,
        trans_derating_factor*, trans_terrain_multiplier*,
        trans_new_build_allowed*

    Note that in the next file, parameter names are written on the first
    row (as usual), and the single value for each parameter is written in
    the second row.

    trans_params.csv*
        trans_capital_cost_per_mw_km*, trans_lifetime_yrs*,
        trans_fixed_om_fraction*
    """
    # TODO: send issue / pull request to Pyomo to allow .csv files with
    # no rows after header (fix bugs in pyomo.core.plugins.data.text)
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "transmission_lines.csv"),
        index=mod.TRANSMISSION_LINES,
        optional_params=(
            "trans_dbid",
            "trans_derating_factor",
            "trans_terrain_multiplier",
            "trans_new_build_allowed",
        ),
        param=(
            mod.trans_lz1,
            mod.trans_lz2,
            mod.trans_length_km,
            mod.trans_efficiency,
            mod.existing_trans_cap,
            mod.trans_dbid,
            mod.trans_derating_factor,
            mod.trans_terrain_multiplier,
            mod.trans_new_build_allowed,
        ),
    )
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "trans_params.csv"),
        optional=True,
        param=(
            mod.trans_capital_cost_per_mw_km,
            mod.trans_lifetime_yrs,
            mod.trans_fixed_om_fraction,
        ),
    )


def post_solve(instance, outdir):
    mod = instance
    normalized_dat = [
        {
            "TRANSMISSION_LINE": tx,
            "PERIOD": p,
            "trans_lz1": mod.trans_lz1[tx],
            "trans_lz2": mod.trans_lz2[tx],
            "trans_dbid": mod.trans_dbid[tx],
            "trans_length_km": mod.trans_length_km[tx],
            "trans_efficiency": mod.trans_efficiency[tx],
            "trans_derating_factor": mod.trans_derating_factor[tx],
            "TxCapacityNameplate": value(mod.TxCapacityNameplate[tx, p]),
            "TxCapacityNameplateAvailable": value(
                mod.TxCapacityNameplateAvailable[tx, p]
            ),
            "TotalAnnualCost": value(
                mod.TxCapacityNameplate[tx, p] * mod.trans_cost_annual[tx]
            ),
        }
        for tx, p in mod.TRANSMISSION_LINES * mod.PERIODS
    ]
    tx_build_df = pd.DataFrame(normalized_dat)
    tx_build_df.set_index(["TRANSMISSION_LINE", "PERIOD"], inplace=True)
    if instance.options.sorted_output:
        tx_build_df.sort_index(inplace=True)
    tx_build_df.to_csv(os.path.join(outdir, "transmission.csv"))
