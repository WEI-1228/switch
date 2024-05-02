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

if __name__ == '__main__':
    header, data = parse_input("gen_info.csv")
    print(header)