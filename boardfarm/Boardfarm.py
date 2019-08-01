# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.
#!/usr/bin/env python

import os
import subprocess

class Boardfarm(object):
    '''
    Runs 'bft'
    '''

    def __init__(self, config_url):
        self.config_url = config_url

    def run(self, board_type, testsuite):
        output_dir = os.path.join(os.getcwd(), "results")
        print("Trying to run bft ...")
        cmd = "bft -b {b} --testsuite {t} -c {c} -o {o}".format(b=board_type,
                                                                t=testsuite,
                                                                c=self.config_url,
                                                                o=output_dir)
        print(cmd)
        result = subprocess.check_output(cmd, shell=True)
        print("Results in %s" % output_dir)
        print("\n".join(os.listdir(output_dir)))
