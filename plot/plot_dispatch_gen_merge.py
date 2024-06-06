from utils import *
import os

energy_list = ['Coal', 'Gas', 'Nuclear']

noev_csv_path = "/home/ljw2022/switch/input/outputs/DispatchGen.csv"
ev_csv_path = "/home/ljw2022/switch/input/outputs/DispatchGen.csv"

print("正在加载数据")
_, data_list, zones = parse_input(noev_csv_path)
_, ev_data_list, zones = parse_input(ev_csv_path)

# tps = '2025.01.22'
tps = None
tps_norm_factor=12

if not tps:
    assert tps_norm_factor > 1, "没有设置日期，必须指定日期的数量 tps_norm_factor ，来做平均"
else:
    tps_norm_factor = 1


def merge(dict1, dict2):
    new_dict = {}
    for k, v in dict1.items():
        new_dict[k] = new_dict.get(k, 0) + v
    for k, v in dict2.items():
        new_dict[k] = new_dict.get(k, 0) + v
    return new_dict

for i, z in enumerate(zones):
    print(f"{i + 1}/{len(zones)} 省份 ：{z:50}", end='\r')
    merge_energy_data = {}
    ev_merge_energy_data = {}
    for e in energy_list:
        filter_data = filter_by_zone_and_type(data_list, z, e, tps)
        merge_data = merge_data_by_tps(filter_data, tps_norm_factor)
        merge_energy_data = merge(merge_energy_data, merge_data)
        
        ev_filter_data = filter_by_zone_and_type(ev_data_list, z, e, tps)
        ev_merge_data = merge_data_by_tps(ev_filter_data, tps_norm_factor)
        ev_merge_energy_data = merge(ev_merge_energy_data, ev_merge_data)
    
    dto = DataObj(merge_energy_data, "no-ev", 'o', tps)
    ev_dto = DataObj(ev_merge_energy_data, "ev", 'x', tps)
    
    if tps:
        save_path = f"dispatch_gen_merge/{tps}/{z}/"
    else:
        save_path = f"dispatch_gen_merge/avg/{z}/"
    os.makedirs(save_path, exist_ok=True)
    # plot_by_tps([dto, ev_dto], f"{z}-{e}", "Timepoints", "MW", save_path + f"{e}.jpg")
    plot_by_tps(ev_dto, z, "Timepoints", "MW", save_path + f"merge.jpg")