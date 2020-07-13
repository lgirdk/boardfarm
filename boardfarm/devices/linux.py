#!/usr/bin/env python3
import binascii
import ipaddress
import os
import re

import pexpect
import six
from boardfarm.exceptions import PexpectErrorTimeout
from boardfarm.lib.regexlib import (
    AllValidIpv6AddressesRegex,
    InterfaceIPv6_AddressRegex,
    LinuxMacFormat,
    ValidIpv4AddressRegex,
)

from . import base

BFT_DEBUG = "BFT_DEBUG" in os.environ


class LinuxDevice(base.BaseDevice):
    """Linux implementations."""

    tftp_dir = "/tftpboot"

    def check_status(self):
        """Check the state of the device."""
        print("\n\nRunning check_status() on %s" % self.name)
        self.sendline(
            "\ncat /proc/version; cat /proc/uptime; ip a; ifconfig; route -n; route -6 -n"
        )
        self.expect_exact(
            "cat /proc/version; cat /proc/uptime; ip a; ifconfig; route -n; route -6 -n"
        )
        self.expect("version", timeout=5)
        self.expect(self.prompt, timeout=5)

    def get_interface_ipaddr(self, interface):
        """Get ipv4 address of interface."""
        self.sendline("\nifconfig %s" % interface)
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
        ipaddr = self.match.group(1)
        ipv4address = str(ipaddress.IPv4Address(six.text_type(ipaddr)))
        self.expect(self.prompt)
        print("ifconfig {} IPV4 {}".format(interface, ipv4address))
        return ipv4address

    def get_interface_ip6addr(self, interface):
        """Get ipv6 address of interface."""
        # to minimise the chance of getting stray ipv6 addresses from the pexpect
        # ".before" buffer tagging with bft_inet6 the lines of OUR command output that
        # have an ipv6 address (so we can pick them later)
        # REASON: on some linux based embedded devices the console can be VERY verbose
        # and spurious debug messages can have ipv6 addresses in it

        regex = [AllValidIpv6AddressesRegex, InterfaceIPv6_AddressRegex]
        self.expect(pexpect.TIMEOUT, timeout=0.5)
        self.before = ""

        self.sendline("ifconfig %s | sed 's/inet6 /bft_inet6 /'" % interface)
        self.expect(self.prompt)
        print(self.before)

        ips = re.compile("|".join(regex), re.M | re.U).findall(self.before)
        for i in ips:
            try:
                # we use IPv6Interface for convenience (any exception will be ignored)
                ipv6_iface = ipaddress.IPv6Interface(six.text_type(i))
                if ipv6_iface and ipv6_iface.is_global:
                    print("ifconfig {} IPV6 {}".format(interface, str(ipv6_iface.ip)))
                    return str(ipv6_iface.ip)
            except Exception:
                continue
        print("Failed ifconfig {} IPV6 {}".format(interface, ips))
        raise Exception("Did not find non-link-local ipv6 address")

    def get_interface_macaddr(self, interface):
        """Get the interface macaddress."""
        self.sendline("cat /sys/class/net/{}/address | \\".format(interface))
        self.sendline("awk '{print \"bft_macaddr : \"$1}'")
        self.expect("bft_macaddr : {}".format(LinuxMacFormat))
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
        self.sudo_sendline(
            "ifconfig {} {} netmask {} up".format(interface, fix_ip, fix_mark)
        )
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
        self.sudo_sendline("dhclient -r {!s}".format(interface))
        self.expect(self.prompt)

    def check_access_url(self, url, source_ip=None):
        """Check source_ip can access url.

        Name: check_access_url
        Purpose: check source_ip can access url
        Input:  url, source_ip
        Output: True or False
        """
        if source_ip is None:
            self.sendline("curl -I {!s}".format(url))
        else:
            self.sendline("curl --interface {!s} -I {!s}".format(source_ip, url))
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
        self, ping_ip, ping_count=4, ping_interface=None, options="", timetorun=None
    ):
        """Check ping from any device."""
        timeout = 50
        basic_cmd = "ping -c {} {}".format(ping_count, ping_ip)

        if timetorun:
            basic_cmd = "timeout {} ping {} {}".format(timetorun, ping_ip, options)
            timeout = int(timetorun) + 10
        elif ping_interface:
            basic_cmd += " -I {} {}".format(ping_interface, options)
        else:
            basic_cmd += " {}".format(options)
        self.sendline(basic_cmd)
        self.expect(self.prompt, timeout=timeout)

        if timetorun:
            # Validation can be added - future note
            return True
        else:
            match = re.search(
                "%s packets transmitted, %s received, 0%% packet loss"
                % (ping_count, ping_count),
                self.before,
            )
            if match:
                return True
            else:
                return False

    def traceroute(self, host_ip, version="", options="", timeout=60):
        """Traceroute returns the route that packets take to a network host."""
        try:
            self.sendline("traceroute%s %s %s" % (version, options, host_ip))
            self.expect_exact("traceroute%s %s %s" % (version, options, host_ip))
            self.expect_prompt(timeout=timeout)
            return self.before
        except pexpect.TIMEOUT:
            self.sendcontrol("c")
            self.expect(self.prompt)
            return None

    def is_link_up(self, interface, pattern="BROADCAST,MULTICAST,UP"):
        """Check the interface status."""
        self.sendline("ip link show %s" % interface)
        self.expect(self.prompt)
        link_state = self.before
        match = re.search(pattern, link_state)
        if match:
            return match.group(0)
        else:
            return None

    def set_link_state(self, interface, state):
        """Set the interface status."""
        self.sudo_sendline("ip link set %s %s" % (interface, state))
        self.expect(self.prompt)

    def add_new_user(self, id, pwd):
        """Create new login ID. But check if already exists."""
        self.sendline("\nadduser %s" % id)
        try:
            self.expect_exact("Enter new UNIX password", timeout=5)
            self.sendline("%s" % pwd)
            self.expect_exact("Retype new UNIX password")
            self.sendline("%s" % pwd)
            self.expect_exact("Full Name []")
            self.sendline("%s" % id)
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
            self.sendline("usermod -aG sudo %s" % id)
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
            with gzip.GzipFile(fileobj=out, mode="w") as fo:
                fo.write(string_)
            return out.getvalue()

        with open(src, mode="rb") as file:
            bin_file = binascii.hexlify(gzip_str(file.read()))
        if dst is None:
            dst = self.tftp_dir + "/" + os.path.basename(src)
        print("Copying %s to %s" % (src, dst))
        saved_logfile_read = self.logfile_read
        self.logfile_read = None
        self.sendline(
            """cat << EOFEOFEOFEOF | xxd -r -p | gunzip > %s
%s
EOFEOFEOFEOF"""
            % (dst, bin_file)
        )
        self.expect(self.prompt)
        self.sendline("ls %s" % dst)
        self.expect_exact("ls %s" % dst)
        i = self.expect(
            ["ls: cannot access %s: No such file or directory" % dst] + self.prompt
        )
        if i == 0:
            raise Exception("Failed to copy file")
        self.logfile_read = saved_logfile_read

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
        super(LinuxDevice, self).sendline(cmd)

    def set_cli_size(self, columns):
        """Set the terminal colums value."""
        self.sendline("stty columns %s" % str(columns))
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
                print(e)
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
                    print("waiting for wan/lan ipaddr")
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
            "external: eth1",
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
            self.sendline("sed -i 's/^Port 8888/Port 8080/' %s" % f)
            self.expect(self.prompt)
            self.sendline("sed 's/#Allow/Allow/g' -i %s" % f)
            self.expect(self.prompt)
            self.sendline("sed '/Listen/d' -i %s" % f)
            self.expect(self.prompt)
            self.sendline("sed '/ConnectPort/d' -i %s" % f)
            self.expect(self.prompt)
            self.sendline('echo "Listen 0.0.0.0" >> %s' % f)
            self.expect(self.prompt)
            self.sendline('echo "Listen ::" >> %s' % f)
            self.expect(self.prompt)
        self.sendline("/etc/init.d/tinyproxy restart")
        self.expect("Restarting")
        self.expect(self.prompt)
        self.sendline("sleep 3; ps auxwww")
        self.expect("/usr/sbin/tinyproxy")
        self.expect_prompt()

    def take_lock(self, file_lock, fd=9, timeout=200):
        """Take a file lock on file_lock."""
        self.sendline("exec %s>%s" % (fd, file_lock))
        self.expect(self.prompt)
        self.sendline("flock -x %s" % fd)
        self.expect(self.prompt, timeout=timeout)

    def release_lock(self, file_lock, fd=9):
        """Releases a lock taken."""
        self.sendline("flock -u %s" % fd)
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
            web_addr = "{}://{}:{}".format(protocol, host_ip, str(port))
        else:
            web_addr = "{}://{}".format(protocol, host_ip)
        command = "curl {} {}".format(options, web_addr)
        self.sendline(command)
        index = self.expect(
            ["Connected to"]
            + ["DOCTYPE html PUBLIC"]
            + ["Connection timed out"]
            + ["Failed to connect to"]
            + self.prompt,
            timeout=100,
        )
        try:
            self.expect_prompt()
        except pexpect.exceptions.TIMEOUT:
            self.sendcontrol("c")
            self.expect_prompt()
        return index in [0, 1]

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
