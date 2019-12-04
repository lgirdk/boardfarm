# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import importlib
import glob
import os
import requests
import json

import boardfarm

local_path = os.path.dirname(os.path.realpath(__file__))

# Boardfarm configuration describes test stations - see boardfarm doc.
# Can be local or remote file.
boardfarm_config_location = os.environ.get('BFT_CONFIG', os.path.join(local_path, 'boardfarm_config_example.json'))

# Test Suite config files. Standard python config file format.
testsuite_config_files = [os.path.join(local_path, 'testsuites.cfg'), ]
# Files named 'layerconf.py' can contain extra code needed to run
layerconfs = []

for modname in sorted(boardfarm.plugins):
    overlay = os.path.dirname(boardfarm.plugins[modname].__file__)
    # Find testsuite config files
    testsuites_path = glob.glob(os.path.join(overlay, 'testsuites.cfg')) + \
                      glob.glob(os.path.join(overlay, '*', 'testsuites.cfg'))
    testsuite_config_files += testsuites_path
    # Find layerconf files and import them
    layerconf_path = glob.glob(os.path.join(overlay, 'layerconf.py')) + \
                     glob.glob(os.path.join(overlay, '*', 'layerconf.py'))
    for f in layerconf_path:
        if os.path.isfile(f):
            location = os.path.dirname(f)
            m = os.path.basename(location)+'.'+os.path.basename(f.strip('.py'))
            tmp = importlib.import_module(m)
            layerconfs.append((location, tmp))

# Logstash server - a place to send JSON-format results to
# when finished. Set to None or name:port, e.g. 'logstash.mysite.com:1300'
logging_server = None

# Elasticsearch server. Data in JSON-format can be directly sent here.
# Set to None or to a valid host, see documentation:
#     https://elasticsearch-py.readthedocs.org/en/master/api.html#elasticsearch
elasticsearch_server = os.environ.get('BFT_ELASTICSERVER', None)

# MongoDB server. Data in JSON-format can be directly sent here.
mongodb = {"host": os.environ.get('BFT_MONGOHOST', None),
           "username": os.environ.get('BFT_MONGOUSER', None),
           "password": os.environ.get('BFT_MONGOPASS', None)
           }

# Code change server like gerrit, github, etc... Used only in display
# of the results html file to list links to code changes tested.
code_change_server = None

# creates a small dictionary of all the options
# this  will probably grow as options are added
option_dict = {
        "proxy":["normal","socks5"],
        "webdriver":["chrome","ffox"],
        "disp":["xvfb", "xephyr", "xvnc"],
        "disp_port":["0"],
        "disp_size":["1366x768"]
        }

# the syntax is
# BFT_OPTIONS="proxy=normal webdriver=chrome"
default_proxy_type = "normal"
default_web_driver = "ffox"
default_display_backend = "xvnc"
default_display_backend_port = "0" # i.e. use any available ports
default_display_backend_size = "1366x768"

if 'BFT_OPTIONS' in os.environ:
    for option in os.environ['BFT_OPTIONS'].split(' '):
        k,v = option.split(':')
        if option_dict.get(k) and (v in option_dict[k]):
            if k == "proxy":
                default_proxy_type = v
            if k == "webdriver":
                default_web_driver  = v
            if k == "disp":
                default_display_backend = v
        elif k == "disp_port":
            # quick validation
            i = int(v) # if not a valid num python will throw and exception
            if i != 0 and not 1024 <= i <= 65535:
                print("Warning: display backend port: %i not in range (1024-65535)" % i)
                exit(1)
            default_display_backend_port = v
        elif k == "disp_size":
            default_display_backend_size = v
        else:
            print("Warning: Ignoring option: %s (misspelled?)" % option)

def get_display_backend_size():
    xc,yc = default_display_backend_size.split('x')
    x = int(xc)
    y = int(yc)
    return x,y

if 'BFT_DEBUG' in os.environ:
    print("Using proxy:"+default_proxy_type)
    print("Using webdriver:"+default_web_driver)
    print("Using disp:"+default_display_backend)
    print("Using disp_port:"+default_display_backend_port)
    print("Using disp_size:"+default_display_backend_size)

# BFT_ARGS points to json file for test args.
# File needs to be a flat json.
test_args_location = os.environ.get('BFT_ARGS', None)
test_args = {}

# The following is a dictionary use for the error injection feature
# if populated the code will attempt to intercept the
# "class_name" obj."function_name" and return value_to_be_returned/
# instead of running the actual function.

err_injection_dict = {}

def update_error_injection_dict(err_dict):
    """
    Updates the error injection dictionary (empty by default) from a list of json files.
    The dictionary basic structure is
    {
      "class_name":
      {
         "function_name": value_to_be_returned
      }
    }


    :param err_dict: A list of filepaths (or http) that contains the error dictionary in json format
    :type err_dict: list, strings

    Returns:

    :return: err_injection_dict (dict) the updated error injection dictionary
    :rtype: dict
    """

    if type(err_dict) is not list:
        err_dict = [err_dict]

    for d in err_dict:
        try:
            if 'BFT_DEBUG' in os.environ:
                print("Processing: '{}'".format(d))
            if d.startswith("http"):
                data = requests.get(d).json()
                err_injection_dict.update(requests.get(d).json())
            else:
                data = open(d, 'r').read()
                err_injection_dict.update(json.loads(data))
        except:
            print("Failed to fetch error dictionay at '{}', skipping...".format(d))

    if err_injection_dict:
        print("Error injection dictionary:")
        print(json.dumps(err_injection_dict, indent=4))
    return err_injection_dict


def get_err_injection_dict():
    """
    Gets the error injection dictionary

    :return: err_injection_dict (dict): the error injection dictionary
    :rtype: dict
    """
    return err_injection_dict
