import utils

header, datas = utils.parse_input('zone_coincident_peak_demand_bak.csv')

filter_data = []
for data in datas:
    if '2023' == data[1]:
        filter_data.append(data)

utils.save_file(header, filter_data, 'zone_coincident_peak_demand.csv')