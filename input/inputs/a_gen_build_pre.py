import utils

header, datas = utils.parse_input("gen_build_predetermined_bak.csv")

header, new_datas = utils.do_filter(
    header,
    datas,
    remove_condition={
        "GENERATION_PROJECT":["Hydro_Pumped"]
    }
)

utils.save_file(header, new_datas, "gen_build_predetermined.csv")