import matplotlib.pyplot as plt

class DataObj:
    def __init__(self, data, annotation, mark):
        self.data = data
        self.annotation = annotation
        self.mark=mark
        
    def get_tps_list(self):
        tps_list = list(self.data.keys())
        tps_list.sort()
        return tps_list
    
    def get_value_list(self):
        tps_list = self.get_tps_list()
        data_list = [self.data[tps] for tps in tps_list]
        return data_list

def parse_input(filename):
    fin = open(filename)
    header = fin.readline().strip().split(',')
    zones = set()
    data = []
    for line in fin:
        line = line.strip()
        sp = line.split(',')
        if not line:
            continue
        data.append(sp)
        z = sp[0].split('-')[0]
        zones.add(z)
    fin.close()
    return header, data, list(zones)


def filter_by_zone_and_type(data_list:list, zone:str, etype:str, tps=None):
    """
    根据地区和该地区的能源类型过滤数据\n
    时间点是可选的参数\n
    必须保证数据的第一列包含地区和能源类型的信息
    """
    filter_data = []
    for data in data_list:
        if zone in data[0] and etype in data[0]:
            if tps and tps not in data[1]:
                continue
            filter_data.append(data)
    return filter_data


def merge_data_by_tps(data_list):
    """
    根据时间点合并数据，将同一个时间点的数据全部加起来\n
    返回：{tps1: v1, tps2: v2, ...}
    """
    data_dict = {}
    for _, tps, v in data_list:
        if tps not in data_dict:
            data_dict[tps] = 0
        data_dict[tps] += float(v)
    return data_dict



def plot_by_tps(dataObj, title, xlabel, ylabel, save_path):
    """
    数据格式必须是：{tps1: v1, tps2: v2, ...}\\
    `merge_data_by_tps`返回的数据可以直接传入
    """
    if isinstance(dataObj, DataObj):
        dataObj = [dataObj]
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    tps_list = dataObj[0].get_tps_list()
    plt.xticks(range(len(tps_list)), labels=tps_list, rotation=45, ha='right')
    
    for data in dataObj:
        plt.plot(range(len(tps_list)), data.get_value_list(), label=data.annotation, marker=data.mark)
    
    plt.tight_layout()
    plt.legend()
    
    plt.savefig(save_path, dpi=300)
    plt.clf()