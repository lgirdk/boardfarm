#!/usr/bin/env python3
"""Linux based DSLite server using ISC AFTR."""
import os
import sys
import time

from boardfarm.devices.platform import debian


class AFTR(debian.DebianBox):
    """Linux based DSLite server using ISC AFTR.

    This class should is used to configure AFTR
    """

    model = name = "aftr"

    def __init__(self, *args, **kwargs):
        """To initialize the container details."""

    def configure_aftr(self, wan, board):
        ipv6_addr = wan.get_interface_ip6addr(wan.iface_dut)
        hosts_data = wan.check_output("cat /etc/dnsmasq.hosts")
        if "aftr.boardfarm.com" not in hosts_data:
            wan.sendline(f"echo {ipv6_addr} aftr.boardfarm.com >> /etc/dnsmasq.hosts")
            wan.expect(wan.prompt)
            wan.sendline("service dnsmasq stop")
            wan.expect(wan.prompt)
            wan.sendline("service dnsmasq start")
            wan.expect(wan.prompt)
            wan.sendline("sync")
            # disable / enable to update endpoint address
            board.dmcli.SPV("Device.DSLite.Enable", "false", "bool")
            time.sleep(20)
            board.dmcli.SPV("Device.DSLite.Enable", "true", "bool")


if __name__ == "__main__":
    # Example use
    try:
        ipaddr, port = sys.argv[1].split(":")
    except Exception:
        raise Exception("First argument should be in form of ipaddr:port")

    # for getting lib.common from tests working
    sys.path.append(os.getcwd() + "/../")
    sys.path.append(os.getcwd() + "/../tests")
