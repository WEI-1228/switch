import os

fin = open("gen_info_bak.csv")
data_line = []

headers = fin.readline().strip().split(',') + ['gen_is_reconnected', 'gen_is_grid_connected', 'gen_is_distributed', 'storage_max_power_mw']
header_to_idx = {h:i for (i, h) in enumerate(headers)}

for line in fin:
    sp = line.strip().split(',')
    t = sp[0]
    if 'Battery_Storage' in sp[0]:
        sp[0] = t + '-1'
        data_line.append(sp + ['TRUE', 'FALSE', 'FALSE', '10'])
        sp[0] = t + '-2'
        data_line.append(sp + ['FALSE', 'TRUE', 'FALSE', '10'])
        sp[0] = t + '-3'
        data_line.append(sp + ['FALSE', 'FALSE', 'TRUE', '10'])


for data in data_line:
    if data[header_to_idx["gen_is_grid_connected"]] == 'TRUE':
        data[header_to_idx["gen_can_provide_spinning_reserves"]] = 'TRUE'
    else:
        data[header_to_idx["gen_can_provide_spinning_reserves"]] = 'FALSE'

bad_header = ['gen_is_cogen', 'gen_is_pumped_hydro', 'gen_can_provide_quickstart_reserves']
filter_header = [header for header in headers if header not in bad_header]

filter_id = [header_to_idx[x] for x in filter_header]

filter_header[0] = 'STORAGE_PROJECT'
filter_header = [x.replace('gen_', 'str_') for x in filter_header]

fout = open("str_info.csv", 'w')
fout.write(','.join(filter_header) + '\n')
for line in data_line:
    new_line = [line[i] for i in filter_id]
    fout.write(','.join(new_line) + '\n')