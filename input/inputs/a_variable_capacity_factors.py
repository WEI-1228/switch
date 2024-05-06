import utils

header, datas = utils.parse_input("variable_capacity_factors_bak.csv")

new_data = []
for data in datas:
    if '2025' in data[1]:
        new_data.append(data)
        
utils.save_file(header, new_data, "variable_capacity_factors.csv")