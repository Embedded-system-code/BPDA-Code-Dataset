from front_analysise.untils.logger.logger import get_logger
from front_analysise.modules.analysise import FrontAnalysise, BackAnalysise
from front_analysise.untils.config import ANALYSIZER, B_FILTERS, F_FILTERS, API_SPLIT_MARCH, FROM_BIN_ADD, \
    UPNP_ANALYSISE
from front_analysise.untils.output import Output
from front_analysise.untils.tools import runtimer
from front_analysise.tools.upnpanalysise import UpnpAnalysise
from config import GHIDRA_SCRIPT, HEADLESS_GHIDRA
from ..Backward.CPFinder_libc import *
from ..Backward.CPFinder_libc_traceback import *

import datetime
import subprocess
import shutil
import argparse
import uuid
import os

import sys

sys.setrecursionlimit(5000)

front_result_output = ""
ghidra_result_output = ""

log = get_logger()

scripts = {
    "ref2share": os.path.join(GHIDRA_SCRIPT, "ref2share.py"),
    "ref2sink_bof": os.path.join(GHIDRA_SCRIPT, "ref2sink_bof.py"),
    "ref2sink_cmdi": os.path.join(GHIDRA_SCRIPT, "ref2sink_cmdi.py"),
    "share2sink": os.path.join(GHIDRA_SCRIPT, "share2sink.py")
}

def argsparse():
    
    parser = argparse.ArgumentParser(description="Taint tool",
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-d", "--directory", required=True, metavar="/root/path/_ac18.extracted",
                        help="Directory of the file system after firmware decompression")

    
    parser.add_argument("-o", "--output", required=True, metavar="/root/output",
                        help="Folder for output results ")
    
    parser.add_argument("--ghidra_script", required=False,
                        choices=["ref2sink_cmdi", "ref2sink_bof", "share2sink", "ref2share", "all"],
                        action="append",
                        help="ghidra script to run"
                        )
    parser.add_argument("--ref2share_result", required=False, metavar="/root/path/ref2share_result",
                        help="This input is this parameter is the result of ref2share")

    parser.add_argument("--save_ghidra_project", required=False, action="store_true",
                        help="whether to save the ghidra project")

    
    parser.add_argument("--taint_check", required=False, action="store_true", default=False,
                        help="Enable taint analysis")

    
    
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-b", "--bin", required=False, action="append", metavar="/var/ac18/bin/httpd",
                       help="Input border bin")
    group.add_argument("-l", "--len", required=False, default=3, type=int, metavar="3", help="Take the first few")

    args = parser.parse_args()

    
    global ghidra_result_output, front_result_output
    front_result_output = os.path.join(args.output, "keyword_extract_result")
    ghidra_result_output = os.path.join(args.output, "ghidra_extract_result")

    
    if not os.path.isdir(args.directory):
        log.error("Firmware path entered : {} not found".format(args.directory))
        sys.exit()

    
    if not os.path.isdir(front_result_output):
        log.info("Init output keyword_extract_result directory : {} ".format(front_result_output))
        os.makedirs(front_result_output)

    if args.ghidra_script:
        
        if not os.path.isdir(ghidra_result_output):
            log.info("Init output ghidra_extract_result directory : {} ".format(ghidra_result_output))
            os.makedirs(ghidra_result_output)

    return args

