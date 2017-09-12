# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import rootfs_boot
from devices import board, wan, lan, wlan, prompt

class OEVersion(rootfs_boot.RootFSBootTest):
    '''Record OE version'''
    def runTest(self):
        board.sendline('cat /etc/os-release')
        # PRETTY_NAME=RDK (A Yocto Project 1.6 based Distro) 2.0 (krogoth)
        board.expect('PRETTY_NAME=([^\s]*) \(A Yocto Project ([^\s]*) based Distro\) ([^\s]*) \(([^\)]*)\)')
        print("#########################################")
        print("bsp-type = %s" % board.match.group(1))
        print("oe-version = %s" % board.match.group(2))
        print("bsp-version = %s" % board.match.group(3))
        print("oe-version-string = %s" % board.match.group(4))
        print("#########################################")

        self.result_message="BSP = %s, BSP version = %s, OE version = %s, OE version string = %s" % \
                (board.match.group(1), board.match.group(3), board.match.group(2), board.match.group(4))
        self.logged['bsp-type'] = board.match.group(1)
        self.logged['oe-version'] = board.match.group(2)
        self.logged['bsp-version'] = board.match.group(3)
        self.logged['oe-version-string'] = board.match.group(4)
        board.expect(prompt)
