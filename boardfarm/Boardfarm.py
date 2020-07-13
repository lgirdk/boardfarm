#!/usr/bin/env python
# Copyright (c) 2019
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import os
import subprocess

import boardfarm

from .dbclients import boardfarmwebclient


class Boardfarm(object):
    """This class makes it easy to interact with the boardfarm server, and to run tests."""

    def __init__(self, bfconfig_url, debug=False):
        """Parameters: bfconfig_url: location of boardfarm config file.

        debug: if True, there will be much more verbose output.
        """
        self.bfconfig_url = bfconfig_url
        self.server = boardfarmwebclient.BoardfarmWebClient(
            bfconfig_url, bf_version=boardfarm.__version__, debug=debug
        )
        self.debug = debug

    def list_tests(self):
        """Search for all available tests and return a dict."""
        from boardfarm import tests, config

        tests.init(config)
        return tests.available_tests

    def list_stations(self):
        """Query boardfarm server for stations and return a dict."""
        for name in self.server.bf_config:
            print("%s" % name)

    def _supported_devices(self):
        """Create list of supported device names that can be used in tests."""
        from boardfarm import devices

        devs = []
        for f in devices.device_mappings:
            devs += [n.__name__ for n in devices.device_mappings[f]]
        return sorted(devs)

    def run_bft(self, board_type, testsuite):
        """Run the boardfarm tests using the 'bft' command-line tool."""
        output_dir = os.path.join(os.getcwd(), "results")
        print("Trying to run bft ...")
        cmd = ""
        if self.debug:
            cmd += "export BFT_DEBUG=%s ; " % self.debug
        cmd += "bft -b {b} --testsuite {t} -c {c} -o {o}".format(
            b=board_type, t=testsuite, c=self.bfconfig_url, o=output_dir
        )
        print(cmd)
        subprocess.check_output(cmd, shell=True)
        print("Results in %s" % output_dir)
        print("\n".join(os.listdir(output_dir)))
