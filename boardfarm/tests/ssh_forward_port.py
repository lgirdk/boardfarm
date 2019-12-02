# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

from boardfarm.tests import rootfs_boot
from boardfarm import lib
import pexpect

from boardfarm.devices import board, wan

class SshWanDetect(rootfs_boot.RootFSBootTest):
    '''Can access main web GUI page.'''
    @lib.common.run_once
    def runTest(self):
        super(SshWanDetect, self).runTest()

        board.uci_allow_wan_ssh()

        ipaddr = board.get_interface_ipaddr(board.wan_iface)
        port = "22"

        if wan:
            t = wan
        else:
            t = pexpect.spawn("bash")
        t.close()

        sp = lib.bft_pexpect_helper.spawn_ssh_pexpect(ipaddr, "root",
                "password", prompt="root@OpenWrt", port=port, via=wan)
        sp.sendline("exit")