def front_analysise(args):
    
    remove_keyword_collection = []
    remove_function_collection = []

    runtimer.set_step1()
    f_analysise = FrontAnalysise(args.directory)
    f_analysise.analysise(ANALYSIZER)

    runtimer.set_step2()
    f_res = f_analysise.get_analysise_result()
    f_remove_file = f_analysise.get_remove_file()

    
    upapanalysise = set()
    if UPNP_ANALYSISE:
        upnpanaly = UpnpAnalysise(args.directory)
        upapanalysise = upnpanaly.get_result()

    runtimer.set_step3()
    for _F in F_FILTERS:
        f = _F()
        f()

        remove_keyword = f.get_remove_keyword()
        remove_func = f.get_remove_functions()

        remove_keyword_collection = list(set(remove_keyword + remove_keyword_collection))
        remove_function_collection = list(set(remove_func + remove_function_collection))

    runtimer.set_step4()
    if args.bin:
        b_analysise = BackAnalysise(args.directory, args.bin)
    else:
        b_analysise = BackAnalysise(args.directory)
    b_analysise.analysise()
    names = b_analysise.getbinname_and_path()

    
    for _F in B_FILTERS:
        f = _F()
        f()
        remove_keyword = f.get_remove_keyword()
        remove_func = f.get_remove_functions()

        remove_keyword_collection = list(set(remove_keyword + remove_keyword_collection))
        remove_function_collection = list(set(remove_func + remove_function_collection))

        
        b_analysise.delete_function(remove_func)
        b_analysise.delete_keyword(remove_keyword)

    
    api_match_results = set()
    if API_SPLIT_MARCH:
        api_match_results = b_analysise.api_march()

    runtimer.set_end_time()
    
    res = b_analysise.get_result()

    
    border_bin = []
    if not args.bin:
        for bin in res[:args.len]:
            pth = bin["name"]
            name = pth.split("/")[-1]
            border_bin.append((name, pth))
    else:
        for f_name, f_path in names:
            border_bin.append((f_name, f_path))

    
    o = Output(res, front_result_output)
    o.custom_write()

    
    o.write_file_info(f_res)
    o.write_remove_info(remove_function_collection, remove_keyword_collection)

    o.write_info()

    o.write_remove_jsfile(f_remove_file)
    o.write_api_split(api_match_results)

    if FROM_BIN_ADD:
        o.write_from_bin_add()
        o.write_from_bin_add_v2()

    if UPNP_ANALYSISE:
        res = b_analysise.get_upnp_result()
        o.write_upnp_keywords(res)
        o.write_upnp_analysise(upapanalysise)

    return border_bin

def ghidra_analysise(args, border_bin):

    ghidra_scripts = args.ghidra_script

    if "all" in ghidra_scripts:
        ghidra_scripts = ["ref2share", "ref2sink_bof", "ref2sink_cmdi"]

    ghidra_project = os.path.join(ghidra_result_output, "ghidra_project")

    
    if not os.path.isdir(ghidra_project):
        os.makedirs(ghidra_project)

    
    for s in ghidra_scripts:
        keyword_file = ""
        if s == "share2sink" and args.ref2share_result:
            keyword_file = args.ref2share_result
        exec_script = scripts.get(s, "")
        if exec_script == "":
            log.error("没有找到%s脚本", args.ghidra_script)

        random = uuid.uuid4().hex

        for binname, binpath in border_bin:
            if not keyword_file:
                keyword_file = os.path.join(front_result_output, "simple", ".data", binname + ".result")
            ghidra_rep = os.path.join(ghidra_project, binname + "_" + s) + ".rep"

            bin_ghidra_project = os.path.join(ghidra_result_output, binname)

            if not os.path.isdir(bin_ghidra_project):
                os.makedirs(bin_ghidra_project)

            
            print("copy {} to {}".format(binname, bin_ghidra_project))
            shutil.copy2(binpath, bin_ghidra_project)

            output_name = os.path.join(bin_ghidra_project, "{}_{}.result".format(binname, s))

            project_name = binname + "_" + s + random

            ghidra_args = [
                HEADLESS_GHIDRA, ghidra_project, project_name,
                '-postscript', exec_script, keyword_file, output_name,
                '-scriptPath', os.path.dirname(exec_script)
            ]
            if os.path.exists(ghidra_rep):
                ghidra_args += ['-process', os.path.basename(binpath)]
            else:
                ghidra_args += ['-import', "'" + binpath + "'"]

            p = subprocess.Popen(ghidra_args)
            p.wait()

    
    if not args.save_ghidra_project:
        shutil.rmtree(ghidra_project)

def main():
    start_time = datetime.datetime.now()
    log.info("Start analysis time : {}".format(str(start_time)))
    args = argsparse()

    if args.ghidra_script and args.taint_check:
        
        from taint_check.main import taint_stain_analysis
        from taint_check.bug_finder.config import checkcommandinjection, checkbufferoverflow

        global checkcommandinjection, checkbufferoverflow

        log.info("Start taint check ... ")

        for bin_name, bin_path in bin_list:
            for gs in args.ghidra_script:
                if gs in ["ref2sink_bof", "ref2sink_cmdi"]:
                    ghidra_result = "result-libc.txt"
                    if gs == "ref2sink_bof":
                        checkbufferoverflow = True
                        checkcommandinjection = False
                    if gs == "ref2sink_cmdi":
                        checkbufferoverflow = False
                        checkcommandinjection = True

                    
                    taint_stain_analysis(bin_path, ghidra_result, args.output)

        log.info("End taint check ...")
    end_time = datetime.datetime.now()

    log.info("Total time : {}s".format((start_time-end_time).seconds))

if __name__ == "__main__":
    main()
