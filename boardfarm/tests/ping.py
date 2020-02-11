# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

from boardfarm.tests import rootfs_boot
from boardfarm import lib

class RouterPingWanDev(rootfs_boot.RootFSBootTest):
    '''Router can ping device through WAN interface.'''
    def runTest(self):
        board = self.dev.board
        wan = self.dev.wan
        if not wan:
            msg = 'No WAN Device defined, skipping ping WAN test.'
            lib.common.test_msg(msg)
            self.skipTest(msg)
        board.sendline('\nping -c5 %s' % wan.gw)
        board.expect('5 (packets )?received', timeout=15)
        board.expect(board.prompt)
    def recover(self):
        self.dev.board.sendcontrol('c')

class RouterPingInternet(rootfs_boot.RootFSBootTest):
    '''Router can ping internet address by IP.'''
    def runTest(self):
        board = self.dev.board
        board.sendline('\nping -c2 8.8.8.8')
        board.expect('2 (packets )?received', timeout=15)
        board.expect(board.prompt)

class RouterPingInternetName(rootfs_boot.RootFSBootTest):
    '''Router can ping internet address by name.'''
    def runTest(self):
        board = self.dev.board
        board.sendline('\nping -c2 www.google.com')
        board.expect('2 (packets )?received', timeout=15)
        board.expect(board.prompt)

class LanDevPingRouter(rootfs_boot.RootFSBootTest):
    '''Device on LAN can ping router.'''
    def runTest(self):
        board = self.dev.board
        lan = self.dev.lan
        if not lan:
            msg = 'No LAN Device defined, skipping ping test from LAN.'
            lib.common.test_msg(msg)
            self.skipTest(msg)
        router_ip = board.get_interface_ipaddr(board.lan_iface)
        lan.sendline('\nping -i 0.2 -c 5 %s' % router_ip)
        lan.expect('PING ')
        lan.expect('5 (packets )?received', timeout=15)
        lan.expect(lan.prompt)

class LanDevPingWanDev(rootfs_boot.RootFSBootTest):
    '''Device on LAN can ping through router.'''
    def runTest(self):
        lan = self.dev.lan
        wan = self.dev.wan
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
        lan.expect(lan.prompt)
    def recover(self):
        self.dev.lan.sendcontrol('c')

class LanDevPingInternet(rootfs_boot.RootFSBootTest):
    '''Device on LAN can ping through router to internet.'''
    def runTest(self):
        lan = self.dev.lan
        if not lan:
            msg = 'No LAN Device defined, skipping ping test from LAN.'
            lib.common.test_msg(msg)
            self.skipTest(msg)
        lan.sendline('\nping -c2 8.8.8.8')
        lan.expect('2 (packets )?received', timeout=10)
        lan.expect(lan.prompt)
    def recover(self):
        self.dev.lan.sendcontrol('c')
