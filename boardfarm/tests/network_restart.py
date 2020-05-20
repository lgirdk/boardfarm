# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import time

from boardfarm.tests import rootfs_boot


class RestartNetwork(rootfs_boot.RootFSBootTest):
    """Restarted router network."""
    def runTest(self):
        board = self.dev.board

        board.network_restart()
        print("\nWaiting 30s to give things time to fully start...\n")
        time.sleep(30)

    def recover(self):
        board = self.dev.board

        board.sendcontrol('c')
