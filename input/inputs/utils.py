def parse_input(filename):
    fin = open(filename)
    header = fin.readline().strip().split(',')
    data = []
    for line in fin:
        data.append(line.strip().split(','))
    fin.close()
    return header, data

def save_file(header, data, filename):
    fout = open(filename, 'w')
    fout.write(','.join(header) + '\n')
    for d in data:
        fout.write(','.join(d) + '\n')
    fout.close()

def do_filter(header, data_list, remove_column:list=None, remove_condition:dict=None, save_condition:dict=None):
    name_to_idx = {name:idx for (idx, name) in enumerate(header)}
    remove_idx = None
    if remove_column: 
        remove_idx = [name_to_idx[h] for h in header]
        header = [h for h in header if h not in remove_column]
        
    new_data = []
    for data in data_list:
        add_flag = False
        if save_condition:
            for name, save_con in save_condition.items():
                for con in save_con:
                    if con in data[name_to_idx[name]]:
                        add_flag = True
                    
        if add_flag:
            if remove_idx: data = [data[i] for i in range(len(data)) if i not in remove_idx]
            new_data.append(data)
            continue
        
        del_flag = False
        if remove_condition:
            for name, remove_con in remove_condition.items():
                for con in remove_con:
                    if con in data[name_to_idx[name]]:
                        del_flag = True

        if del_flag:
            continue
        
        if remove_idx: data = [data[i] for i in range(len(data)) if i not in remove_idx]
        new_data.append(data)
    
    return header, new_data

if __name__ == '__main__':
    header, data = parse_input("gen_info.csv")
    new_header, new_data = do_filter(header, data,
                                     remove_condition={"GENERATION_PROJECT":["Hydro_Pumped"]})
    print(new_data[0])
    save_file(new_header, new_data, "a.csv")