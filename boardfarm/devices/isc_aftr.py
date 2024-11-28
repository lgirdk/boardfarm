#!/usr/bin/env python3
"""Linux based DSLite server using ISC AFTR."""

import ipaddress
import os
import re
import sys
import time

from boardfarm.devices.platform import debian


class AFTR(debian.DebianBox):
    """Linux based DSLite server using ISC AFTR.

    This class is used to configure AFTR
    """

    model = name = "aftr"

    def __init__(self, *args, **kwargs):
        """To initialize the container details."""
        self.ipv6_ep = ipaddress.IPv6Interface(str(kwargs.get("ipv6_ep", "2001::1/48")))
        self.ipv6_acl_cfg = kwargs.get("ipv6_ACL", ["2001:dead:beef::/48"])

    def configure_aftr(self, wan, board):
        self.ipv6_acl = [
            str(self.ipv6_ep.network),
            str(wan.ipv6_interface.network),
        ] + self.ipv6_acl_cfg
        self.update_aftr_conf(wan, self.ipv6_acl)
        self.update_aftr_script(wan)
        hosts_data = wan.check_output("cat /etc/dnsmasq.hosts")

        # Assumption: if AFTR endpoint IP exists, it means AFTR entry exists
        if str(self.ipv6_ep.ip) not in hosts_data:
            hosts_data = [
                line.strip() for line in hosts_data.splitlines() if "aftr" not in line
            ]
            hosts_data.append(f"{self.ipv6_ep.ip}  aftr.boardfarm.com")
            wan.sendline("cat > /etc/dnsmasq.hosts << EOF")
            for line in hosts_data:
                wan.sendline(line)
            wan.sendline("EOF")
            wan.expect(wan.prompt)
            wan.check_output("service dnsmasq stop")
            wan.check_output("service dnsmasq start")
            wan.check_output("sync")
            # disable / enable to update endpoint address
            board.dmcli.SPV("Device.DSLite.Enable", "false", "bool")
            time.sleep(20)
            board.dmcli.SPV("Device.DSLite.Enable", "true", "bool")

    def update_aftr_conf(self, wan, ipv6_acl):
        ipv6_ep_addr = str(self.ipv6_ep.ip)
        wan.sendline("cat /root/aftr/aftr.conf")
        wan.expect(wan.prompt)
        res = wan.before
        res = res.split("\n")[1:]
        res = "\n".join(res)
        if ipv6_ep_addr not in res:
            updated_conf = res.replace(
                "address endpoint", f"address endpoint {ipv6_ep_addr}"
            )
            acl6 = "\n".join(map(lambda x: f"acl6 {x}", ipv6_acl))
            updated_aftr_conf = updated_conf + acl6
            updated_aftr_conf = re.sub(
                r"(\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]))", "", updated_aftr_conf
            )
            to_send = f"cat > /root/aftr/aftr.conf << EOF\n{updated_aftr_conf}\nEOF"
            wan.sendline(to_send)
            wan.expect(self.prompt)

    def update_aftr_script(self, wan):
        ipv6_ep_net = str(self.ipv6_ep.network)
        wan.sendline("cat /root/aftr/aftr-script")
        wan.expect(wan.prompt)
        res = wan.before
        res = res.split("\n")[1:]
        res = "\n".join(res)
        if ipv6_ep_net not in res:
            updated_script = res.replace(
                "ip -6 route add", f"ip -6 route add {ipv6_ep_net} dev tun0"
            )
            updated_script = re.sub(
                r"(\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]))", "", updated_script
            )
            to_send = f"cat > /root/aftr/aftr-script << EOF\n{updated_script}\nEOF"
            wan.sendline(to_send)
            wan.expect(self.prompt)
            wan.sendline("chmod +x /root/aftr/aftr-script")
            wan.expect(self.prompt)


if __name__ == "__main__":
    # Example use
    try:
        ipaddr, port = sys.argv[1].split(":")
    except Exception:
        raise Exception("First argument should be in form of ipaddr:port")

    # for getting lib.common from tests working
    sys.path.append(os.getcwd() + "/../")
    sys.path.append(os.getcwd() + "/../tests")
