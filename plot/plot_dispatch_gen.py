from utils import *
import os

energy_list = ['Coal', 'PV', 'Wind', 'Gas', 'Hydro', 'Nuclear']

noev_csv_path = "/home/ljw/switch/input1/outputs/DispatchGen.csv"
ev_csv_path = "/home/ljw/switch/input1/outputs-带电动汽车/DispatchGen.csv"

print("正在加载数据")
_, data_list, zones = parse_input(noev_csv_path)
_, ev_data_list, zones = parse_input(ev_csv_path)

tps = '2025.01.22'

for e in energy_list:
    print(f"正在画 {e}", end=" ")
    for i, z in enumerate(zones):
        print(f"省份 {i + 1}/{len(zones)}：{z:20}", end='\r')
        filter_data = filter_by_zone_and_type(data_list, z, e, tps)
        merge_data = merge_data_by_tps(filter_data)
        
        ev_filter_data = filter_by_zone_and_type(ev_data_list, z, e, tps)
        ev_merge_data = merge_data_by_tps(ev_filter_data)
        
        dto = DataObj(merge_data, "no-ev", 'o')
        ev_dto = DataObj(ev_merge_data, "ev", 'x')
        
        save_path = f"diapatch_gen/{z}/"
        os.makedirs(save_path, exist_ok=True)
        plot_by_tps([dto, ev_dto], f"{z}-{e}", "Timepoints", "MW", save_path + f"{e}.jpg")
    print()