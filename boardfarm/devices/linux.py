#!/usr/bin/env python3
import binascii
import ipaddress
import logging
import os
import re
from contextlib import contextmanager, suppress
from typing import Any, Dict, Optional, Union

import jc.parsers.ping
import pexpect

from boardfarm.exceptions import BftIfaceNoIpV6Addr, CodeError, PexpectErrorTimeout
from boardfarm.lib.regexlib import (
    AllValidIpv6AddressesRegex,
    InterfaceIPv6_AddressRegex,
    LinuxMacFormat,
    ValidIpv4AddressRegex,
)

from . import base

BFT_DEBUG = "BFT_DEBUG" in os.environ
logger = logging.getLogger("bft")


class LinuxInterface:
    """Linux implementations. Cannot be instantiated by itself."""

    tftp_dir = "/tftpboot"
    sign_check = True
    iface_dut: Optional[str] = None
    name: str = ""
    gw: str = ""

    def check_status(self):
        """Check the state of the device."""
        logger.debug(f"\n\nRunning check_status() on {self.name}")
        self.sendline(
            "\ncat /proc/version; cat /proc/uptime; ip a; ifconfig; route -n; route -6 -n"
        )
        self.expect_exact(
            "cat /proc/version; cat /proc/uptime; ip a; ifconfig; route -n; route -6 -n"
        )
        self.expect("version", timeout=5)
        self.expect(self.prompt, timeout=5)

    @property
    def hostname(self):
        return self.check_output("echo $HOSTNAME")

    def get_interface_ipaddr(self, interface):
        """Get ipv4 address of interface."""
        self.sendline(f"\nifconfig {interface}")
        regex = [
            r"addr:(\d{1,3}.\d{1,3}.\d{1,3}.\d{1,3}).*(Bcast|P-t-P):",
            r"inet:?\s*(\d{1,3}.\d{1,3}.\d{1,3}.\d{1,3}).*(broadcast|P-t-P|Bcast)",
            "inet ("
            + ValidIpv4AddressRegex
            + ").*netmask ("
            + ValidIpv4AddressRegex
            + ").*destination "
            + ValidIpv4AddressRegex,
        ]
        self.expect(regex)
        try:
            ipaddr = self.match.group(1)
        except AttributeError as e:
            raise PexpectErrorTimeout(e)
        ipv4address = str(ipaddress.IPv4Address(str(ipaddr)))
        self.expect(self.prompt)
        logger.debug(f"ifconfig {interface} IPV4 {ipv4address}")
        return ipv4address

    def get_interface_mask(self, interface):
        """Get ipv4 mask of interface."""
        self.sendline(f"\nifconfig {interface}")
        regex = [
            r"(?<=netmask )" + ValidIpv4AddressRegex,
            r"(?<=Mask:)" + ValidIpv4AddressRegex,
        ]
        self.expect(regex)
        ipaddr = self.match.group(0)
        self.expect(self.prompt)
        logger.debug(f"ifconfig {interface} IPV4 Mask {ipaddr}")
        return ipaddr

    def _get_interface_ip6addr_generic(self, interface, address_type):
        """Generic method to get ipv6 address of interface."""
        regex = [AllValidIpv6AddressesRegex, InterfaceIPv6_AddressRegex]
        self.expect(pexpect.TIMEOUT, timeout=0.5)
        self.before = ""
        output = self.check_output(f"ifconfig {interface} | sed 's/inet6 /bft_inet6 /'")
        logger.debug(output)

        ips = re.compile("|".join(regex), re.M | re.U).findall(output)
        for i in ips:
            try:
                # we use IPv6Interface for convenience (any exception will be ignored)
                ipv6_iface = ipaddress.IPv6Interface(str(i))
                if ipv6_iface and (
                    (address_type == "private" and ipv6_iface.is_private)
                    or (address_type == "link-local" and ipv6_iface.is_link_local)
                    or (address_type == "global" and ipv6_iface.is_global)
                ):
                    logger.debug(f"ifconfig {interface} IPV6 {str(ipv6_iface.ip)}")
                    return str(ipv6_iface.ip)
            except Exception:
                continue

        logger.debug(f"Failed ifconfig {interface} IPV6 {ips}")
        raise BftIfaceNoIpV6Addr(f"Did not find {address_type} ipv6 address")

    def get_interface_ip6addr(self, interface):
        """Get ipv6 address of interface."""
        # to minimise the chance of getting stray ipv6 addresses from the pexpect
        # ".before" buffer tagging with bft_inet6 the lines of OUR command output that
        # have an ipv6 address (so we can pick them later)
        # REASON: on some linux based embedded devices the console can be VERY verbose
        # and spurious debug messages can have ipv6 addresses in it

        return self._get_interface_ip6addr_generic(interface, "global")

    def get_interface_link_local_ip6addr(self, interface):
        """function helps in getting ipv6 link local address of the interface
        :param device: device name
        :param interface: interface name to get the link local
        :return link_local: Link local address of the interface
        : return type: string
        """

        return self._get_interface_ip6addr_generic(interface, "link-local")

    def get_interface_private_ip6addr(self, interface):
        """function helps in getting private ipv6 address of the interface
        :param interface: interface name to get the iprivate ipv6 address
        :return private_ipv6: Private IPv6 address of the interface
        : return type: string
        """

        return self._get_interface_ip6addr_generic(interface, "private")

    def get_interface_macaddr(self, interface):
        """Get the interface macaddress."""
        self.sendline(f"cat /sys/class/net/{interface}/address | \\")
        self.sendline("awk '{print \"bft_macaddr : \"$1}'")
        self.expect(f"bft_macaddr : {LinuxMacFormat}")
        macaddr = self.match.group(1)
        self.expect(self.prompt)
        return macaddr

    def get_seconds_uptime(self):
        """Return seconds since last reboot. Stored in /proc/uptime."""
        self.sendcontrol("c")
        self.expect(self.prompt)
        self.sendline("\ncat /proc/uptime")
        self.expect(r"((\d+)\.(\d{2}))(\s)(\d+)\.(\d{2})")
        seconds_up = float(self.match.group(1))
        self.expect(self.prompt)
        return seconds_up

    def enable_ipv6(self, interface):
        """Enable ipv6 of the interface."""
        self.sendline("sysctl net.ipv6.conf." + interface + ".accept_ra=2")
        self.expect(self.prompt, timeout=30)
        self.sendline("sysctl net.ipv6.conf." + interface + ".disable_ipv6=0")
        self.expect(self.prompt, timeout=30)

    def set_static_ip(self, interface, fix_ip, fix_mark):
        """Set static ip of the interface."""
        self.sudo_sendline(f"ifconfig {interface} {fix_ip} netmask {fix_mark} up")
        self.expect(self.prompt)

        ip = self.get_interface_ipaddr(interface)
        if ip == fix_ip:
            return ip
        else:
            return None

    def disable_ipv6(self, interface):
        """Disable ipv6 of the interface."""
        self.sendline("sysctl net.ipv6.conf." + interface + ".disable_ipv6=1")
        self.expect(self.prompt, timeout=30)

    def release_dhcp(self, interface):
        """Release ip of the interface."""
        self.sudo_sendline(f"dhclient -r {interface!s}")
        self.expect(self.prompt)

    def renew_dhcp(self, interface):
        """Renew ip of the interface."""
        self.sudo_sendline(f"dhclient -v {interface!s}")
        if 0 == self.expect([pexpect.TIMEOUT] + self.prompt, timeout=30):
            self.sendcontrol("c")
            self.expect(self.prompt)
        return self.before

    def release_ipv6(self, interface, stateless=False):
        """Release ipv6 for the interface."""
        mode = "-S" if stateless else "-6"
        self.sudo_sendline(f"dhclient {mode} -r {interface!s}")
        self.expect(self.prompt)

    def renew_ipv6(self, interface, stateless=False):
        """Renew ipv6 for the interface."""
        mode = "-S" if stateless else "-6"
        self.sudo_sendline(f"dhclient {mode} -v {interface!s}")
        if 0 == self.expect([pexpect.TIMEOUT] + self.prompt, timeout=15):
            self.sendcontrol("c")
            self.expect(self.prompt)
        return self.before

    def check_access_url(self, url, source_ip=None):
        """Check source_ip can access url.

        Name: check_access_url
        Purpose: check source_ip can access url
        Input:  url, source_ip
        Output: True or False
        """
        if source_ip is None:
            self.sendline(f"curl -I {url!s}")
        else:
            self.sendline(f"curl --interface {source_ip!s} -I {url!s}")
        try:
            self.expect(self.prompt, timeout=10)
        except pexpect.TIMEOUT:
            self.sendcontrol("c")
            self.expect(self.prompt)

        match = re.search(r"HTTP\/.* 200", self.before)
        if match:
            return True
        else:
            return False

    def kill_dhclient(self, ipv6=False):
        """To kill dhclient process

        param ipv6: True/False; defaults to false
        type ipv6: boolean
        """
        var = "6" if ipv6 else ""
        self.sendline(f"kill $(</run/dhclient{var}.pid)")
        self.expect(self.prompt)

        self.sendline("ps aux")
        if self.expect(["dhclient"] + self.prompt) == 0:
            logger.warning(
                "WARN: dhclient still running, something started rogue client!"
            )
            self.sendline(f"pkill --signal 9 -f dhclient.*{self.iface_dut}")
            self.expect(self.prompt)

    def set_password(self, password):
        """Set password using passwd command."""
        self.sendline("passwd")
        self.expect("password:", timeout=8)
        self.sendline(password)
        self.expect("password:")
        self.sendline(password)
        self.expect(self.prompt)

    def set_printk(self, CUR=1, DEF=1, MIN=1, BTDEF=7):
        """Modify the log level in kernel."""
        try:
            self.sendline(
                '\necho "%d %d %d %d" > /proc/sys/kernel/printk'
                % (CUR, DEF, MIN, BTDEF)
            )
            self.expect("echo")
            self.expect(self.prompt, timeout=10)
        except Exception:
            pass

    def prefer_ipv4(self, pref=True):
        """Edits the /etc/gai.conf file.

        This is to give/remove ipv4 preference (by default ipv6 is preferred)
        See /etc/gai.conf inline comments for more details
        """
        if pref is True:
            self.sendline(
                r"sed -i 's/^#precedence ::ffff:0:0\/96  100/precedence ::ffff:0:0\/96  100/'  /etc/gai.conf"
            )
        else:
            self.sendline(
                r"sed -i 's/^precedence ::ffff:0:0\/96  100/#precedence ::ffff:0:0\/96  100/'  /etc/gai.conf"
            )
        self.expect(self.prompt)

    def ping(
        self,
        ping_ip: str,
        ping_count: int = 4,
        ping_interface: Optional[str] = None,
        options: str = "",
        timeout: int = 50,
        json_output: bool = False,
    ) -> Union[bool, Dict[str, Any]]:
        """Ping remote host. Return True if ping has 0% loss
        or parsed output in JSON if json_output=True flag is provided.

        :param ping_ip: ping ip
        :type ping_ip: str
        :param ping_count: number of ping, defaults to 4
        :type ping_count: int, optional
        :param ping_interface: ping via interface, defaults to None
        :type ping_interface: str, optional
        :param options: extra ping options, defaults to ""
        :type options: str, optional
        :param timeout: timeout, defaults to 50
        :type timeout: int, Optional
        :param json_output: return ping output in dictionary format, defaults to False
        :type json_output: bool, optional
        :return: ping output
        :rtype: bool or dict of ping output
        """
        basic_cmd = f"ping -c {ping_count} {ping_ip}"

        if ping_interface:
            basic_cmd += f" -I {ping_interface}"

        basic_cmd += f" {options}"
        self.sendline(basic_cmd)
        self.expect(self.prompt, timeout=timeout)

        if json_output:
            return jc.parsers.ping.parse(self.before)

        match = re.search(
            "%s packets transmitted, %s [packets ]*received, 0%% packet loss"
            % (ping_count, ping_count),
            self.before,
        )
        return bool(match)

    def traceroute(self, host_ip, version="", options="", timeout=60):
        """Traceroute returns the route that packets take to a network host."""
        try:
            self.sendline(f"traceroute{version} {options} {host_ip}")
            self.expect_exact(f"traceroute{version} {options} {host_ip}")
            self.expect_prompt(timeout=timeout)
            return self.before
        except pexpect.TIMEOUT:
            self.sendcontrol("c")
            self.expect(self.prompt)
            return None

    def is_link_up(self, interface, pattern="BROADCAST,MULTICAST,UP"):
        """Check the interface status."""
        self.sendline(f"ip link show {interface}")
        self.expect(self.prompt)
        link_state = self.before
        match = re.search(pattern, link_state)
        if match:
            return match.group(0)
        else:
            return None

    def get_process_status(self, process_name, options=""):
        """Return the process status output
        Args:
            process name (string): linux process name eg: "ping"
            options (string): ps options eg "-ef", "-aux"
            eg command: "ps -ef | grep ping"
        """
        command = f"ps {options} | grep {process_name}"
        self.sendline(command)
        self.expect_exact(command)
        self.expect(self.prompt)
        return self.before

    def set_link_state(self, interface, state):
        """Set the interface status."""
        self.sudo_sendline(f"ip link set {interface} {state}")
        self.expect(self.prompt)

    def add_new_user(self, id, pwd):
        """Create new login ID. But check if already exists."""
        self.sendline(f"\nadduser {id}")
        try:
            self.expect_exact("Enter new UNIX password", timeout=5)
            self.sendline(f"{pwd}")
            self.expect_exact("Retype new UNIX password")
            self.sendline(f"{pwd}")
            self.expect_exact("Full Name []")
            self.sendline(f"{id}")
            self.expect_exact("Room Number []")
            self.sendline("1")
            self.expect_exact("Work Phone []")
            self.sendline("4081234567")
            self.expect_exact("Home Phone []")
            self.sendline("4081234567")
            self.expect_exact("Other []")
            self.sendline("4081234567")
            self.expect_exact("Is the information correct?")
            self.sendline("y")
            self.expect(self.prompt)
            self.sendline(f"usermod -aG sudo {id}")
            self.expect(self.prompt)
            # Remove "$" in the login prompt and replace it with "#"
            self.sendline(r"sed -i \'s/\\w\\\$ /\\\w# /g\' //home/%s/.bashrc" % id)
            self.expect(self.prompt, timeout=30)
        except Exception:
            self.expect(self.prompt, timeout=30)

    def copy_file_to_server(self, src, dst=None):
        """Copy the file from source to destination."""

        def gzip_str(string_):
            import gzip
            import io

            out = io.BytesIO()
            with gzip.GzipFile(fileobj=out, mode="w") as file:
                file.write(string_)
            return out.getvalue()

        with open(src, mode="rb") as file:
            bin_file = binascii.hexlify(gzip_str(file.read()))
        if dst is None:
            dst = self.tftp_dir + "/" + os.path.basename(src)
        logger.info(f"Copying {src} to {dst}")
        self.sendline(
            f"""cat << EOFEOFEOFEOF | xxd -r -p | gunzip > {dst}
{bin_file}
EOFEOFEOFEOF"""
        )
        self.expect(self.prompt)
        self.sendline(f"ls {dst}")
        self.expect_exact(f"ls {dst}")
        i = self.expect(
            [f"ls: cannot access {dst}: No such file or directory"] + self.prompt
        )
        if i == 0:
            raise Exception("Failed to copy file")

    def ip_neigh_flush(self):
        """Remove entries in the neighbour table."""
        self.sendline("\nip -s neigh flush all")
        self.expect("flush all")
        self.expect(self.prompt)

    def sudo_sendline(self, cmd):
        """Add sudo in the sendline if username is root."""
        if self.username != "root":
            self.sendline("sudo true")
            i = self.expect(["password for .*:", "Password:"] + self.prompt)
            if i > 1:
                will_prompt_for_password = False
            else:
                will_prompt_for_password = True

            cmd = "sudo " + cmd
            if will_prompt_for_password:
                self.sendline(self.password)
                self.expect(self.prompt)
        super().sendline(cmd)

    def set_cli_size(self, columns):
        """Set the terminal columns value."""
        self.sendline(f"stty columns {str(columns)}")
        self.expect(self.prompt)

    def wait_for_linux(self):
        """Verify Linux starts up."""
        i = self.expect(
            [
                "Reset Button Push down",
                "Linux version",
                "Booting Linux",
                "Starting kernel ...",
                "Kernel command line specified:",
            ],
            timeout=45,
        )
        if i == 0:
            self.expect("httpd")
            self.sendcontrol("c")
            self.expect(self.uprompt)
            self.sendline("boot")
        i = self.expect(
            ["U-Boot", "login:", "Please press Enter to activate this console"]
            + self.prompt,
            timeout=150,
        )
        if i == 0:
            raise Exception("U-Boot came back when booting kernel")
        elif i == 1:
            self.sendline("root")
            if 0 == self.expect(["assword:"] + self.prompt):
                self.sendline("password")
                self.expect(self.prompt)

    def get_dns_server_upstream(self):
        """Get the IP of name server."""
        self.sendline("grep nameserver /etc/resolv.conf")
        self.expect_exact("grep nameserver /etc/resolv.conf")
        self.expect(self.prompt)
        return self.before

    def get_nf_conntrack_conn_count(self):
        """Get the total number of connections in the network."""
        pp = self.get_pp_dev()

        for _ in range(5):
            try:
                pp.sendline("cat /proc/sys/net/netfilter/nf_conntrack_count")
                pp.expect_exact(
                    "cat /proc/sys/net/netfilter/nf_conntrack_count", timeout=2
                )
                pp.expect(pp.prompt, timeout=15)
                ret = int(pp.before.strip())

                self.touch()
                return ret
            except Exception:
                continue
            else:
                raise Exception("Unable to extract nf_conntrack_count!")

    def get_proc_vmstat(self, pp=None):
        """Get the virtual machine status."""
        if pp is None:
            pp = self.get_pp_dev()

        for _ in range(5):
            try:
                pp.sendline("cat /proc/vmstat")
                pp.expect_exact("cat /proc/vmstat")
                pp.expect(pp.prompt)
                results = re.findall(r"(\w+) (\d+)", pp.before)
                ret = {}
                for key, value in results:
                    ret[key] = int(value)

                return ret
            except Exception as e:
                logger.error(e)
                continue
            else:
                raise Exception("Unable to parse /proc/vmstat!")

    def wait_for_network(self):
        """Wait until network interfaces have IP Addresses."""
        for interface in [self.wan_iface, self.lan_iface]:
            for _ in range(5):
                try:
                    if interface is not None:
                        ipaddr = self.get_interface_ipaddr(interface).strip()
                        if not ipaddr:
                            continue
                        self.sendline("route -n")
                        self.expect(interface, timeout=2)
                        self.expect(self.prompt)
                except PexpectErrorTimeout:
                    logger.error("waiting for wan/lan ipaddr")
                else:
                    break

    def get_memfree(self):
        """Return the kB of free memory."""
        # free pagecache, dentries and inodes for higher accuracy
        self.sendline("\nsync; echo 3 > /proc/sys/vm/drop_caches")
        self.expect("drop_caches")
        self.expect(self.prompt)
        self.sendline("cat /proc/meminfo | head -2")
        self.expect(r"MemFree:\s+(\d+) kB")
        memFree = self.match.group(1)
        self.expect(self.prompt)
        return int(memFree)

    def start_webproxy(self, dante=False):
        if dante:
            self.stop_tinyproxy()
            self.start_danteproxy()
        else:
            self.stop_danteproxy()
            self.start_tinyproxy()

    def start_danteproxy(self):
        """Start the dante server for socks5 proxy connections"""

        to_send = [
            "cat > /etc/danted.conf <<EOF",
            "logoutput: stderr",
            "internal: 0.0.0.0 port = 8080",
            f"external: {self.iface_dut}",
            "clientmethod: none",
            "socksmethod: username none #rfc931",
            "user.privileged: root",
            "user.unprivileged: nobody",
            "user.libwrap: nobody",
            "client pass {",
            "    from: 0.0.0.0/0 to: 0.0.0.0/0",
            "    log: connect disconnect error",
            "}",
            "socks pass {",
            "    from: 0.0.0.0/0 to: 0.0.0.0/0",
            "    log: connect disconnect error",
            "}",
            "EOF",
        ]
        self.sendline("\n".join(to_send))
        self.expect_prompt()
        # NOTE: service danted restart DOES NOT WORK!
        self.sendline("service danted stop; service danted start")
        self.expect_prompt()

    def stop_danteproxy(self):
        self.sendline("service danted stop")
        self.expect_prompt()

    def stop_tinyproxy(self):
        self.sendline("/etc/init.d/tinyproxy stop")
        self.expect_prompt()

    def start_tinyproxy(self):
        # TODO: determine which config file is the correct one... but for now just modify both
        for f in ["/etc/tinyproxy.conf", "/etc/tinyproxy/tinyproxy.conf"]:
            self.sendline(f"sed -i 's/^Port 8888/Port 8080/' {f}")
            self.expect(self.prompt)
            self.sendline(f"sed 's/#Allow/Allow/g' -i {f}")
            self.expect(self.prompt)
            self.sendline(f"sed '/Listen/d' -i {f}")
            self.expect(self.prompt)
            self.sendline(f"sed '/ConnectPort/d' -i {f}")
            self.expect(self.prompt)
            self.sendline(f'echo "Listen 0.0.0.0" >> {f}')
            self.expect(self.prompt)
            self.sendline(f'echo "Listen ::" >> {f}')
            self.expect(self.prompt)
        self.sendline("/etc/init.d/tinyproxy restart")
        self.expect("Restarting")
        self.expect(self.prompt)
        self.sendline("sleep 3; ps auxwww")
        self.expect("/usr/sbin/tinyproxy")
        self.expect_prompt()

    def take_lock(self, file_lock, fd=9, timeout=200):
        """Take a file lock on file_lock."""
        self.sendline(f"exec {fd}>{file_lock}")
        self.expect(self.prompt)
        self.sendline(f"flock -x {fd}")
        self.expect(self.prompt, timeout=timeout)

    def release_lock(self, file_lock, fd=9):
        """Releases a lock taken."""
        self.sendline(f"flock -u {fd}")
        self.expect(self.prompt)

    def perform_curl(self, host_ip, protocol, port=None, options=""):
        """Perform curl action to web service running on host machine.

        :param dev : dev to perform curl
        :type dev : device object
        :param host_ip : ip address of the server device
        :type host_ip : str
        :param protocol : Web Protocol (http or https)
        :type protocol : str
        :param port : port number of server
        :type port : str, default to None
        :param options : Additional curl option
        :type options : str, default to empty
        """
        if port:
            if re.search(AllValidIpv6AddressesRegex, host_ip) and "[" not in host_ip:
                host_ip = "[" + host_ip + "]"
            web_addr = f"{protocol}://{host_ip}:{str(port)}"
        else:
            web_addr = f"{protocol}://{host_ip}"
        command = f"curl {options} {web_addr}"
        logger.info(self.before)
        self.before = None
        self.sendline(command)
        index = self.expect(
            ["Connected to"]
            + ["DOCTYPE html PUBLIC"]
            + ["doctype html"]
            + ["Connection timed out"]
            + ["Failed to connect to"]
            + ["Couldn't connect to server"],
            timeout=100,
        )
        try:
            self.expect_prompt()
        except pexpect.exceptions.TIMEOUT:
            self.sendcontrol("c")
            self.expect_prompt()
        return index in [0, 1, 2]

    def get_lease_time(self):
        """Get DHCP lease time from dhclient.leases file.

        :return: lease_time
        :rtype: integer
        """
        self.sendline("\ncat /var/lib/dhcp/dhclient.leases | grep dhcp-lease-time")
        self.expect(r"\s+option\sdhcp-lease-time\s(\d+);")
        lease_time = int(self.match.group(1))
        self.expect(self.prompt)
        return lease_time

    def scp(
        self,
        host: str,
        port: Union[int, str],
        username: str,
        password: str,
        src_path: str,
        dst_path: str,
        action: str = "download",
        scp_command: str = "scp",
        timeout: int = 30,
    ) -> None:
        """Scp file to remote host

        :param host: remote host ssh IP
        :param port: remote host ssh port number
        :param username: ssh username
        :param password: ssh password
        :param src_path: copy this
        :param dst_path: to that
        :param action: download or upload.
        :param scp_command: command name. Could be used if scp name was changed to something else
        :param timeout: timeout value for the expect
        """
        if action == "download":
            command = f"{scp_command} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -q -P {port} {username}@{host}:{src_path} {dst_path}"
        else:
            command = f"{scp_command} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -q -P {port} {src_path} {username}@{host}:{dst_path}"
        print(f"Sending {command}")
        self.sendline(command)
        first_time = self.expect(
            [pexpect.TIMEOUT, "continue connecting?"], timeout=timeout
        )
        if first_time:
            self.sendline("y")
        self.expect("assword:", timeout=timeout)
        self.sendline(password)
        self.expect_prompt(timeout=timeout)

    def get_date(self):
        """Get the system date and time

        :return: CM date
        :rtype: str
        """
        self.sendline("date '+%A, %B %d, %Y %T'")
        self.expect_prompt()
        date = re.search(
            r"(\w+,\s\w+\s\d+,\s\d+\s(([0-1]?[0-9])|(2[0-3])):[0-5][0-9]:[0-5][0-9])",
            self.before,
        )
        if date:
            return date.group(0)

    def set_date(self, opt, format):
        """Set the system date and time

        :param format: value to be changed
        :type fromat: str
        :param opt: Option to set the date or time or day
        :type opt: str
        :return: True if set is successful
        :rtype: bool
        """
        self.sendline(f"date {opt} {format}")
        self.expect_prompt()
        return format in self.before

    def get_default_gw(self):
        self.sendline("ip route show | grep default")
        self.expect(f"default via ({ValidIpv4AddressRegex})")
        gw_ip = self.match.group(1)
        self.expect_prompt()
        return gw_ip

    @contextmanager
    def tcpdump_capture(
        self,
        fname: str,
        interface: str = "any",
        additional_args: Optional[str] = None,
    ) -> None:
        """Capture packets from specified interface

        Packet capture using tcpdump utility at a specified interface.

        :param fname: name of the file where packet captures will be stored
        :type fname: str
        :param interface: name of the interface, defaults to "all"
        :type interface: str
        :param additional_args: arguments to tcpdump command, defaults to None
        :type additional_args: Optional[str]
        :yield: process id of tcpdump process
        :rtype: None
        """
        process_id: str = ""
        command_str = f"tcpdump -U -i {interface} -n -w {fname} "
        if additional_args:
            command_str += additional_args

        try:

            self.sudo_sendline(f"{command_str} &")
            self.expect_exact(f"tcpdump: listening on {interface}")
            process_id = re.search(r"(\[\d{1,10}\]\s(\d+))", self.before).group(2)
            yield process_id

        finally:

            # This should always be executed, might kill other tcpdumps[need to agree]
            if process_id:
                self.sudo_sendline(f"kill {process_id}")
                self.expect(self.prompt)
                for _ in range(3):
                    with suppress(pexpect.TIMEOUT):
                        self.sudo_sendline("sync")
                        self.expect(self.prompt)
                        if "Done" in self.before:
                            break

    def tcpdump_read_pcap(
        self,
        fname: str,
        additional_args: Optional[str] = None,
        timeout: int = 30,
        rm_pcap: bool = False,
    ) -> str:
        """Read packet captures from an existing file

        :param fname: name of file to read from
        :type fname: str
        :param additional_args: filter to apply on packet display, defaults to None
        :type additional_args: Optional[str]
        :param timeout: time for tcpdump read command to complete, defaults to 30
        :type timeout: int
        :param rm_pcap: if True remove packet capture file after read, defaults to False
        :type rm_pcap: bool
        :return: console output from the command execution
        :rtype: str
        """

        read_command = f"tcpdump -n -r {fname} "
        if additional_args:
            read_command += additional_args
        self.sudo_sendline(read_command)
        self.expect(self.prompt, timeout=timeout)
        output = self.before
        if "No such file or directory" in output:
            raise FileNotFoundError(
                f"pcap file not found {fname} on device={self.name}"
            )
        if "syntax error in filter expression" in output:
            raise CodeError(
                f"Invalid filters for tcpdump read , review additional_args={additional_args}"
            )
        if rm_pcap:
            self.sudo_sendline(f"rm {fname}")
            self.expect(self.prompt)
        return output

    def tshark_read_pcap(
        self,
        fname: str,
        additional_args: Optional[str] = None,
        timeout: int = 30,
        rm_pcap: bool = False,
    ) -> str:
        """Read packet captures from an existing file

        :param fname: name of the file in which captures are saved
        :type fname: str
        :param additional_args: additional arguments for tshark command to display filtered output, defaults to None
        :type additional_args: Optional[str]
        :param timeout: time out for tshark command to be executed, defaults to 30
        :type timeout: int
        :param rm_pcap: If True remove the packet capture file after reading it, defaults to False
        :type rm_pcap: bool
        :return: return tshark read command console output
        :rtype: str
        """

        read_command = f"tshark -r {fname} "
        if additional_args:
            read_command += additional_args

        self.sendline(read_command)
        self.expect(self.prompt, timeout=timeout)
        output = self.before
        if f'The file "{fname}" doesn\'t exist' in output:
            raise FileNotFoundError(
                f"pcap file not found {fname} on device {self.name}"
            )
        if "was unexpected in this context" in output:
            raise CodeError(
                f"Invalid filters for tshark read , review additional_args={additional_args}"
            )
        if rm_pcap:
            self.sudo_sendline(f"rm {fname}")
            self.expect(self.prompt)
        return output

    def set_default_gw(
        self,
        gateway_address: Union[str, ipaddress.IPv4Address],
        interface: str,
    ) -> None:
        """Set default gateway for the interface.

        :param gateway_address: default gatway ip address.
        :type gateway_address: Union[str, ipaddress.IPv4Address]
        :param interface: interface name to set default gateway on
        :type interface: string
        """
        self.sendline("ip route del default")
        self.expect(self.prompt)
        self.sendline("ip route show default")
        self.expect(self.prompt)
        if self.before.splitlines()[1:]:
            raise CodeError(
                f"Failed to remove existing defualt route {self.before}, unable to proceed with set default gatway command "
            )
        self.sendline(f"route add default gw {gateway_address} dev {interface}")
        self.expect(self.prompt)
        self.sendline("ip route show default")
        self.expect(self.prompt)
        if str(gateway_address) not in self.before.lower():
            raise CodeError(
                f"Failed to add default route, ip route output : {self.before},"
            )
        logger.debug("The route is configured successfully .")

    def download_build(
        self, build: str, source: str, destination: str = "/tftpboot"
    ) -> bool:
        """Download the build from the source to the destination if the build is not already there

        :param build: name of the image file
        :type build: str
        :param source: source address of the build to download
        :type source: str
        :param destination: destination path to which the build should download to, defaults to "/tftpboot"
        :type destination: str, optional
        :raises CodeError: raises the exception if there goes something wrong during file download
        :return: True if the build is present on the destination
        :rtype: bool
        """
        try:
            self.sendline(f"wget -nc {source} -O {destination}/{build}")
            self.expect_prompt()
        except PexpectErrorTimeout as e:
            raise CodeError(
                f"Failed to download the build on {destination} Error: {e}"
            ) from e

        logger.info(f"{build} downloaded as {build}")
        return "saved" in self.before or "already there; not retrieving" in self.before


class LinuxDevice(LinuxInterface, base.BaseDevice):
    """This aggregates the basedevice and its implementation"""

    pass
