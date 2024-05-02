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
        output_data.append(sp)


fout = open("gen_info.csv", 'w')
fout.write(','.join(header) + '\n')
for line in output_data:
    fout.write(','.join(line) + '\n')