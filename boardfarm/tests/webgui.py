# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

from boardfarm.devices import prompt
from boardfarm.tests import rootfs_boot


class Webserver_Running(rootfs_boot.RootFSBootTest):
    '''Router webserver is running.'''
    def runTest(self):
        board = self.dev.board

        board.sendline('\nps | grep -v grep | grep http')
        board.expect('uhttpd')
        board.expect(prompt)


class WebGUI_Access(rootfs_boot.RootFSBootTest):
    '''Router webpage available to LAN-device at http://192.168.1.1/.'''
    def runTest(self):
        lan = self.dev.lan

        ip = "192.168.1.1"
        url = 'http://%s/' % ip
        lan.sendline('\ncurl -v %s' % url)
        lan.expect('<html')
        lan.expect('<body')
        lan.expect('</body>')
        lan.expect('</html>')
        lan.expect(prompt)


class WebGUI_NoStackTrace(rootfs_boot.RootFSBootTest):
    '''Router webpage at cgi-bin/luci contains no stack traceback.'''
    def runTest(self):
        board = self.dev.board

        board.sendline('\ncurl -s http://127.0.0.1/cgi-bin/luci | head -15')
        board.expect('cgi-bin/luci')
        board.expect(prompt)
        assert 'traceback' not in board.before


class Webserver_Download(rootfs_boot.RootFSBootTest):
    '''Downloaded small file from router webserver in reasonable time.'''
    def runTest(self):
        board = self.dev.board
        lan = self.dev.lan

        ip = "192.168.1.1"
        board.sendline('\nhead -c 1000000 /dev/urandom > /www/deleteme.txt')
        board.expect('head ', timeout=5)
        board.expect(prompt)
        lan.sendline('\ncurl -m 25 http://%s/deleteme.txt > /dev/null' % ip)
        lan.expect('Total', timeout=5)
        lan.expect('100 ', timeout=10)
        lan.expect(prompt, timeout=10)
        board.sendline('\nrm -f /www/deleteme.txt')
        board.expect('deleteme.txt')
        board.expect(prompt)

    def recover(self):
        board = self.dev.board
        lan = self.dev.lan

        board.sendcontrol('c')
        lan.sendcontrol('c')
        board.sendline('rm -f /www/deleteme.txt')
        board.expect(prompt)
