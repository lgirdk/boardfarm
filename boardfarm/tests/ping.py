# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import rootfs_boot
import lib
from devices import board, wan, lan, wlan, prompt

class RouterPingWanDev(rootfs_boot.RootFSBootTest):
    '''Router can ping device through WAN interface.'''
    def runTest(self):
        if not wan:
            msg = 'No WAN Device defined, skipping ping WAN test.'
            lib.common.test_msg(msg)
            self.skipTest(msg)
        board.sendline('\nping -c5 %s' % wan.gw)
        board.expect('5 (packets )?received', timeout=15)
        board.expect(prompt)
    def recover(self):
        board.sendcontrol('c')

class RouterPingInternet(rootfs_boot.RootFSBootTest):
    '''Router can ping internet address by IP.'''
    def runTest(self):
        board.sendline('\nping -c2 8.8.8.8')
        board.expect('2 (packets )?received', timeout=15)
        board.expect(prompt)

class RouterPingInternetName(rootfs_boot.RootFSBootTest):
    '''Router can ping internet address by name.'''
    def runTest(self):
        board.sendline('\nping -c2 www.google.com')
        board.expect('2 (packets )?received', timeout=15)
        board.expect(prompt)

class LanDevPingRouter(rootfs_boot.RootFSBootTest):
    '''Device on LAN can ping router.'''
    def runTest(self):
        if not lan:
            msg = 'No LAN Device defined, skipping ping test from LAN.'
            lib.common.test_msg(msg)
            self.skipTest(msg)
        router_ip = board.get_interface_ipaddr(board.lan_iface)
        lan.sendline('\nping -i 0.2 -c 5 %s' % router_ip)
        lan.expect('PING ')
        lan.expect('5 (packets )?received', timeout=15)
        lan.expect(prompt)

class LanDevPingWanDev(rootfs_boot.RootFSBootTest):
    '''Device on LAN can ping through router.'''
    def runTest(self):
        if not lan:
            msg = 'No LAN Device defined, skipping ping test from LAN.'
            lib.common.test_msg(msg)
            self.skipTest(msg)
        if not wan:
            msg = 'No WAN Device defined, skipping ping WAN test.'
            lib.common.test_msg(msg)
            self.skipTest(msg)
        lan.sendline('\nping -i 0.2 -c 5 %s' % wan.gw)
        lan.expect('PING ')
        lan.expect('5 (packets )?received', timeout=15)
        lan.expect(prompt)
    def recover(self):
        lan.sendcontrol('c')

class LanDevPingInternet(rootfs_boot.RootFSBootTest):
    '''Device on LAN can ping through router to internet.'''
    def runTest(self):
        if not lan:
            msg = 'No LAN Device defined, skipping ping test from LAN.'
            lib.common.test_msg(msg)
            self.skipTest(msg)
        lan.sendline('\nping -c2 8.8.8.8')
        lan.expect('2 (packets )?received', timeout=10)
        lan.expect(prompt)
    def recover(self):
        lan.sendcontrol('c')
