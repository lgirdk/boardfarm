# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

from boardfarm.devices import prompt
from boardfarm.tests import rootfs_boot


class BridgedMode(rootfs_boot.RootFSBootTest):
    """Puts router in bridged mode (other tests may not work after running this)."""

    def runTest(self):
        board = self.dev.board
        lan = self.dev.lan

        board.sendline(
            f'uci set network.lan.ifname="{board.wan_iface} {board.lan_gmac_iface}"'
        )
        board.expect(prompt)
        board.sendline("uci set firewall.@defaults[0]=defaults")
        board.expect(prompt)
        board.sendline("uci set firewall.@defaults[0].input=ACCEPT")
        board.expect(prompt)
        board.sendline("uci set firewall.@defaults[0].output=ACCEPT")
        board.expect(prompt)
        board.sendline("uci set firewall.@defaults[0].syn_flood=1")
        board.expect(prompt)
        board.sendline("uci set firewall.@defaults[0].forward=ACCEPT")
        board.expect(prompt)
        board.sendline("uci set firewall.@zone[0]=zone")
        board.expect(prompt)
        board.sendline("uci set firewall.@zone[0].name=lan")
        board.expect(prompt)
        board.sendline("uci set firewall.@zone[0].network=lan")
        board.expect(prompt)
        board.sendline("uci set firewall.@zone[0].input=ACCEPT")
        board.expect(prompt)
        board.sendline("uci set firewall.@zone[0].output=ACCEPT")
        board.expect(prompt)
        board.sendline("uci set firewall.@zone[0].forward=ACCEPT")
        board.expect(prompt)
        board.sendline("uci set firewall.@zone[1]=zone")
        board.expect(prompt)
        board.sendline("uci set firewall.@zone[1].name=wan")
        board.expect(prompt)
        board.sendline("uci set firewall.@zone[1].network=wan")
        board.expect(prompt)
        board.sendline("uci set firewall.@zone[1].output=ACCEPT")
        board.expect(prompt)
        board.sendline("uci set firewall.@zone[1].mtu_fix=1")
        board.expect(prompt)
        board.sendline("uci set firewall.@zone[1].input=ACCEPT")
        board.expect(prompt)
        board.sendline("uci set firewall.@zone[1].forward=ACCEPT")
        board.expect(prompt)
        board.sendline("uci commit")
        board.expect(prompt)
        board.network_restart()
        board.firewall_restart()

        lan.sendline(f"ifconfig {lan.iface_dut} 192.168.0.2")
        lan.expect(prompt)
