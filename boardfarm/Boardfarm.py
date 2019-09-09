#!/usr/bin/env python
# Copyright (c) 2019
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import devices

from dbclients import boardfarmwebclient


class Boardfarm(object):
    
    def __init__(self, url, debug=False):
        self.server = boardfarmwebclient.BoardfarmWebClient(url, debug=debug)
        self.supported_devices = self._supported_devices()

    def list_tests(self):
        pass

    def list_stations(self):
        for name in self.server.bf_config:
            print("%s" % name)

    def _supported_devices(self):
        '''Create list of supported device names that can be used in tests.'''
        devs = []
        for f in devices.device_mappings:
            devs += [n.__name__ for n in devices.device_mappings[f]]
        return sorted(devs)
