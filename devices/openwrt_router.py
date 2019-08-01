# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import atexit
import os
import os.path
import signal
import socket
import sys
import urllib2
import pexpect
import linux
from datetime import datetime
import ipaddress
import re

import power
import common
import connection_decider
from common import print_bold

class OpenWrtRouter(linux.LinuxDevice):
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
    flash_meta_booted = False
    has_cmts = False
    cdrouter_config = None

    uboot_net_delay = 30

    routing = True
    lan_network = ipaddress.IPv4Network(u"192.168.1.0/24")
    lan_gateway = ipaddress.IPv4Address(u"192.168.1.1")
    tmpdir = "/tmp"
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
                 config=None,
                 **kwargs):

        self.config = config
        self.consoles = [self]
        self.start = kwargs['start']

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

    def get_file(self, fname, lan_ip=lan_gateway):
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
                self.sendline('help')
                self.expect_exact('help')
                self.expect(self.uprompt)
                if 'tftpboot' in self.before:
                    cmd = 'tftpboot'
                else:
                    cmd = 'tftp'
                self.sendline("%s %s %s" % (cmd, loadaddr, filename))
                self.expect_exact("%s %s %s" % (cmd, loadaddr, filename))
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

    def prepare_file(self, fname, tserver=None, tusername=None, tpassword=None, tport=None):
        '''Copy file to tftp server, so that it it available to tftp
        to the board itself.'''
        if tserver is None:
            tserver = self.tftp_server
        if tusername is None:
            tusername = self.tftp_username
        if tpassword is None:
            tpassword = self.tftp_password
        if tport is None:
            tport = self.tftp_port

        if fname.startswith("http://") or fname.startswith("https://"):
            return common.download_from_web(fname, tserver, tusername, tpassword, tport)
        else:
            return common.scp_to_tftp_server(os.path.abspath(fname), tserver, tusername, tpassword, tport)

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

    def enable_mgmt_gui(self):
        '''Allow access to webgui from devices on WAN interface '''
        self.uci_allow_wan_http(self.lan_gateway)

    def enable_ssh(self):
        '''Allow ssh on wan interface '''
        self.uci_allow_wan_ssh(self.lan_gateway)

    def uci_allow_wan_http(self, lan_ip="192.168.1.1"):
        '''Allow access to webgui from devices on WAN interface.'''
        self.uci_forward_traffic_redirect("tcp", "80", lan_ip)

    def uci_allow_wan_ssh(self, lan_ip="192.168.1.1"):
        self.uci_forward_traffic_redirect("tcp", "22", lan_ip)

    def uci_allow_wan_https(self):
        '''Allow access to webgui from devices on WAN interface.'''
        self.uci_forward_traffic_redirect("tcp", "443", "192.168.1.1")

    def uci_forward_traffic_redirect(self, tcp_udp, port_wan, ip_lan):
        self.sendline('uci add firewall redirect')
        self.expect(self.prompt)
        self.sendline('uci set firewall.@redirect[-1].src=wan')
        self.expect(self.prompt)
        self.sendline('uci set firewall.@redirect[-1].src_dport=%s' % port_wan)
        self.expect(self.prompt)
        self.sendline('uci set firewall.@redirect[-1].proto=%s' % tcp_udp)
        self.expect(self.prompt)
        self.sendline('uci set firewall.@redirect[-1].dest=lan')
        self.expect(self.prompt)
        self.sendline('uci set firewall.@redirect[-1].dest_ip=%s' % ip_lan)
        self.expect(self.prompt)
        self.sendline('uci commit firewall')
        self.expect(self.prompt)
        self.firewall_restart()

    def uci_forward_traffic_rule(self, tcp_udp, port, ip, target="ACCEPT"):
        self.sendline('uci add firewall rule')
        self.expect(self.prompt)
        self.sendline('uci set firewall.@rule[-1].src=wan')
        self.expect(self.prompt)
        self.sendline('uci set firewall.@rule[-1].proto=%s' % tcp_udp)
        self.expect(self.prompt)
        self.sendline('uci set firewall.@rule[-1].dest=lan')
        self.expect(self.prompt)
        self.sendline('uci set firewall.@rule[-1].dest_ip=%s' % ip)
        self.expect(self.prompt)
        self.sendline('uci set firewall.@rule[-1].dest_port=%s' % port)
        self.expect(self.prompt)
        self.sendline('uci set firewall.@rule[-1].target=%s' % target)
        self.expect(self.prompt)
        self.sendline('uci commit firewall')
        self.expect(self.prompt)
        self.firewall_restart()

    def wait_for_mounts(self):
        '''wait for overlay to finish mounting'''
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

    def get_dns_server(self):
        '''Getting dns server ip address '''
        return "%s" %self.lan_gateway

    def get_user_id(self, user_id):
        self.sendline('cat /etc/passwd | grep -w ' + user_id)
        idx = self.expect([user_id] + self.prompt)
        if idx == 0:
            self.expect(self.prompt)
        return 0 == idx

    def get_pp_dev(self):
        return self

    def collect_stats(self, stats=[]):
        pp = self.get_pp_dev()
        self.stats = []
        self.failed_stats = {}

        for stat in stats:
            if 'mpstat' in stat:
                for i in range(5):
                    try:
                        pp.sendcontrol('c')
                        pp.sendline("kill `ps | grep mpstat | grep -v grep | awk '{print $1}'`")
                        pp.expect_exact("kill `ps | grep mpstat | grep -v grep | awk '{print $1}'`")
                        pp.expect(pp.prompt)
                        break
                    except:
                        pp.sendcontrol('d')
                        pp = self.get_pp_dev()
                        if i == 4:
                            print_bold("FAILED TO KILL MPSTAT!")
                            pp.sendcontrol('c')
                        pass

                pp.sendline('mpstat -P ALL 5  > %s/mpstat &' % self.tmpdir)
                if 0 == pp.expect(['mpstat: not found'] + pp.prompt):
                    self.failed_stats['mpstat'] = float('nan')
                    continue
                elif 0 == pp.expect(['mpstat: not found', pexpect.TIMEOUT], timeout=4):
                    self.failed_stats['mpstat'] = float('nan')
                    continue

                pp.sendline('ps | grep mpstat')

            self.stats.append(stat)

    def parse_stats(self, dict_to_log={}):
        pp = self.get_pp_dev()

        if 'mpstat' in self.stats:
            pp.sendline('ps | grep mpstat')
            pp.expect_exact('ps | grep mpstat')
            if 0 == pp.expect([pexpect.TIMEOUT, 'mpstat -P ALL 5'], timeout=5):
                self.failed_stats['mpstat'] = float('nan')
                self.stats.remove('mpstat')

        idx = 0
        for not_used in range(len(self.stats)):
            pp.sendline('fg')
            pp.expect(self.stats)
            if 'mpstat' in pp.match.group():
                pp.sendcontrol('c')
                pp.expect(pp.prompt)
                pp.sendline('cat %s/mpstat' % self.tmpdir)
                pp.expect(['cat %s/mpstat' % self.tmpdir, pexpect.TIMEOUT])

                idle_vals = []
                start = datetime.now()
                while 0 == pp.expect(['all(\s+\d+\.\d{2}){9}\r\n', pexpect.TIMEOUT] + pp.prompt):
                    idle_vals.append(float(pp.match.group().strip().split(' ')[-1]))
                    if (datetime.now() - start).seconds > 60:
                        self.touch()

                if len(idle_vals) != 0:
                    avg_cpu_usage = 100 - sum(idle_vals)  / len(idle_vals)
                    dict_to_log['mpstat'] = avg_cpu_usage
                else:
                    dict_to_log['mpstat'] = 0

                pp.sendline('rm %s/mpstat' % self.tmpdir)
                pp.expect([pexpect.TIMEOUT] + pp.prompt)

                idx += 1

        # TODO: verify we got 'em all
        if idx != len(self.stats):
            print("WARN: did not match all stats collected!")

        dict_to_log.update(self.failed_stats)

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
