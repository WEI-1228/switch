from utils import *
import os

energy_list = ['Coal', 'PV', 'Wind', 'Gas', 'Hydro', 'Nuclear']

charging_csv_path = "/home/ljw/switch/input1/outputs-带电动汽车/ChargingPower.csv"
discharging_csv_path = "/home/ljw/switch/input1/outputs-带电动汽车/DischargingPower.csv"

print("正在加载数据")
_, charging_list, zones = parse_input(charging_csv_path)
_, discharging_list, zones = parse_input(discharging_csv_path)

# tps = '2025.01.22'
tps = None
tps_norm_factor=12

if not tps:
    assert tps_norm_factor > 1, "没有设置日期，必须指定日期的数量 tps_norm_factor ，来做平均"
else:
    tps_norm_factor = 1

for i, z in enumerate(zones):
    print(f"{i + 1}/{len(zones)} 省份 ：{z:50}", end='\r')
    filter_data = filter_by_zone(charging_list, z, tps)
    merge_data = merge_data_by_tps(filter_data, tps_norm_factor)
    
    ev_filter_data = filter_by_zone(discharging_list, z, tps)
    ev_merge_data = merge_data_by_tps(ev_filter_data, tps_norm_factor)
    
    charging_dto = DataObj(merge_data, "charging", 'o', tps)
    discharging_dto = DataObj(ev_merge_data, "discharging", 'x', tps)
    
    if tps:
        save_path = f"ev/{tps}/{z}/"
    else:
        save_path = f"ev/avg/{z}/"
    os.makedirs(save_path, exist_ok=True)
    plot_by_tps(charging_dto, f"{z}-Charging", "Timepoints", "MW", save_path + "Charging.jpg")
    plot_by_tps(discharging_dto, f"{z}-DisCharging", "Timepoints", "MW", save_path + "Discharging.jpg")