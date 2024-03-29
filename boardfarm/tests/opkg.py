# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

from boardfarm.devices import prompt
from boardfarm.tests import rootfs_boot


class OpkgList(rootfs_boot.RootFSBootTest):
    """Opkg list shows installed packages."""

    def runTest(self):
        board = self.dev.board

        board.sendline("\nopkg list-installed | wc -l")
        board.expect("opkg list")
        board.expect(r"(\d+)\r\n")
        num_pkgs = int(board.match.group(1))
        board.expect(prompt)
        board.sendline("opkg list-installed")
        board.expect(prompt)
        self.result_message = f"{num_pkgs} OpenWrt packages are installed."
        self.logged["num_installed"] = num_pkgs


class CheckQosScripts(rootfs_boot.RootFSBootTest):
    """Package "qos-scripts" is not installed."""

    def runTest(self):
        board = self.dev.board

        board.sendline("\nopkg list | grep qos-scripts")
        try:
            board.expect("qos-scripts - ", timeout=4)
        except Exception as error:
            print(error)
            return  # pass if not installed
        assert False  # fail if installed


class OpkgUpdate(rootfs_boot.RootFSBootTest):
    """Opkg is able to update list of packages."""

    def runTest(self):
        board = self.dev.board

        board.sendline('\nopkg update && echo "All package lists updated"')
        board.expect("Updated list of available packages")
        board.expect("All package lists updated")
        board.expect(prompt)
