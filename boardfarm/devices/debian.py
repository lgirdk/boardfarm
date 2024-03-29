#!/usr/bin/env python3
# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.
"""Device class for a debian linux."""

import atexit
import ipaddress
import re
import sys
import time
from collections import defaultdict

import pexpect
import six
from debtcollector import deprecate
from nested_lookup import nested_lookup
from termcolor import colored, cprint

from boardfarm.exceptions import PexpectErrorTimeout
from boardfarm.lib.bft_pexpect_helper import bft_pexpect_helper
from boardfarm.lib.common import retry_on_exception
from boardfarm.lib.dhcpoption import configure_option
from boardfarm.lib.network_helper import valid_ipv4
from boardfarm.lib.regexlib import ValidIpv4AddressRegex

from . import linux


class DebianBox(linux.LinuxDevice):
    """A linux machine running an ssh server."""

    model = "debian"
    prompt = ["root\\@.*:.*#", "/ # ", ".*:~ #"]
    static_route = None
    static_ip = False
    wan_dhcp = False
    wan_dhcpv6 = False
    wan_no_eth0 = False
    pkgs_installed = False
    install_pkgs_after_dhcp = False
    is_bridged = False
    shared_tftp_server = False
    wan_dhcp_server = True
    tftp_device = None
    tftp_dir = "/tftpboot"
    mgmt_dns = None
    sign_check = True
    iface_dut = "eth1"
    gw = None

    # TODO: does this need to be calculated?
    gwv6 = None
    ipv6_prefix = 64

    def __init__(self, *args, **kwargs):
        """Instance initialization."""
        deprecate(
            "Warning!",
            message="This DebianBox class is deprecated",
            category=UserWarning,
        )
        self.args = args
        self.kwargs = kwargs
        name = kwargs.pop("name", None)
        ipaddr = kwargs.pop("ipaddr", None)
        color = kwargs.pop("color", "black")
        username = kwargs.pop("username", "root")
        password = kwargs.pop("password", "bigfoot1")
        port = kwargs.pop("port", "22")
        output = kwargs.pop("output", sys.stdout)
        reboot = kwargs.pop("reboot", False)
        location = kwargs.pop("location", None)
        self.dev_array = kwargs.pop("dev_array", None)
        pre_cmd_host = kwargs.pop("pre_cmd_host", None)
        cmd = kwargs.pop("cmd", None)
        post_cmd_host = kwargs.pop("post_cmd_host", None)
        post_cmd = kwargs.pop("post_cmd", None)
        cleanup_cmd = kwargs.pop("cleanup_cmd", None)
        lan_network = ipaddress.IPv4Interface(
            str(kwargs.pop("lan_network", "192.168.1.0/24"))
        ).network
        lan_gateway = ipaddress.IPv4Interface(
            str(kwargs.pop("lan_gateway", "192.168.1.1/24"))
        ).ip
        self.shim = ""
        self.http_proxy = kwargs.pop("http_proxy", ipaddr + ":8080")

        if pre_cmd_host is not None:
            sys.stdout.write("\tRunning pre_cmd_host.... ")
            sys.stdout.flush()
            phc = bft_pexpect_helper.spawn(
                command="bash", args=["-c", pre_cmd_host], env=self.dev.env
            )
            phc.expect(pexpect.EOF, timeout=120)
            print("\tpre_cmd_host done")

        self.legacy_add = False
        # introducing a hack till json schema does not get updated
        if not self.dev_array:
            self.legacy_add = True
            arr_names = {"lan": "lan_clients", "wan": "wan_clients"}
            for k, v in arr_names.items():
                if k in name:
                    self.dev_array = v

        if ipaddr is not None:
            bft_pexpect_helper.spawn.__init__(
                self,
                command="ssh",
                args=[
                    f"{username}@{ipaddr}",
                    "-p",
                    port,
                    "-o",
                    "StrictHostKeyChecking=no",
                    "-o",
                    "UserKnownHostsFile=/dev/null",
                    "-o",
                    "ServerAliveInterval=60",
                    "-o",
                    "ServerAliveCountMax=5",
                ],
            )

            self.ipaddr = ipaddr

        if cleanup_cmd is not None:
            self.cleanup_cmd = cleanup_cmd
            atexit.register(self.run_cleanup_cmd)

        if cmd is not None:
            sys.stdout.write("\tRunning cmd.... ")
            sys.stdout.flush()
            bft_pexpect_helper.spawn.__init__(
                self, command="bash", args=["-c", cmd], env=self.dev.env
            )
            self.ipaddr = None
            print("\tcmd done")

        self.name = name
        self.color = color
        self.output = output
        self.username = username
        if username != "root":
            self.prompt.append(f"{username}\\@.*:.*$")
        self.password = password
        self.port = port
        self.location = location
        self.lan_network = lan_network
        self.lan_gateway = lan_gateway
        self.tftp_device = self
        self.dante = False

        self.check_connection(username, name, password)

        # attempts to fix the cli columns size
        self.set_cli_size(200)

        # we need to pick a non-conflicting private network here
        # also we want it to be consistent and not random for a particular
        # board
        if self.gw is None:
            if (lan_gateway - lan_network.num_addresses).is_private:
                self.gw = lan_gateway - lan_network.num_addresses
            else:
                self.gw = lan_gateway + lan_network.num_addresses

        self.gw_ng = ipaddress.IPv4Interface(
            str(str(self.gw) + "/" + str(lan_network.prefixlen))
        )
        self.nw = self.gw_ng.network
        self.gw_prefixlen = self.nw.prefixlen

        # override above values if set in wan options
        if "options" in kwargs:
            options = [x.strip() for x in kwargs["options"].split(",")]
            for opt in options:
                if opt.startswith("wan-static-ip:"):
                    value = str(opt.replace("wan-static-ip:", ""))
                    if "/" not in value:
                        value = value + ("/24")
                    self.gw_ng = ipaddress.IPv4Interface(value)
                    self.nw = self.gw_ng.network
                    self.gw_prefixlen = self.nw._prefixlen
                    self.gw = self.gw_ng.ip
                    self.static_ip = True
                if opt.startswith("wan-static-ipv6:"):
                    ipv6_address = str(opt.replace("wan-static-ipv6:", ""))
                    if "/" not in opt:
                        ipv6_address += f"/{six.text_type(str(self.ipv6_prefix))}"
                    self.ipv6_interface = ipaddress.IPv6Interface(ipv6_address)
                    self.ipv6_prefix = self.ipv6_interface._prefixlen
                    self.gwv6 = self.ipv6_interface.ip
                if opt.startswith("wan-static-route:"):
                    self.static_route = opt.replace("wan-static-route:", "").replace(
                        "-", " via "
                    )
                # TODO: remove wan-static-route at some point above
                if opt.startswith("static-route:"):
                    self.static_route = opt.replace("static-route:", "").replace(
                        "-", " via "
                    )
                if opt == "wan-dhcp-client":
                    self.wan_dhcp = True
                if opt == "wan-no-eth0":
                    self.wan_no_eth0 = True
                if opt == "wan-no-dhcp-server":
                    self.wan_dhcp_server = False
                if opt == "wan-dhcp-client-v6":
                    self.wan_dhcpv6 = True
                if opt.startswith("mgmt-dns:"):
                    value = str(opt.replace("mgmt-dns:", ""))
                    self.mgmt_dns = ipaddress.IPv4Interface(value).ip
                else:
                    self.mgmt_dns = "8.8.8.8"
                if opt == "dante":
                    self.dante = True

        if ipaddr is None:
            self.sendline("hostname")
            self.expect("hostname")
            self.expect(self.prompt)
            ipaddr = self.ipaddr = self.before.strip()

        self.print_connected_console_msg(ipaddr, port, color, name)

        if post_cmd_host is not None:
            sys.stdout.write("\tRunning post_cmd_host.... ")
            sys.stdout.flush()
            phc = bft_pexpect_helper.spawn(
                command="bash", args=["-c", post_cmd_host], env=self.dev.env
            )
            i = phc.expect([pexpect.EOF, pexpect.TIMEOUT, "password"])
            if i > 0:
                print("\tpost_cmd_host did not complete, it likely failed\n")
            else:
                print("\tpost_cmd_host done")

        if post_cmd is not None:
            sys.stdout.write("\tRunning post_cmd.... ")
            sys.stdout.flush()
            env_prefix = ""
            for k, v in self.dev.env.items():
                env_prefix += f"export {k}={v}; "

            self.sendline(env_prefix + post_cmd)
            self.expect(self.prompt)
            print("\tpost_cmd done")

        if reboot:
            self.reset()

        self.logfile_read = output

    def check_connection(self, username, name, password):
        """To check ssh connection in debian box.

        :param username: cli-login username
        :type username: string
        :param name: name of the debian device
        :type name: string
        :param password: cli-login password
        :type password: string
        :raises: Unable to connect to device exception
        """
        try:
            i = self.expect(
                ["yes/no", "assword:", "Last login", username + ".*'s password:"]
                + self.prompt,
                timeout=30,
            )
        except PexpectErrorTimeout:
            raise Exception(f"Unable to connect to {name}.")
        except pexpect.EOF:
            if hasattr(self, "before"):
                print(self.before)
                raise Exception(f"Unable to connect to {name}.")
        if i == 0:
            self.sendline("yes")
            i = self.expect(["Last login", "assword:"])
        if i == 1 or i == 3:
            self.sendline(password)
        else:
            pass
        # if we did initially get a prompt wait for one here
        if i < 4:
            self.expect(self.prompt)

    def print_connected_console_msg(self, ipaddr, port, color, name):
        """To print console message if bft is connected to device.

        :param ipaddr: iface ipaddress of the device
        :type ipaddr: string
        :param port: cli-login port of the debian device
        :type port: string
        :param color: color
        :type color: string
        :param name: name of the debian device
        :type name: string
        """
        cmsg = f"{ipaddr} "
        if self.port != 22:
            cmsg += f"{port} port "
        cmsg += "device console = "
        cmsg += colored(f"{color} ({name})", color)
        cprint(cmsg, None, attrs=["bold"])

    def get_default_gateway(self, interface):
        """Get the default gateway from ip route output."""
        self.sendline(f"ip route | grep {interface!s}")
        self.expect(self.prompt)

        match = re.search(f"default via (.*) dev {interface!s}.*\r\n", self.before)
        if match:
            return match.group(1)
        else:
            return None

    def run_cleanup_cmd(self):
        """To clear the buffer."""
        sys.stdout.write(f"Running cleanup_cmd on {self.name}...")
        sys.stdout.flush()
        cc = bft_pexpect_helper.spawn(
            command="bash", args=["-c", self.cleanup_cmd], env=self.dev.env
        )
        cc.expect(pexpect.EOF, timeout=120)
        print("cleanup_cmd done.")

    def reset(self):
        """Reset the debian linux device."""
        self.sendline("reboot")
        self.expect(["going down", "disconnected"])
        try:
            self.expect(self.prompt, timeout=10)
        except Exception:
            pass
        time.sleep(15)  # Wait for the network to go down.
        for i in range(0, 20):
            try:
                bft_pexpect_helper.spawn("ping -w 1 -c 1 " + self.name).expect(
                    "64 bytes", timeout=1
                )
            except Exception:
                print(self.name + f" not up yet, after {i + 15} seconds.")
            else:
                print(
                    "%s is back after %s seconds, waiting for network daemons to spawn."
                    % (self.name, i + 14)
                )
                time.sleep(15)
                break
        self.__init__(
            self.name,
            self.color,
            self.output,
            self.username,
            self.password,
            self.port,
            reboot=False,
        )

    def install_pkgs(self):
        """Install required basic packages in the device."""
        if self.pkgs_installed:
            return

        self.sendline(
            'echo "Acquire::ForceIPv4 "true";" > /etc/apt/apt.conf.d/99force-ipv4'
        )
        self.expect(self.prompt)

        if (
            not self.wan_no_eth0
            and not self.wan_dhcp
            and not self.install_pkgs_after_dhcp
            and not getattr(self, "standalone_provisioner", False)
        ):
            self.sendline(f"ifconfig {self.iface_dut} down")
            self.expect(self.prompt)

        pkgs = "isc-dhcp-server xinetd tinyproxy curl apache2-utils nmap psmisc vim-common tftpd-hpa pppoe isc-dhcp-server procps iptables lighttpd psmisc dnsmasq xxd dante-server"

        def _install_pkgs():
            shim_prefix = self.get_shim_prefix()
            self.sendline(
                '%sapt-get -q update && %sapt-get -o DPkg::Options::="--force-confnew" -qy install %s'
                % (shim_prefix, shim_prefix, pkgs)
            )
            if 0 == self.expect(["Reading package", pexpect.TIMEOUT], timeout=60):
                self.expect(self.prompt, timeout=300)
            else:
                print("Failed to download packages, things might not work")
                self.sendcontrol("c")
                self.expect(self.prompt)

            self.pkgs_installed = True

        # TODO: use netns for all this?
        undo_default_route = None
        self.sendline("ping -4 -c1 deb.debian.org")
        i = self.expect(
            ["ping: unknown host", "connect: Network is unreachable", pexpect.TIMEOUT]
            + self.prompt,
            timeout=10,
        )
        if 0 == i:
            # TODO: don't reference eth0, but the uplink iface
            self.sendline(
                "echo SYNC; ip route list | grep 'via.*dev eth0' | awk '{print $3}'"
            )
            self.expect_exact("SYNC\r\n")
            if 0 == self.expect(
                [r"(\d{1,3}.\d{1,3}.\d{1,3}.\d{1,3})\r\n"] + self.prompt, timeout=5
            ):
                possible_default_gw = self.match.group(1)
                self.sendline(f"ip route add default via {possible_default_gw}")
                self.expect(self.prompt)
                self.sendline("ping -c1 deb.debian.org")
                self.expect(self.prompt)
                undo_default_route = possible_default_gw
                shim_prefix = self.get_shim_prefix()
                self.sendline(
                    '%sapt-get -q update && %sapt-get -o DPkg::Options::="--force-confnew" -qy install %s'
                    % (shim_prefix, shim_prefix, pkgs)
                )
                if 0 == self.expect(["Reading package", pexpect.TIMEOUT], timeout=60):
                    self.expect(self.prompt, timeout=300)
                else:
                    print("Failed to download packages, things might not work")
                    self.sendcontrol("c")
                    self.expect(self.prompt)
        elif 1 == i:
            if self.install_pkgs_after_dhcp:
                _install_pkgs()
            else:
                self.install_pkgs_after_dhcp = True
            return
        elif 2 == i:
            self.sendcontrol("c")
            self.expect(self.prompt)
        else:
            _install_pkgs()

        if undo_default_route is not None:
            self.sendline(f"ip route del default via {undo_default_route}")
            self.expect(self.prompt)

    def turn_on_pppoe(self):
        """Turn on PPPoE server in the linux device."""
        self.sendline("cat > /etc/ppp/pppoe-server-options << EOF")
        self.sendline("noauth")
        self.sendline("ms-dns 8.8.8.8")
        self.sendline("ms-dns 8.8.4.4")
        self.sendline("EOF")
        self.expect(self.prompt)
        self.sendline(
            f"pppoe-server -k -I {self.iface_dut} -L 192.168.2.1 -R 192.168.2.10 -N 4"
        )
        self.expect(self.prompt)

    def turn_off_pppoe(self):
        """Turn off PPPoE server in the linux device."""
        self.sendline("\nkillall pppoe-server pppoe pppd")
        self.expect("pppd")
        self.expect(self.prompt)

    def start_tftp_server(self):
        """Turn on tftp server in the linux device."""
        # we can call this first, before configure so we need to do this here
        # as well
        self.install_pkgs()
        # the entire reason to start tftp is to copy files to devices
        # which we do via ssh so let's start that as well
        self.start_sshd_server()

        try:
            eth1_addr = self.get_interface_ipaddr(self.iface_dut)
        except Exception:
            eth1_addr = None

        # set WAN ip address, for now this will always be this address for the device side
        # TODO: fix gateway for non-WAN tftp_server
        if self.gw != eth1_addr:
            self.sendline(f"ifconfig {self.iface_dut} {self.gw_ng}")
            self.expect(self.prompt)
        self.sendline(f"ifconfig {self.iface_dut} up")
        self.expect(self.prompt)

        # configure tftp server
        self.sendline("/etc/init.d/tftpd-hpa stop")
        self.expect("Stopping")
        self.expect(self.prompt)
        if not self.shared_tftp_server:
            self.sendline("rm -rf " + self.tftp_dir)
            self.expect(self.prompt)
            self.sendline("rm -rf /srv/tftp")
            self.expect(self.prompt)
        self.sendline("mkdir -p /srv/tftp")
        self.expect(self.prompt)
        self.sendline("ln -sf /srv/tftp/ " + self.tftp_dir)
        self.expect(self.prompt)
        self.sendline("mkdir -p " + self.tftp_dir + "/tmp")
        self.expect(self.prompt)
        self.sendline("chmod a+w " + self.tftp_dir + "/tmp")
        self.expect(self.prompt)
        self.sendline("mkdir -p " + self.tftp_dir + "/crashdump")
        self.expect(self.prompt)
        self.sendline("chmod a+w " + self.tftp_dir + "/crashdump")
        self.expect(self.prompt)
        self.sendline("sed /TFTP_ADDRESS/d -i /etc/default/tftpd-hpa")
        self.expect(self.prompt)
        self.sendline('echo TFTP_ADDRESS=\\":69\\" >> /etc/default/tftpd-hpa')
        self.expect(self.prompt)
        self.sendline("sed /TFTP_DIRECTORY/d -i /etc/default/tftpd-hpa")
        self.expect(self.prompt)
        self.sendline('echo TFTP_DIRECTORY=\\"/srv/tftp\\" >> /etc/default/tftpd-hpa')
        self.expect(self.prompt)
        self.restart_tftp_server()

    # mode can be "ipv4" or "ipv6"
    def restart_tftp_server(self, mode=None):
        """Restart tftp server in the linux device."""
        self.sendline("sed /TFTP_OPTIONS/d -i /etc/default/tftpd-hpa")
        self.expect(self.prompt)
        self.sendline(
            'echo TFTP_OPTIONS=\\"%s--secure --create\\" >> /etc/default/tftpd-hpa'
            % ("--%s " % mode if mode else "")
        )
        self.expect(self.prompt)
        self.sendline("\n/etc/init.d/tftpd-hpa restart")
        self.expect("Restarting")
        self.expect(self.prompt)
        self.sendline("/etc/init.d/tftpd-hpa status")
        self.expect("in.tftpd is running")
        self.expect(self.prompt)

    def start_sshd_server(self):
        """Turn on sshd server in the linux device."""
        self.sendline("/etc/init.d/rsyslog start")
        self.expect(self.prompt)
        self.sendline("/etc/init.d/ssh start")
        self.expect(self.prompt)
        self.sendline(
            'sed "s/.*PermitRootLogin.*/PermitRootLogin yes/g" -i /etc/ssh/sshd_config'
        )
        self.expect(self.prompt)
        self.sendline("/etc/init.d/ssh reload")
        self.expect(self.prompt)

    def configure(self, kind, config=None):
        """Configuring the device as WAN or LAN."""
        # TODO: wan needs to enable on more so we can route out?
        if config is None:
            config = []

        self.enable_ipv6(self.iface_dut)
        self.install_pkgs()
        self.start_sshd_server()
        if kind == "wan_device":
            self.setup_as_wan_gateway(config=config)
        elif kind == "lan_device":
            self.setup_as_lan_device()

        # this needs to be more fine-grained controlled.
        # also it needs to have args handling.
        if hasattr(self, "profile"):
            boot_list = nested_lookup("on_boot", self.profile.get(self.name, {}))
            for profile_boot in boot_list:
                profile_boot()

        if self.static_route is not None:
            # TODO: add some ppint handle this more robustly
            self.send(f"ip route del {self.static_route.split(' via ')[0]}; ")
            self.sendline(f"ip route add {self.static_route}")
            self.expect(self.prompt)

    def setup_dhcp_server(self):
        """Configure dhcp server in the linux device."""
        if not self.wan_dhcp_server:
            return

        # configure DHCP server
        self.sendline("/etc/init.d/isc-dhcp-server stop")
        self.expect(self.prompt)
        self.sendline(
            'sed s/INTERFACES=.*/INTERFACES=\\"%s\\"/g -i /etc/default/isc-dhcp-server'
            % self.iface_dut
        )
        self.expect(self.prompt)
        self.sendline(
            'sed s/INTERFACESv4=.*/INTERFACESv4=\\"%s\\"/g -i /etc/default/isc-dhcp-server'
            % self.iface_dut
        )
        self.expect(self.prompt)
        self.sendline(
            'sed s/INTERFACESv6=.*/INTERFACESv6=\\"%s\\"/g -i /etc/default/isc-dhcp-server'
            % self.iface_dut
        )
        self.expect(self.prompt)
        self.sendline("cat > /etc/dhcp/dhcpd.conf << EOF")
        self.sendline("ddns-update-style none;")
        self.sendline('option domain-name "bigfoot-test";')
        self.sendline(f"option domain-name-servers {self.gw};")
        self.sendline("default-lease-time 600;")
        self.sendline("max-lease-time 7200;")
        # use the same netmask as the lan device
        self.sendline(f"subnet {self.nw.network_address} netmask {self.nw.netmask} {{")
        self.sendline(
            "          range %s %s;"
            % (self.nw.network_address + 10, self.nw.network_address + 100)
        )
        self.sendline(f"          option routers {self.gw};")
        self.sendline("}")
        self.sendline("EOF")
        self.expect(self.prompt)
        self.sendline("/etc/init.d/isc-dhcp-server start")
        self.expect(
            ["Starting ISC DHCP(v4)? server.*dhcpd.", "Starting isc-dhcp-server.*"]
        )
        self.expect(self.prompt)

    def setup_dnsmasq(self, config=None):
        """Configure DNS Masq in the linux device."""
        self.sendline("cat > /etc/dnsmasq.conf << EOF")
        self.sendline("server=8.8.4.4")
        self.sendline("listen-address=127.0.0.1")
        self.sendline(f"listen-address={self.gw}")
        if self.gwv6 is not None:
            self.sendline(f"listen-address={self.gwv6}")
        self.sendline(
            "addn-hosts=/etc/dnsmasq.hosts"
        )  # all additional hosts will be added to dnsmasq.hosts
        self.check_output("EOF")
        self.add_hosts(config=config)
        self.restart_dns_server()

    def restart_dns_server(self):
        """Restart dns service in the linux device."""
        self.sendline("/etc/init.d/dnsmasq restart")
        self.expect(self.prompt)
        self.sendline('echo "nameserver 127.0.0.1" > /etc/resolv.conf')
        self.expect(self.prompt)

    def add_hosts(self, addn_host=None, config=None):
        """Add extra hosts(dict) to dnsmasq.hosts if dns has to run in wan container."""
        # this is a hack, the add_host should have been called from RootFs
        if addn_host is None:
            addn_host = {}

        self.hosts = getattr(self, "hosts", defaultdict(list))
        restart = False

        def _update_host_dict(host_data):
            for host, ip in host_data.items():
                if type(ip) is list:
                    self.hosts[host] += ip
                else:
                    self.hosts[host].append(ip)

        if addn_host:
            _update_host_dict(addn_host)
            restart = True
        else:
            if hasattr(self, "profile"):
                host_dicts = nested_lookup("hosts", self.profile.get(self.name, {}))
                for i in host_dicts:
                    _update_host_dict(i)
            if config is not None and hasattr(config, "board"):
                for device in config.board["devices"]:
                    # TODO: this should be different...
                    if "lan" in device["name"]:
                        continue
                    d = getattr(config, device["name"])
                    domain_name = device["name"] + ".boardfarm.com"
                    final = None
                    if "wan-static-ip:" in str(device):
                        final = str(
                            re.search(
                                "wan-static-ip:" + "(" + ValidIpv4AddressRegex + ")",
                                device["options"],
                            ).group(1)
                        )
                    elif "ipaddr" in device:
                        final = str(device["ipaddr"])
                    elif hasattr(d, "ipaddr"):
                        final = str(d.ipaddr)

                    if final == "localhost":
                        if hasattr(d, "gw"):
                            final = str(d.gw)
                        elif hasattr(d, "iface_dut"):
                            final = d.get_interface_ipaddr(d.iface_dut)
                        else:
                            final = None
                    if final is not None:
                        self.hosts[domain_name].append(final)

                    # for IPv6 part:
                    # each device should setup it's own v6 host
                    # TODO: need to change iteration of device via device manager.
                    if getattr(d, "gwv6", None):
                        self.hosts[domain_name].append(str(d.gwv6))
        if self.hosts:
            self.sendline("cat > /etc/dnsmasq.hosts << EOF")
            for host, ips in self.hosts.items():
                for ip in set(ips):
                    self.sendline(ip + " " + host)
            self.check_output("EOF")
        if restart:
            self.restart_dns_server()

    def remove_hosts(self):
        """Remove dnsmasq.hosts and restart the service."""
        # TODO: we should probably be specific here whether we want to remove
        # everything or just few hosts.
        self.sendline("rm  /etc/dnsmasq.hosts")
        self.expect(self.prompt)
        self.sendline("/etc/init.d/dnsmasq restart")
        self.expect(self.prompt)

    def setup_as_wan_gateway(self, config=None):
        """Set the device as WAN Gateway."""
        self.setup_dnsmasq(config)

        self.sendline("killall iperf ab hping3")
        self.expect(self.prompt)

        # temporary hack
        if type(self).__name__ != "DebianISCProvisioner":
            self.sendline("killall dhcpd dhclient")
            self.expect(self.prompt)

        # potential cleanup so this wan device works
        self.sendline("iptables -t nat -X")
        self.expect(self.prompt)
        self.sendline("iptables -t nat -F")
        self.expect(self.prompt)

        # set WAN ip address
        if self.wan_dhcp:
            self.sendline("/etc/init.d/isc-dhcp-server stop")
            self.expect(self.prompt)
            self.sendline(f"dhclient -r {self.iface_dut}; dhclient {self.iface_dut}")
            self.expect(self.prompt)
            self.gw = self.get_interface_ipaddr(self.iface_dut)
        else:
            if not self.wan_no_eth0:
                self.sendline(f"ifconfig {self.iface_dut} {self.gw_ng}")
                self.expect(self.prompt)
                self.sendline(f"ifconfig {self.iface_dut} up")
                self.expect(self.prompt)
            if self.wan_dhcp_server:
                self.setup_dhcp_server()

        if self.wan_dhcpv6:
            # we are bypass this for now (see http://patchwork.ozlabs.org/patch/117949/)
            self.sendline(f"sysctl -w net.ipv6.conf.{self.iface_dut}.accept_dad=0")
            self.expect(self.prompt)
            try:
                self.gwv6 = self.get_interface_ip6addr(self.iface_dut)
            except Exception:
                self.sendline(f"dhclient -6 -i -r {self.iface_dut}")
                self.expect(self.prompt)
                self.sendline(f"dhclient -6 -i -v {self.iface_dut}")
                self.expect(self.prompt)
                self.sendline("ip -6 addr")
                self.expect(self.prompt)
                self.gwv6 = self.get_interface_ip6addr(self.iface_dut)
        elif self.gwv6 is not None:
            # we are bypass this for now (see http://patchwork.ozlabs.org/patch/117949/)
            self.sendline(f"sysctl -w net.ipv6.conf.{self.iface_dut}.accept_dad=0")
            self.expect(self.prompt)
            self.sendline(
                f"ip -6 addr add {self.gwv6}/{self.ipv6_prefix} dev {self.iface_dut}"
            )
            self.expect(self.prompt)

        # configure routing
        self.sendline("sysctl net.ipv4.ip_forward=1")
        self.expect(self.prompt)
        self.sendline("sysctl net.ipv6.conf.all.forwarding=0")
        self.expect(self.prompt)

        if self.wan_no_eth0 or self.wan_dhcp:
            wan_uplink_iface = self.iface_dut
        else:
            wan_uplink_iface = "eth0"

        wan_ip_uplink = self.get_interface_ipaddr(wan_uplink_iface)
        self.sendline(
            "iptables -t nat -A POSTROUTING -o %s -j SNAT --to-source %s"
            % (wan_uplink_iface, wan_ip_uplink)
        )
        self.expect(self.prompt)

        self.sendline("echo 0 > /proc/sys/net/ipv4/tcp_timestamps")
        self.expect(self.prompt)
        self.sendline("echo 0 > /proc/sys/net/ipv4/tcp_sack")
        self.expect(self.prompt)

        self.sendline(f"ifconfig {self.iface_dut}")
        self.expect(self.prompt)

        self.turn_off_pppoe()

        if self.dante:
            self.start_webproxy(self.dante)

    def setup_as_lan_device(self):
        """Set the device as a LAN Device."""
        # potential cleanup so this wan device works
        self.sendline("killall iperf ab hping3")
        self.expect(self.prompt)
        self.sendline("\niptables -t nat -X")
        self.expect("iptables -t")
        self.expect(self.prompt)
        self.sendline("sysctl net.ipv4.ip_forward=1")
        self.expect(self.prompt)
        self.sendline("iptables -t nat -F; iptables -t nat -X")
        self.expect(self.prompt)
        self.sendline("iptables -F; iptables -X")
        self.expect(self.prompt)
        self.sendline(
            "iptables -t nat -A PREROUTING -p tcp --dport 222 -j DNAT --to-destination %s:22"
            % self.lan_gateway
        )
        self.expect(self.prompt)
        self.sendline(
            "iptables -t nat -A POSTROUTING -o %s -p tcp --dport 22 -j MASQUERADE"
            % self.iface_dut
        )
        self.expect(self.prompt)
        self.sendline("echo 0 > /proc/sys/net/ipv4/tcp_timestamps")
        self.expect(self.prompt)
        self.sendline("echo 0 > /proc/sys/net/ipv4/tcp_sack")
        self.expect(self.prompt)
        self.sendline(f"pkill --signal 9 -f dhclient.*{self.iface_dut}")
        self.expect(self.prompt)
        self.sendline(f"{self.get_shim_prefix()}apt install -qy ndisc6")
        if 0 == self.expect(["Reading package", pexpect.TIMEOUT], timeout=60):
            self.expect(self.prompt, timeout=60)
        else:
            print("Failed to download packages, things might not work")
            self.sendcontrol("c")
            self.expect(self.prompt)

    def start_lan_client(self, wan_gw=None, ipv4_only=False):
        """Start lan client and get ip addresses received from DUT."""
        ipv4, ipv6 = None, None
        self.sendline(
            f"ip link set down {self.iface_dut} && ip link set up {self.iface_dut}"
        )
        self.expect(self.prompt)

        self.sendline(f"dhclient -4 -r {self.iface_dut}")
        self.expect(self.prompt)
        self.sendline(f"dhclient -6 -r -i {self.iface_dut}")
        self.expect(self.prompt, timeout=60)

        self.sendline("kill $(</run/dhclient6.pid)")
        self.expect(self.prompt)

        self.sendline("kill $(</run/dhclient.pid)")
        self.expect(self.prompt)

        self.sendline("ps aux")
        if self.expect(["dhclient"] + self.prompt) == 0:
            print("WARN: dhclient still running, something started rogue client!")
            self.sendline(f"pkill --signal 9 -f dhclient.*{self.iface_dut}")
            self.expect(self.prompt)

        if not ipv4_only:

            self.disable_ipv6(self.iface_dut)
            self.enable_ipv6(self.iface_dut)
            self.sendline(f"sysctl -w net.ipv6.conf.{self.iface_dut}.accept_dad=0")

            # check if board is providing an RA, if yes use that detail to perform DHCPv6
            # default method used will be statefull DHCPv6
            output = self.check_output(f"rdisc6 -1 {self.iface_dut}", timeout=60)
            M_bit, O_bit = True, True
            if "Prefix" in output:
                M_bit, O_bit = map(
                    lambda x: "Yes" in x, re.findall(r"Stateful.*\W", output)
                )

            # Condition for Stateless DHCPv6, this should update DNS details via DHCP and IP via SLAAC
            if not M_bit and O_bit:
                self.sendline(f"dhclient -S -v {self.iface_dut}")
                if 0 == self.expect([pexpect.TIMEOUT] + self.prompt, timeout=15):
                    self.sendcontrol("c")
                    self.expect(self.prompt)

            # Condition for Statefull DHCPv6, DNS and IP details provided using DHCPv6
            elif M_bit and O_bit:
                self.sendline(f"dhclient -6 -i -v {self.iface_dut}")
                if 0 == self.expect([pexpect.TIMEOUT] + self.prompt, timeout=15):
                    self.sendcontrol("c")
                    self.expect(self.prompt)

            # if env is dual, code should always return an IPv6 address
            # need to actually throw an error, for IPv6 not receiving an IP
            try:
                ipv6 = self.get_interface_ip6addr(self.iface_dut)
            except Exception:
                pass

        self.disable_ipv6("eth0")

        self.sendline(f"\nifconfig {self.iface_dut} 0.0.0.0")
        self.expect(self.prompt)
        self.sendline("rm /var/lib/dhcp/dhclient.leases")
        self.expect(self.prompt)
        self.sendline(
            "sed -e 's/mv -f $new_resolv_conf $resolv_conf/cat $new_resolv_conf > $resolv_conf/g' -i /sbin/dhclient-script"
        )
        self.expect(self.prompt)
        if self.mgmt_dns is not None:
            self.sendline(
                "sed '/append domain-name-servers %s/d' -i /etc/dhcp/dhclient.conf"
                % str(self.mgmt_dns)
            )
            self.expect(self.prompt)
            self.sendline(
                'echo "append domain-name-servers %s;" >> /etc/dhcp/dhclient.conf'
                % str(self.mgmt_dns)
            )
            self.expect(self.prompt)

        self.configure_dhclient((["60", True], ["61", True]))

        # TODO: don't hard code eth0
        self.sendline("ip route del default dev eth0")
        self.expect(self.prompt)
        for _ in range(3):
            try:
                self.sendline(f"dhclient -4 -v {self.iface_dut}")
                if 0 == self.expect(["DHCPOFFER"] + self.prompt, timeout=30):
                    self.expect(self.prompt)
                    break
                else:
                    retry_on_exception(
                        valid_ipv4,
                        (self.get_interface_ipaddr(self.iface_dut),),
                        retries=5,
                    )
                    break
            except Exception:
                self.sendline("killall dhclient")
                self.sendcontrol("c")
        else:
            raise Exception("Error: Device on LAN couldn't obtain address via DHCP.")

        self.sendline("cat /etc/resolv.conf")
        self.expect(self.prompt)
        self.sendline(f"ip addr show dev {self.iface_dut}")
        self.expect(self.prompt)
        self.sendline("ip route")
        # TODO: we should verify this so other way, because the they could be the same subnets
        # in theory
        i = self.expect(
            [
                f"default via {self.lan_gateway} dev {self.iface_dut}",
                pexpect.TIMEOUT,
            ],
            timeout=5,
        )
        if i == 1:
            # bridged mode
            self.is_bridged = True
            # update gw
            self.sendline("ip route list 0/0 | awk '{print $3}'")
            self.expect_exact("ip route list 0/0 | awk '{print $3}'")
            self.expect(self.prompt)
            self.lan_gateway = ipaddress.IPv4Address(str(self.before.strip()))

            ip_addr = self.get_interface_ipaddr(self.iface_dut)
            self.sendline("ip route | grep %s | awk '{print $1}'" % ip_addr)
            self.expect_exact("ip route | grep %s | awk '{print $1}'" % ip_addr)
            self.expect(self.prompt)
            self.lan_network = ipaddress.IPv4Network(str(self.before.strip()))
        self.sendline("ip -6 route")
        self.expect(self.prompt)

        # Setup HTTP proxy, so board webserver is accessible via this device
        self.sendline("curl --version")
        self.expect_exact("curl --version")
        self.expect(self.prompt)
        self.sendline("ab -V")
        self.expect(self.prompt)
        self.sendline("nmap --version")
        self.expect(self.prompt)
        self.start_webproxy(self.dante)
        # Write a useful ssh config for routers
        self.sendline("mkdir -p ~/.ssh")
        self.sendline("cat > ~/.ssh/config << EOF")
        self.sendline(f"Host {self.lan_gateway}")
        self.sendline("StrictHostKeyChecking no")
        self.sendline("UserKnownHostsFile=/dev/null")
        self.sendline("")
        self.sendline("Host krouter")
        self.sendline(f"Hostname {self.lan_gateway}")
        self.sendline("StrictHostKeyChecking no")
        self.sendline("UserKnownHostsFile=/dev/null")
        self.sendline("EOF")
        self.expect(self.prompt)
        # Copy an id to the router so people don't have to type a password to ssh or scp
        self.sendline(f"nc {self.lan_gateway} 22 -w 1 | cut -c1-3")
        self.expect_exact(f"nc {self.lan_gateway} 22 -w 1 | cut -c1-3")
        if 0 == self.expect(["SSH"] + self.prompt, timeout=5) and not self.is_bridged:
            self.sendcontrol("c")
            self.expect(self.prompt)
            self.sendline(
                '[ -e /root/.ssh/id_rsa ] || ssh-keygen -N "" -f /root/.ssh/id_rsa'
            )
            if 0 != self.expect(["Protocol mismatch."] + self.prompt):
                self.sendline(
                    "\nscp ~/.ssh/id_rsa.pub %s:/etc/dropbear/authorized_keys"
                    % self.lan_gateway
                )
                self.expect("_keys")
                if 0 == self.expect(["assword:"] + self.prompt):
                    self.sendline("password")
                    self.expect(self.prompt)
        else:
            self.sendcontrol("c")
            self.expect(self.prompt)

        if self.install_pkgs_after_dhcp:
            self.install_pkgs()

        if (
            wan_gw is not None
            and "options" in self.kwargs
            and "lan-fixed-route-to-wan" in self.kwargs["options"]
        ):
            self.sendline(f"ip route add {wan_gw} via {self.lan_gateway}")
            self.expect(self.prompt)
        ipv4 = self.get_interface_ipaddr(self.iface_dut)

        return ipv4, ipv6

    def tftp_server_ip_int(self):
        """Return the DUT facing side tftp server ip."""
        return self.gw

    def tftp_server_ipv6_int(self):
        """Return the DUT facing side tftp server ipv6."""
        return self.gwv6

    def get_shim_prefix(self):
        if getattr(self, "shim", ""):
            return self.shim

        self.sendline("alias mgmt")
        idx = self.expect(
            ["alias mgmt=", "alias: mgmt: not found", pexpect.TIMEOUT], timeout=10
        )
        self.expect(self.prompt)
        if idx == 0:
            self.shim = "mgmt "
        else:
            self.shim = ""

        return self.shim

    def configure_dhclient(self, dhcpopt):
        """configure dhclient options in lan dhclient.conf

        param dhcpopt: contains list of dhcp options to configure enable or disable
        type dhcpopt: list)
        """
        for opt, enable in dhcpopt:
            configure_option(opt, (self, enable))


if __name__ == "__main__":
    # Example use
    try:
        ipaddr, port = sys.argv[1].split(":")
    except Exception:
        raise Exception("First argument should be in form of ipaddr:port")
    dev = DebianBox(
        ipaddr=ipaddr, color="blue", username="root", password="bigfoot1", port=port
    )
    dev.sendline("echo Hello")
    dev.expect("Hello", timeout=4)
    dev.expect(dev.prompt)

    if sys.argv[2] == "setup_as_lan_device":
        dev.configure("lan_device")
    if sys.argv[2] == "setup_as_wan_gateway":
        dev.configure("wan_device")
