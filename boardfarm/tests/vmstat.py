# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

from boardfarm.devices import prompt
from boardfarm.tests import rootfs_boot


class ProcVmstat(rootfs_boot.RootFSBootTest):
    '''Check /proc/vmstat stats.'''
    def runTest(self):
        board = self.dev.board

        self.logged.update(board.get_proc_vmstat())

        # Display extra info
        board.sendline('cat /proc/slabinfo /proc/buddyinfo /proc/meminfo')
        board.expect('cat /proc/')
        board.expect(prompt)
        board.sendline('cat /proc/vmallocinfo')
        board.expect('cat /proc/vmallocinfo')
        board.expect(prompt)
