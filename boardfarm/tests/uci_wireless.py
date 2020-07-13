# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import re

from boardfarm.devices import prompt
from boardfarm.lib.wifi import wifi_interface
from boardfarm.tests import rootfs_boot


class UciShowWireless(rootfs_boot.RootFSBootTest):
    """UCI lists wifi interfaces."""

    def runTest(self):
        """Start test to list wifi interfaces by UCI."""
        board = self.dev.board

        wlan_iface = wifi_interface(board)
        if wlan_iface is None:
            self.skipTest("No wifi interfaces detected, skipping..")

        board.sendline("\nuci show wireless")
        board.expect("uci show wireless")
        board.expect(prompt)
        wifi_interfaces = re.findall("wireless.*=wifi-device", board.before)
        self.result_message = "UCI shows %s wifi interface(s)." % (len(wifi_interfaces))
        self.logged["num_ifaces"] = len(wifi_interfaces)
        # Require that at least one wifi interface is present
        assert len(wifi_interfaces) > 0
