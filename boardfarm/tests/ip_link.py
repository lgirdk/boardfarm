# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import re

from boardfarm.devices import prompt
from boardfarm.tests import rootfs_boot


class InterfacesShow(rootfs_boot.RootFSBootTest):
    """Used "ip" or "ifconfig" to list interfaces."""

    def runTest(self):
        """Runtest implementation."""
        board = self.dev.board

        board.sendline("\nip link show")
        board.expect("ip link show")
        board.expect(prompt)
        if "ip: not found" not in board.before:
            up_interfaces = re.findall(
                r"\d: ([A-Za-z0-9-\.]+)[:@].*state UP ", board.before
            )
        else:
            board.sendline("ifconfig")
            board.expect(prompt)
            up_interfaces = re.findall(r"([A-Za-z0-9-\.]+)\s+Link", board.before)
        num_up = len(up_interfaces)
        if num_up >= 1:
            msg = "%s interfaces are UP: %s." % (
                num_up,
                ", ".join(sorted(up_interfaces)),
            )
        else:
            msg = "0 interfaces are UP."
        self.result_message = msg
        assert num_up >= 2
