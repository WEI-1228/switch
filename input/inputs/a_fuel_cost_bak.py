import utils

header, datas = utils.parse_input("fuel_cost_bak.csv")

new_data = []
for data in datas:
    if '2023' == data[2]:
        new_data.append(data)
        
utils.save_file(header, new_data, "fuel_cost.csv")