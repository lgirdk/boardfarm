# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import random
import re

import pexpect

from boardfarm.devices import prompt
from boardfarm.tests import rootfs_boot


class Nmap_LAN(rootfs_boot.RootFSBootTest):
    """Ran nmap port scanning tool on LAN interface."""

    def recover(self):
        lan = self.dev.lan
        lan.sendcontrol("c")

    def runTest(self):
        board = self.dev.board
        lan = self.dev.lan

        lan.sendline(
            f"nmap -sS -A -v -p 1-10000 {board.get_interface_ipaddr(board.lan_iface)}"
        )
        lan.expect("Starting Nmap")
        for _ in range(12):
            if 0 == lan.expect(["Nmap scan report", pexpect.TIMEOUT], timeout=100):
                break
            board.touch()
        lan.expect(prompt, timeout=60)
        open_ports = re.findall(r"(\d+)/tcp\s+open", lan.before)
        msg = "Found {} open TCP ports on LAN interface: {}.".format(
            len(open_ports),
            ", ".join(open_ports),
        )
        self.result_message = msg


class Nmap_WAN(rootfs_boot.RootFSBootTest):
    """Ran nmap port scanning tool on WAN interface."""

    def recover(self):
        wan = self.dev.wan

        wan.sendcontrol("c")

    def runTest(self):
        board = self.dev.board
        wan = self.dev.wan

        wan_ip_addr = board.get_interface_ipaddr(board.wan_iface)
        wan.sendline(f"\nnmap -sS -A -v {wan_ip_addr}")
        wan.expect("Starting Nmap", timeout=5)
        wan.expect(pexpect.TIMEOUT, timeout=60)
        board.touch()
        wan.expect(pexpect.TIMEOUT, timeout=60)
        board.touch()
        wan.expect(pexpect.TIMEOUT, timeout=60)
        board.touch()
        wan.expect("Nmap scan report", timeout=60)
        wan.expect(prompt, timeout=60)
        open_ports = re.findall(r"(\d+)/tcp\s+open", wan.before)
        msg = f"Found {len(open_ports)} open TCP ports on WAN interface."
        self.result_message = msg
        print(f"open ports = {open_ports}")
        if hasattr(board, "wan_open_ports"):
            print(f"allowing open ports {board.wan_open_ports}")
            open_ports = set(map(int, open_ports)) - set(board.wan_open_ports)
        assert len(open_ports) == 0


class UDP_Stress(rootfs_boot.RootFSBootTest):
    """Ran nmap through router, creating hundreds of UDP connections."""

    def runTest(self):
        lan = self.dev.lan

        start_port = random.randint(1, 11000)
        lan.sendline(
            f"\nnmap --min-rate 100 -sU -p {start_port}-{start_port + 200} 192.168.0.1"
        )
        lan.expect("Starting Nmap", timeout=5)
        lan.expect("Nmap scan report", timeout=30)
        lan.expect(prompt)

    def recover(self):
        lan = self.dev.lan

        lan.sendcontrol("c")
