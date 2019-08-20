# Copyright (c) 2018
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import pexpect
import rootfs_boot
from boardfarm.devices import board, wan, lan, wlan, prompt

class TCPDumpWANandLAN(rootfs_boot.RootFSBootTest):
    '''Captures traces for WAN and LAN devices'''

    opts = ""

    def runTest(self):
        for d in [wan, lan]:
            d.sendline('tcpdump -i %s -w /tmp/tcpdump.pcap %s' % (d.iface_dut, self.opts))

        board.expect(pexpect.TIMEOUT, timeout=15)

        for d in [wan, lan]:
            d.sendcontrol('c')

        # TODO: copy dumps to results/ dir for logging

class TCPDumpWANandLANfilterICMP(TCPDumpWANandLAN):
    opts = "icmp"
