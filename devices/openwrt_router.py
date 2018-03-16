# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import atexit
import os
import os.path
import random
import signal
import socket
import sys
import urllib2
import pexpect
import base
from datetime import datetime
import ipaddress

import power
import common
import connection_decider

class OpenWrtRouter(base.BaseDevice):
    '''
    Args:
      model: Examples include "ap148" and "ap135".
      conn_cmd: Command to connect to device such as "ssh -p 3003 root@10.0.0.202"
      power_ip: IP Address of power unit to which this device is connected
      power_outlet: Outlet # this device is connected
    '''
    conn_list = None
    consoles = []

    prompt = ['root\\@.*:.*#', '/ # ', '@R7500:/# ']
    uprompt = ['ath>', '\(IPQ\) #', 'ar7240>', '\(IPQ40xx\)']
    uboot_eth = "eth0"
    linux_booted = False
    saveenv_safe = True
    lan_gmac_iface = "eth1"
    lan_iface = "br-lan"
    wan_iface = "eth0"
    tftp_server_int = None

    uboot_net_delay = 30

    routing = True
    lan_network = ipaddress.IPv4Network(u"192.168.1.0/24")
    lan_gateway = ipaddress.IPv4Address(u"192.168.1.1")

    def __init__(self,
                 model,
                 conn_cmd,
                 power_ip,
                 power_outlet,
                 output=sys.stdout,
                 password='bigfoot1',
                 web_proxy=None,
                 tftp_server=None,
                 tftp_username=None,
                 tftp_password=None,
                 tftp_port=None,
                 connection_type=None,
                 power_username=None,
                 power_password=None,
                 **kwargs):

        self.consoles.append(self)

        if type(conn_cmd) is list:
            self.conn_list = conn_cmd
            conn_cmd = self.conn_list[0]

        if connection_type is None:
            print("\nWARNING: Unknown connection type using ser2net\n")
            connection_type = "ser2net"

        self.connection = connection_decider.connection(connection_type, device=self, conn_cmd=conn_cmd, **kwargs)
        self.connection.connect()
        self.logfile_read = output

        self.power = power.get_power_device(power_ip, outlet=power_outlet, username=power_username, password=power_password)
        self.model = model
        self.web_proxy = web_proxy
        if tftp_server:
            try:
                self.tftp_server = socket.gethostbyname(tftp_server)
                if tftp_username:
                    self.tftp_username = tftp_username
                if tftp_password:
                    self.tftp_password = tftp_password
                if tftp_port:
                    self.tftp_port = tftp_port
            except:
                pass
        else:
            self.tftp_server = None
        atexit.register(self.kill_console_at_exit)

    def reset(self, break_into_uboot=False):
        '''Power-cycle this device.'''
        if not break_into_uboot:
            self.power.reset()
            return
        for attempt in range(3):
            try:
                self.power.reset()
                self.expect('U-Boot', timeout=30)
                self.expect('Hit any key ')
                self.sendline('\n\n\n\n\n\n\n') # try really hard
                self.expect(self.uprompt, timeout=4)
                # Confirm we are in uboot by typing any command.
                # If we weren't in uboot, we wouldn't see the command
                # that we type.
                self.sendline('echo FOO')
                self.expect('echo FOO', timeout=4)
                self.expect(self.uprompt, timeout=4)
                return
            except Exception as e:
                print(e)
                print("\nWe appeared to have failed to break into U-Boot...")

    def get_ip_addr(self, interface):
        '''Return IP Address for given interface.'''
        self.sendline("\nifconfig %s" % interface)
        self.expect('addr:(\d{1,3}.\d{1,3}.\d{1,3}.\d{1,3}).*(Bcast|P-t-P):', timeout=5)
        ipaddr = self.match.group(1)
        self.expect(self.prompt)
        return ipaddr

    def get_seconds_uptime(self):
        '''Return seconds since last reboot. Stored in /proc/uptime'''
        self.sendcontrol('c')
        self.expect(self.prompt)
        self.sendline('\ncat /proc/uptime')
        self.expect('(\d+).(\d+).*\r\n')
        seconds_up = int(self.match.group(1))
        self.expect(self.prompt)
        return seconds_up

    def get_memfree(self):
        '''Return the kB of free memory.'''
        # free pagecache, dentries and inodes for higher accuracy
        self.sendline('\nsync; echo 3 > /proc/sys/vm/drop_caches')
        self.expect('drop_caches')
        self.expect(self.prompt)
        self.sendline('cat /proc/meminfo | head -2')
        self.expect('MemFree:\s+(\d+) kB')
        memFree = self.match.group(1)
        self.expect(self.prompt)
        return int(memFree)

    def get_file(self, fname, lan_ip="192.168.1.1"):
        '''
        OpenWrt routers have a webserver, so we use that to download
        the file via a webproxy (e.g. a device on the board's LAN).
        '''
        if not self.web_proxy:
            raise Exception('No web proxy defined to access board.')
        url = 'http://%s/TEMP' % lan_ip
        self.sendline("\nchmod a+r %s" % fname)
        self.expect('chmod ')
        self.expect(self.prompt)
        self.sendline("ln -sf %s /www/TEMP" % fname)
        self.expect(self.prompt)
        proxy = urllib2.ProxyHandler({'http': self.web_proxy+':8080'})
        opener = urllib2.build_opener(proxy)
        urllib2.install_opener(opener)
        print("\nAttempting download of %s via proxy %s" % (url, self.web_proxy+':8080'))
        return urllib2.urlopen(url, timeout=30)

    def tftp_get_file(self, host, filename, timeout=30):
        '''Download file from tftp server.'''
        self.sendline("tftp-hpa %s" % host)
        self.expect("tftp>")
        self.sendline("get %s" % filename)
        t = timeout
        self.expect("tftp>", timeout=t)
        self.sendline("q")
        self.expect(self.prompt)
        self.sendline("ls `basename %s`" % filename)
        new_fname = os.path.basename(filename)
        self.expect("%s" % new_fname)
        self.expect(self.prompt)
        return new_fname

    def tftp_get_file_uboot(self, loadaddr, filename, timeout=60):
        '''Within u-boot, download file from tftp server.'''
        for attempt in range(3):
            try:
                self.sendline("tftpboot %s %s" % (loadaddr, filename))
                self.expect_exact("tftpboot %s %s" % (loadaddr, filename))
                i = self.expect(['Bytes transferred = (\d+) (.* hex)'] + self.uprompt, timeout=timeout)
                if i != 0:
                    continue
                ret = int(self.match.group(1))
                self.expect(self.uprompt)
                return ret
            except:
                print("\nTFTP failed, let us try that again")
                self.sendcontrol('c')
                self.expect(self.uprompt)
        raise Exception("TFTP failed, try rebooting the board.")

    def prepare_file(self, fname):
        '''Copy file to tftp server, so that it it available to tftp
        to the board itself.'''
        if fname.startswith("http://") or fname.startswith("https://"):
            return common.download_from_web(fname, self.tftp_server, self.tftp_username, self.tftp_password, self.tftp_port)
        else:
            return common.scp_to_tftp_server(os.path.abspath(fname), self.tftp_server, self.tftp_username, self.tftp_password, self.tftp_port)

    def install_package(self, fname):
        '''Install OpenWrt package (opkg).'''
        target_file = fname.replace('\\', '/').split('/')[-1]
        new_fname = self.prepare_file(fname)
        local_file = self.tftp_get_file(self.tftp_server, new_fname, timeout=60)
        # opkg requires a correct file name
        self.sendline("mv %s %s" % (local_file, target_file))
        self.expect(self.prompt)
        self.sendline("opkg install --force-downgrade %s" % target_file)
        self.expect(['Installing', 'Upgrading', 'Downgrading'])
        self.expect(self.prompt, timeout=60)
        self.sendline("rm -f /%s" % target_file)
        self.expect(self.prompt)

    def randomMAC(self):
        mac = [0x00, 0x16, 0x3e,
               random.randint(0x00, 0x7f),
               random.randint(0x00, 0xff),
               random.randint(0x00, 0xff)]
        return ':'.join(map(lambda x: "%02x" % x, mac))

    def check_memory_addresses(self):
        '''Check/set memory addresses and size for proper flashing.'''
        pass

    def flash_uboot(self, uboot):
        raise Exception('Code not written for flash_uboot for this board type, %s' % self.model)

    def flash_rootfs(self, ROOTFS):
        raise Exception('Code not written for flash_rootfs for this board type, %s' % self.model)

    def flash_linux(self, KERNEL):
        raise Exception('Code not written for flash_linux for this board type, %s.' % self.model)

    def flash_meta(self, META_BUILD):
        raise Exception('Code not written for flash_meta for this board type, %s.' % self.model)

    def prepare_nfsroot(self, NFSROOT):
        raise Exception('Code not written for prepare_nfsroot for this board type, %s.' % self.model)

    def wait_for_boot(self):
        '''
        Break into U-Boot. Check memory locations and sizes, and set
        variables needed for flashing.
        '''
        # Try to break into uboot
        for attempt in range(4):
            try:
                self.expect('U-Boot', timeout=30)
                i = self.expect(['Hit any key ', 'gpio 17 value 1'] + self.uprompt)
                if i == 1:
                    print("\n\nWARN: possibly need to hold down reset button to break into U-Boot\n\n")
                    self.expect('Hit any key ')

                self.sendline('\n\n\n\n\n\n\n') # try really hard
                i = self.expect(['httpd'] + self.uprompt, timeout=4)
                if i == 0:
                    self.sendcontrol('c')
                self.sendline('echo FOO')
                self.expect('echo FOO')
                self.expect('FOO')
                self.expect(self.uprompt, timeout=4)
                break
            except:
                print('\n\nFailed to break into uboot, try again.')
                self.reset()
        else:
            # Tried too many times without success
            print('\nUnable to break into U-Boot, test will likely fail')

        self.check_memory_addresses()

        # save env first, so CRC is OK for later tests
        self.sendline("saveenv")
        self.expect(["Writing to Nand... done", "Protected 1 sectors", "Saving Environment to NAND...", 'Saving Environment to FAT...'])
        self.expect(self.uprompt)

    def kill_console_at_exit(self):
        self.kill(signal.SIGKILL)

    def wait_for_network(self):
        '''Wait until network interfaces have IP Addresses.'''
        for interface in [self.wan_iface, self.lan_iface]:
            for i in range(5):
                try:
                    if interface is not None:
                        ipaddr = self.get_interface_ipaddr(interface).strip()
                        if not ipaddr:
                            continue
                        self.sendline("route -n")
                        self.expect(interface)
                        self.expect(self.prompt)
                except pexpect.TIMEOUT:
                    print("waiting for wan/lan ipaddr")
                else:
                    break

    def network_restart(self):
        '''Restart networking.'''
        self.sendline('\nifconfig')
        self.expect('HWaddr', timeout=10)
        self.expect(self.prompt)
        self.sendline('/etc/init.d/network restart')
        self.expect(self.prompt, timeout=40)
        self.sendline('ifconfig')
        self.expect(self.prompt)
        self.wait_for_network()

    def firewall_restart(self):
        '''Restart the firewall. Return how long it took.'''
        start = datetime.now()
        self.sendline('/etc/init.d/firewall restart')
        self.expect_exact(["Loading redirects", "* Running script '/usr/share/miniupnpd/firewall.include'", "Running script '/etc/firewall.user'"])
        if 'StreamBoost' in self.before:
            print("test_msg: Sleeping for Streamboost")
            self.expect(pexpect.TIMEOUT, timeout=45)
        else:
            self.expect(pexpect.TIMEOUT, timeout=15)
        self.expect(self.prompt, timeout=80)
        return int((datetime.now() - start).seconds)

    def get_wan_iface(self):
        '''Return name of WAN interface.'''
        self.sendline('\nuci show network.wan.ifname')
        self.expect("wan.ifname='?([a-zA-Z0-9\.-]*)'?\r\n", timeout=5)
        return self.match.group(1)

    def get_wan_proto(self):
        '''Return protocol of WAN interface, e.g. dhcp.'''
        self.sendline('\nuci show network.wan.proto')
        self.expect("wan.proto='?([a-zA-Z0-9\.-]*)'?\r\n", timeout=5)
        return self.match.group(1)

    def setup_uboot_network(self, tftp_server=None):
        if self.tftp_server_int is None:
            if tftp_server is None:
                raise Exception("Error in TFTP server configuration")
            self.tftp_server_int = tftp_server
        '''Within U-boot, request IP Address,
        set server IP, and other networking tasks.'''
        # Use standard eth1 address of wan-side computer
        self.sendline('setenv autoload no')
        self.expect(self.uprompt)
        self.sendline('setenv ethact %s' % self.uboot_eth)
        self.expect(self.uprompt)
        self.expect(pexpect.TIMEOUT, timeout=self.uboot_net_delay) # running dhcp too soon causes hang
        self.sendline('dhcp')
        i = self.expect(['Unknown command', 'DHCP client bound to address'], timeout=60)
        self.expect(self.uprompt)
        if i == 0:
            self.sendline('setenv ipaddr 192.168.0.2')
            self.expect(self.uprompt)
        self.sendline('setenv serverip %s' % self.tftp_server_int)
        self.expect(self.uprompt)
        if self.tftp_server_int:
            #interfaces=['eth1','eth0']
            passed = False
            for attempt in range(5):
                try:
                    self.sendcontrol('c')
                    self.expect('<INTERRUPT>')
                    self.expect(self.uprompt)
                    self.sendline("ping $serverip")
                    self.expect("host %s is alive" % self.tftp_server_int)
                    self.expect(self.uprompt)
                    passed = True
                    break
                except:
                    print("ping failed, trying again")
                    # Try other interface
                    self.sendcontrol('c')
                    self.expect('<INTERRUPT>')
                    self.expect(self.uprompt)
                    #self.sendline('setenv ethact %s' % (interfaces[attempt%2]))
                    #self.expect(self.uprompt)
                    self.sendline('dhcp')
                    self.expect('DHCP client bound to address', timeout=60)
                    self.expect(self.uprompt)
                self.expect(pexpect.TIMEOUT, timeout=1)
            assert passed
        self.sendline('setenv dumpdir crashdump')
        if self.saveenv_safe:
            self.expect(self.uprompt)
            self.sendline('saveenv')
        self.expect(self.uprompt)

    def boot_linux(self, rootfs=None, bootargs=""):
        print("\nWARNING: We don't know how to boot this board to linux "
              "please write the code to do so.")

    def wait_for_linux(self):
        '''Verify Linux starts up.'''
        i = self.expect(['Reset Button Push down', 'Linux version', 'Booting Linux', 'Starting kernel ...', 'Kernel command line specified:'], timeout=45)
        if i == 0:
            self.expect('httpd')
            self.sendcontrol('c')
            self.expect(self.uprompt)
            self.sendline('boot')
        i = self.expect(['U-Boot', 'login:', 'Please press Enter to activate this console'] + self.prompt, timeout=150)
        if i == 0:
            raise Exception('U-Boot came back when booting kernel')
        elif i == 1:
            self.sendline('root')
            if 0 == self.expect(['assword:'] + self.prompt):
                self.sendline('password')
                self.expect(self.prompt)

        # Give things time to start or crash on their own.
        # Some things, like wifi, take a while.
        self.expect(pexpect.TIMEOUT, timeout=40)
        self.sendline('\r')
        self.expect(self.prompt)
        self.sendline('uname -a')
        self.expect('Linux ')
        self.expect(self.prompt)

    def config_wan_proto(self, proto):
        '''Set protocol for WAN interface.'''
        if "dhcp" in proto:
            if self.get_wan_proto() != "dhcp":
                self.sendline("uci set network.wan.proto=dhcp")
                self.sendline("uci commit")
                self.expect(self.prompt)
                self.network_restart()
                self.expect(pexpect.TIMEOUT, timeout=10)
        if "pppoe" in proto:
            self.wan_iface = "pppoe-wan"
            if self.get_wan_proto() != "pppoe":
                self.sendline("uci set network.wan.proto=pppoe")
                self.sendline("uci commit")
                self.expect(self.prompt)
                self.network_restart()
                self.expect(pexpect.TIMEOUT, timeout=10)

    def uci_allow_wan_http(self, lan_ip="192.168.1.1"):
        '''Allow access to webgui from devices on WAN interface.'''
        self.uci_forward_traffic_redirect("tcp", "80", lan_ip)

    def uci_allow_wan_ssh(self, lan_ip="192.168.1.1"):
        self.uci_forward_traffic_redirect("tcp", "22", lan_ip)

    def uci_forward_traffic_redirect(self, tcp_udp, port_wan, ip_lan):
        self.sendline('uci add firewall redirect')
        self.sendline('uci set firewall.@redirect[-1].src=wan')
        self.sendline('uci set firewall.@redirect[-1].src_dport=%s' % port_wan)
        self.sendline('uci set firewall.@redirect[-1].proto=%s' % tcp_udp)
        self.sendline('uci set firewall.@redirect[-1].dest_ip=%s' % ip_lan)
        self.sendline('uci commit firewall')
        self.firewall_restart()

    def uci_forward_traffic_rule(self, tcp_udp, port, ip, target="ACCEPT"):
        self.sendline('uci add firewall rule')
        self.sendline('uci set firewall.@rule[-1].src=wan')
        self.sendline('uci set firewall.@rule[-1].proto=%s' % tcp_udp)
        self.sendline('uci set firewall.@rule[-1].dest=lan')
        self.sendline('uci set firewall.@rule[-1].dest_ip=%s' % ip)
        self.sendline('uci set firewall.@rule[-1].dest_port=%s' % port)
        self.sendline('uci set firewall.@rule[-1].target=%s' % target)
        self.sendline('uci commit firewall')
        self.firewall_restart()

    def wait_for_mounts(self):
        # wait for overlay to finish mounting
	for i in range(5):
	    try:
		board.sendline('mount')
		board.expect_exact('overlayfs:/overlay on / type overlay', timeout=15)
		board.expect(prompt)
		break
	    except:
		pass
	else:
		print("WARN: Overlay still not mounted")


if __name__ == '__main__':
    # Example use
    board = OpenWrtRouter('ap148-beeliner',
                          conn_cmd='telnet 10.0.0.146 6003',
                          power_ip='10.0.0.218',
                          power_outlet='9',
                          web_proxy="10.0.0.66:8080")
    board.sendline('\nuname -a')
    board.expect('Linux')
    board.expect('root@[^ ]+')
    #board.reset()
    #board.expect('U-Boot')
    # Example downloading a file from the board
    remote_fname = '/tmp/dhcp.leases'
    local_fname = '/tmp/dhcp.leases'
    with open(local_fname, 'wb') as local_file:
        local_file.write(board.get_file(remote_fname).read())
        print("\nCreated %s" % local_fname)
