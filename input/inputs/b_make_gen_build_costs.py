import utils
import copy

header, datas = utils.parse_input('gen_build_costs_bak.csv')

common_data = []
storage_data = []

for data in datas:
    if 'Battery_Storage' in data[0]:
        t = data[0]
        data[0] = t + '-1'
        storage_data.append(copy.copy(data))
        data[0] = t + '-2'
        storage_data.append(copy.copy(data))
        data[0] = t + '-3'
        storage_data.append(copy.copy(data))
    else:
        common_data.append(data)

new_header = copy.copy(header)
new_header[0] = 'STORAGE_PROJECT'
new_header = [h.replace('gen', 'str') for h in new_header]
utils.save_file(new_header, storage_data, "str_build_costs.csv")
utils.save_file(header, common_data, "gen_build_costs.csv")