# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import traceback
import warnings

from debtcollector import removals

import boardfarm.lib.booting
import boardfarm.exceptions
from boardfarm import lib

from . import bft_base_test

warnings.simplefilter("always", UserWarning)


class RootFSBootTest(bft_base_test.BftBaseTest):
    '''Flashed image and booted successfully.'''
    def boot(self, reflash=True):
        try:
            boardfarm.lib.booting.boot(self, self.config, self.env_helper,
                                       reflash, self.logged)
        except boardfarm.exceptions.NoTFTPServer:
            msg = 'No WAN Device or tftp_server defined, skipping flash.'
            lib.common.test_msg(msg)
            self.skipTest(msg)

    reflash = False
    reboot = False

    @lib.common.run_once
    def runTest(self):
        if self.__class__.__name__ == "RootFSBootTest":
            try:
                self.boot()
            except Exception as e:
                print("\n\nFailed to Boot")
                print(e)
                traceback.print_exc()
                raise boardfarm.exceptions.BootFail

    @removals.remove(removal_version="> 1.1.1", category=UserWarning)
    def recover(self):
        board = self.dev.board
        if self.__class__.__name__ == "RootFSBootTest":
            board.close()
            lib.common.test_msg("Unable to boot, skipping remaining tests...")
            return
        try:
            # let user interact with console if test failed
            try:
                board.sendline()
                board.sendline()
                if not self.config.batch:
                    board.interact()
            except:
                pass
            if self.reboot == True and self.reset_after_fail:
                self.boot(self.reflash)
            self.reboot = True
        except Exception as e:
            print("Unable to recover, %s" % e)
            self.assertEqual(1, 0, e)
