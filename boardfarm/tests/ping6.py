# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

from boardfarm.tests import rootfs_boot
from boardfarm.devices import lan
from boardfarm.devices import prompt


class LanDevPing6Router(rootfs_boot.RootFSBootTest):
    '''Device on LAN can ping6 router.'''
    def runTest(self):
        lan.sendline('\nping6 -c 20 4aaa::1')
        lan.expect('PING ')
        lan.expect(' ([0-9]+) (packets )?received')
        n = int(lan.match.group(1))
        lan.expect(prompt)
        assert n > 0


class LanDevPing6WanDev(rootfs_boot.RootFSBootTest):
    '''Device on LAN can ping6 through router.'''
    def runTest(self):
        # Make Lan-device ping Wan-Device
        lan.sendline('\nping6 -c 20 5aaa::6')
        lan.expect('PING ')
        lan.expect(' ([0-9]+) (packets )?received')
        n = int(lan.match.group(1))
        lan.expect(prompt)
        assert n > 0
