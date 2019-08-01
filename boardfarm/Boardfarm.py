# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.
#!/usr/bin/env python

import subprocess

class Boardfarm(object):
    '''
    Runs 'bft'
    '''

    def __init__(self, config_url):
        self.config_url = config_url

    def run(self):
        print("Trying to run bft ...")
        cmd = "bft -b mv1 --testsuite basic -c http://172.19.17.134/boardfarm/api/bf_config"
        result = subprocess.check_output("bft --version", shell=True)
        #print("result:")
        #print(result)

