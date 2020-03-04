# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

from boardfarm.tests import rootfs_boot
from boardfarm.devices import board
from boardfarm.devices import prompt


class OEVersion(rootfs_boot.RootFSBootTest):
    '''Record OE version'''
    def runTest(self):
        board.sendline('cat /etc/os-release')
        # PRETTY_NAME=RDK (A Yocto Project 1.6 based Distro) 2.0 (krogoth)
        if 0 == board.expect([
                "cat: can't open '/etc/os-release': No such file or directory",
                'PRETTY_NAME=([^\s]*) \(A Yocto Project (?:[^\s]*?)\s?based Distro\) ([^\s]*) \(([^\)]*)\)'
        ]):
            self.skipTest("Skipping, not not an OE based distro")

        index = 1
        bsp_type = board.match.group(index)
        index += 1
        if len(board.match.groups()) == 4:
            oe_version = board.match.group(index)
            index += 1
        else:
            oe_version = "Unknown"
        bsp_version = board.match.group(index)
        index += 1
        oe_version_string = board.match.group(index)
        index += 1

        board.expect(prompt)

        print("#########################################")
        print("bsp-type = %s" % bsp_type)
        print("oe-version = %s" % oe_version)
        print("bsp-version = %s" % bsp_version)
        print("oe-version-string = %s" % oe_version_string)
        print("#########################################")

        self.result_message="BSP = %s, BSP version = %s, OE version = %s, OE version string = %s" % \
                (bsp_type, bsp_version, oe_version, oe_version_string)
        self.logged['bsp-type'] = bsp_type
        self.logged['oe-version'] = oe_version
        self.logged['bsp-version'] = bsp_version
        self.logged['oe-version-string'] = oe_version_string
