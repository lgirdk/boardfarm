#!/usr/bin/env python
# Copyright (c) 2019
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

from dbclients import boardfarmwebclient


class Boardfarm(object):
    
    def __init__(self, url, debug=False):
        self.server = boardfarmwebclient.BoardfarmWebClient(url, debug=debug)

    def list_tests(self):
        pass

    def list_stations(self):
        for name in self.server.bf_config:
            print("%s" % name)
