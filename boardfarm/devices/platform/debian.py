#!/usr/bin/env python3
# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import atexit
import copy
import ipaddress
import logging
import os  # noqa : F401
import re
import sys
import time
from collections import defaultdict

import pexpect
from nested_lookup import nested_lookup
from termcolor import colored

from boardfarm.devices import linux  # noqa : F401
from boardfarm.exceptions import PexpectErrorTimeout
from boardfarm.lib.bft_pexpect_helper import bft_pexpect_helper
from boardfarm.lib.installers import apt_install

logger = logging.getLogger("bft")


class DebianBox(linux.LinuxDevice):
    """A linux machine running an ssh server."""

    prompt = ["root\\@.*:.*#", "/ # ", ".*:~ #"]
    sign_check = True
    pkgs_installed = False
    install_pkgs_after_dhcp = False
    tftp_device = None
    tftp_dir = "/tftpboot"
    iface_dut = "eth1"
    gw = None
    init_static_ip = ipaddress.ip_address("192.168.0.10")
    ipv6_prefix = 64

    def parse_device_options(self, *args, **kwargs):
        self.args = args
        self.kwargs = {}
        for k, v in kwargs.items():
            if getattr(kwargs[k], "name", "") != "device_manager":
                self.kwargs[k] = copy.deepcopy(v)
        self.username = kwargs.pop("username", "root")
        self.password = kwargs.pop("password", "bigfoot1")
        self.output = kwargs.pop("output", sys.stdout)
        self.dev_array = kwargs.pop("dev_array", None)
        name = kwargs.pop("name", None)
        ipaddr = kwargs.pop("ipaddr", None)
        color = kwargs.pop("color", "black")
        port = kwargs.pop("port", "22")
        reboot = kwargs.pop("reboot", False)
        location = kwargs.pop("location", None)
        cmd = kwargs.pop("cmd", None)
        pre_cmd_host = kwargs.pop("pre_cmd_host", None)
        post_cmd_host = kwargs.pop("post_cmd_host", None)
        post_cmd = kwargs.pop("post_cmd", None)
        cleanup_cmd = kwargs.pop("cleanup_cmd", None)

        self.http_proxy = kwargs.pop("http_proxy", ipaddr + ":8080")
        self.tftp_device = self
        self.dante = False
        self.legacy_add = False
        if "options" in kwargs:
            for opt in kwargs["options"].split(","):
                opt = opt.strip()
                if opt == "dante":
                    self.dante = True
                elif opt == "wan-dhcp-client-v6":
                    self.wan_dhcpv6 = True
                elif opt == "wan-no-dhcp-server":
                    self.wan_dhcp_server = False
                elif opt == "wan-no-eth0":
                    self.wan_no_eth0 = True
                elif opt == "wan-dhcp-client":
                    self.wan_dhcp = True
                elif opt.startswith("wan-static-ipv6:"):
                    ipv6_address = str(  # noqa : F821
                        opt.replace("wan-static-ipv6:", "")
                    )
                    if "/" not in opt:
                        ipv6_address += "/%s" % str(  # noqa : F821
                            str(self.ipv6_prefix)
                        )
                    self.ipv6_interface = ipaddress.IPv6Interface(  # noqa : F821
                        ipv6_address
                    )
                    self.ipv6_prefix = self.ipv6_interface._prefixlen
                    self.gwv6 = self.ipv6_interface.ip
                elif opt.startswith("wan-static-ip:"):
                    value = str(opt.replace("wan-static-ip:", ""))  # noqa : F401
                    if "/" not in value:
                        value += "/24"
                    self.gw_ng = ipaddress.IPv4Interface(value)  # noqa : F821
                    self.nw = self.gw_ng.network
                    self.gw_prefixlen = self.nw._prefixlen
                    self.gw = self.gw_ng.ip
                    self.static_ip = True
                elif opt.startswith("static-route:"):
                    self.static_route = opt.replace("static-route:", "").replace(
                        "-", " via "
                    )
                elif opt.startswith("static-route6:"):
                    self.static_route6 = opt.replace("static-route6:", "").replace(
                        "-", " via "
                    )
                elif opt.startswith("wan-static-route:"):
                    self.static_route = opt.replace("wan-static-route:", "").replace(
                        "-", " via "
                    )
                elif opt.startswith("mgmt_dns:"):
                    value = opt.replace("mgmt_dns:", "").strip()
                    self.mgmt_dns = ipaddress.IPv4Interface(value).ip  # noqa : F821
                elif opt == "lan-fixed-route-to-wan":
                    self.lan_fixed_route_to_wan = self.options[opt]

        if pre_cmd_host is not None:
            sys.stdout.write("\tRunning pre_cmd_host.... ")
            sys.stdout.flush()
            phc = bft_pexpect_helper.spawn(
                command="bash", args=["-c", pre_cmd_host], env=self.dev.env
            )
            phc.expect(pexpect.EOF, timeout=120)
            logger.info("\tpre_cmd_host done")

        if ipaddr is not None:
            bft_pexpect_helper.spawn.__init__(
                self,
                command="ssh",
                args=[
                    f"{self.username}@{ipaddr}",
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
                env={"TERM": "xterm-mono"},
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
            logger.info("\tcmd done")

        self.name = name
        self.color = color
        if self.username != "root":
            self.prompt.append(f"{self.username}\\@.*:.*$")
        self.port = port
        self.location = location

        self.check_connection(self.username, name, self.password)

        # attempts to fix the cli colums size
        self.set_cli_size(300)

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
                logger.error("\tpost_cmd_host did not complete, it likely failed\n")
            else:
                logger.info("\tpost_cmd_host done")

        if post_cmd is not None:
            sys.stdout.write("\tRunning post_cmd.... ")
            sys.stdout.flush()
            env_prefix = "".join(f"export {k}={v}; " for k, v in self.dev.env.items())
            self.sendline(env_prefix + post_cmd)
            self.expect(self.prompt)
            logger.info("\tpost_cmd done")

        if reboot:
            self.reset()

        self.logfile_read = self.output
        self.configure_gw_ip()

    def configure_gw_ip(self):
        if self.gw is None:
            self.gw_ng = ipaddress.ip_interface(f"{DebianBox.init_static_ip}/24")
            DebianBox.init_static_ip += 1
            self.gw = self.gw_ng.ip
            self.nw = self.gw_ng.network
            self.gw_prefixlen = self.nw.prefixlen

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
                logger.debug(self.before)
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
        logger.debug(colored(cmsg, None, attrs=["bold"]))

    def get_default_gateway(self, interface):
        self.sendline(f"ip route | grep {interface!s}")
        self.expect(self.prompt)

        match = re.search(f"default via (.*) dev {interface!s}.*\r\n", self.before)
        if match:
            return match.group(1)
        else:
            return None

    def run_cleanup_cmd(self):
        sys.stdout.write(f"Running cleanup_cmd on {self.name}...")
        sys.stdout.flush()
        cc = bft_pexpect_helper.spawn(
            command="bash", args=["-c", self.cleanup_cmd], env=self.dev.env
        )
        cc.expect(pexpect.EOF, timeout=120)
        print("cleanup_cmd done.")

    def reset(self):
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
                logger.error(self.name + f" not up yet, after {i + 15} seconds.")
            else:
                logger.info(
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
        if self.pkgs_installed:
            return

        self.sendline(
            'echo "Acquire::ForceIPv4 "true";" > /etc/apt/apt.conf.d/99force-ipv4'
        )
        self.expect(self.prompt)

        set_iface_again = False
        if (
            not self.wan_no_eth0
            and not self.wan_dhcp
            and not self.install_pkgs_after_dhcp
            and not getattr(self, "standalone_provisioner", False)
        ):
            set_iface_again = True
            self.sendline(f"ifconfig {self.iface_dut} down")
            self.expect(self.prompt)

        pkgs = "xinetd tinyproxy nmap psmisc tftpd-hpa pppoe isc-dhcp-server procps iptables lighttpd dnsmasq xxd dante-server rsyslog snmp"

        def _install_pkgs():
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
                apt_install(
                    self, pkgs, dpkg_options='-o DPkg::Options::="--force-confnew"'
                )
                # self.sendline(
                #    % pkgs
                # if 0 == self.expect(["Reading package", pexpect.TIMEOUT], timeout=60):
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

        if set_iface_again:
            self.sendline(f"ifconfig {self.iface_dut} {self.gw_ng}")
            self.expect(self.prompt)
            self.sendline(f"ifconfig {self.iface_dut} up")
            self.expect(self.prompt)
            if self.static_route is not None:
                self.sendline(f"ip route add {self.static_route}")
                self.expect(self.prompt)

    def turn_on_pppoe(self):
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
        self.sendline("\nkillall pppoe-server pppoe pppd")
        self.expect("pppd")
        self.expect(self.prompt)

    def start_webserver(self):
        self.sendline("service lighttpd restart")
        self.expect_prompt()

    # TODO: This may conflict with Ayush changes. To be revisited.
    def download_from_server(
        self,
        url: str,
        extra: str = "",
    ):
        self.sendline(f"mgmt wget {url} {extra}")
        self.expect_prompt(timeout=120)

    def start_tftp_server(self, ip=None):
        # we can call this first, before configure so we need to do this here
        # as well
        self.install_pkgs()
        # the entire reason to start tftp is to copy files to devices
        # which we do via ssh so let's start that as well
        self.start_sshd_server()

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
        if ip:
            self.sendline(f"ifconfig {self.iface_dut} {ip}")
            self.expect(self.prompt)
        self.restart_tftp_server()

    # mode can be "ipv4" or "ipv6"
    def restart_tftp_server(self, mode=None):
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

    def configure(self, config=None):
        # TODO: wan needs to enable on more so we can route out?
        if config is None:
            config = []
        self.enable_ipv6(self.iface_dut)
        self.install_pkgs()
        self.start_sshd_server()
        self.setup(config=config)

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

    def setup_dnsmasq(self, config=None):
        self.sendline("cat > /etc/dnsmasq.conf << EOF")
        self.sendline("local-ttl=60")
        upstream_dns = "8.8.4.4"
        if self.mgmt_dns:
            upstream_dns = self.mgmt_dns
        if self.auth_dns:
            upstream_dns = "127.0.0.1"
        self.sendline(f"server={upstream_dns}")
        self.sendline("listen-address=127.0.0.1")
        self.sendline(f"listen-address={self.gw}")
        if self.gwv6 is not None:
            self.sendline(f"listen-address={self.gwv6}")
        self.sendline(
            "addn-hosts=/etc/dnsmasq.hosts"
        )  # all additional hosts will be added to dnsmasq.hosts
        self.sendline(
            f"auth-zone=boardfarm.com,{self.gw_ng.network},{self.ipv6_interface.network}"
        )
        self.sendline("auth-zone=google.com")
        self.sendline(f"auth-server=wan.boardfarm.com,{self.iface_dut}")
        self.check_output("EOF")
        self.add_hosts(config=config)
        self.restart_dns_server()

    def restart_dns_server(self):
        self.sendline("/etc/init.d/dnsmasq restart")
        self.expect(self.prompt)
        self.sendline(f'echo "nameserver {self.gw}" > /etc/resolv.conf')
        self.expect(self.prompt)

    def modify_dns_hosts(self, dns_entry=None):
        self.hosts = getattr(self, "hosts", defaultdict(list))

        if dns_entry:
            self.hosts.update(dns_entry)
            self.sendline("cat > /etc/dnsmasq.hosts << EOF")
            for host, ips in self.hosts.items():
                for ip in set(ips):
                    self.sendline(ip + " " + host)
            self.check_output("EOF")
            self.restart_dns_server()

    def add_hosts(self, addn_host=None, config=None):
        # to add extra hosts(dict) to dnsmasq.hosts if dns has to run in wan container
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

        if hasattr(self, "profile"):
            host_dicts = nested_lookup("hosts", self.profile.get(self.name, {}))
            for i in host_dicts:
                _update_host_dict(i)
        if config is not None and hasattr(config, "board"):
            for dev in config.devices:
                d = getattr(config, dev, None)
                if hasattr(d, "dns"):
                    v4_hosts = d.dns.hosts_v4
                    v6_hosts = d.dns.hosts_v6
                    for host_val in v4_hosts, v6_hosts:
                        for host, ips in host_val.items():
                            for ip in set(ips):
                                self.hosts[host].append(ip)

        if self.hosts:
            self.sendline("cat > /etc/dnsmasq.hosts << EOF")
            for host, ips in self.hosts.items():
                for ip in set(ips):
                    self.sendline(ip + " " + host)
            self.check_output("EOF")
        if restart:
            self.restart_dns_server()

    def remove_hosts(self):
        # TODO: we should probably be specific here whether we want to remove
        # everything or just few hosts.
        self.sendline("rm  /etc/dnsmasq.hosts")
        self.expect(self.prompt)
        self.sendline("/etc/init.d/dnsmasq restart")
        self.expect(self.prompt)

    def tftp_server_ip_int(self):
        """Return the DUT facing side tftp server ip."""
        return self.gw

    def tftp_server_ipv6_int(self):
        """Return the DUT facing side tftp server ipv6."""
        return self.gwv6

    def setup(self, config):
        """setup device"""
        Exception("Not implemented")

    def get_shim_prefix(self):
        # pylint: disable=access-member-before-definition
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

    def check_dut_iface(self):
        """Check that the dut iface exists and has a carrier"""
        output = self.check_output(f"ip link show {self.iface_dut}")
        if (
            self.iface_dut not in output
            or f'Device "{self.iface_dut}" does not exist' in output
        ):
            output = self.check_output("ip link")
            msg = colored(
                f"{self.name}: {self.iface_dut} NOT found\n{output}",
                color="red",
                attrs=["bold"],
            )
            logger.error(msg)
            raise Exception(msg)
        return output
