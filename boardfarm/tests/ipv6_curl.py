"""Downloaded file through router using IPv6."""
# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

from boardfarm.devices import prompt
from boardfarm.tests import rootfs_boot


class IPv6_File_Download(rootfs_boot.RootFSBootTest):
    """Downloaded file through router using IPv6."""

    def runTest(self):
        """Performs the Download action via Curl."""
        wan = self.dev.wan
        lan = self.dev.lan

        # WAN Device: create large file in web directory
        fname = "/var/www/20mb.txt"
        wan.sendline(f'\n[ -e "{fname}" ] || head -c 20971520 /dev/urandom > {fname}')
        wan.expect("/var")
        wan.expect(prompt)
        # LAN Device: download the file
        lan.sendline("\ncurl -m 57 -g -6 http://[5aaa::6]/20mb.txt > /dev/null")
        lan.expect("Total", timeout=5)
        i = lan.expect(["couldn't connect", "20.0M  100 20.0M"], timeout=60)
        if i == 0:
            assert False
        lan.expect(prompt)
