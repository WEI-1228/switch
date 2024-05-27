import utils
fin = open("gen_info_bak.csv")

header = fin.readline().strip().split(',')
header.append("variable_gen_cost")
output_data = []

for line in fin:
    sp = line.strip().split(',')
    if 'Battery_Storage' in sp[0]:
        pass
    else:
        if sp[3] in ['Solar', 'Wind']:
            sp.append('1') # variable_gen_cost
        else:
            sp.append('0') # variable_gen_cost
        
        # gen_can_provide_spinning_reserves = header.index("gen_can_provide_spinning_reserves")
        # gen_energy_source = header.index("gen_energy_source")
        # if sp[gen_energy_source] in ['Coal', 'Gas', 'Uranium']:
        #     sp[gen_can_provide_spinning_reserves] = 'TRUE'
        # else:
        #     sp[gen_can_provide_spinning_reserves] = 'FALSE'
        output_data.append(sp)

header, output_data = utils.do_filter(header, output_data,
                                     remove_condition={"GENERATION_PROJECT":["Hydro_Pumped"]})

fout = open("gen_info.csv", 'w')
fout.write(','.join(header) + '\n')
for line in output_data:
    fout.write(','.join(line) + '\n')
