import utils

header, datas = utils.parse_input('loads_bak.csv')

filter_data = []
for data in datas:
    if '2025' in data[1]:
        filter_data.append(data)

utils.save_file(header, filter_data, 'loads.csv')