# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import sys
import time
import pexpect
import linux
import atexit
import os
import ipaddress

from termcolor import colored, cprint

class DebianBox(linux.LinuxDevice):
    '''
    A linux machine running an ssh server.
    '''

    model = ('debian')
    prompt = ['root\\@.*:.*#', '/ # ', ".*:~ #" ]
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
    tftp_dir = '/tftpboot'
    mgmt_dns = None

    iface_dut = "eth1"
    gw = None

    # TODO: does this need to be calculated?
    gwv6 = None
    ipv6_prefix = 64

    def __init__(self,
                 *args,
                 **kwargs):
        self.args = args
        self.kwargs = kwargs
        name = kwargs.pop('name', None)
        ipaddr = kwargs.pop('ipaddr', None)
        color = kwargs.pop('color', 'black')
        username = kwargs.pop('username', 'root')
        password = kwargs.pop('password', 'bigfoot1')
        port = kwargs.pop('port', '22')
        output = kwargs.pop('output', sys.stdout)
        reboot = kwargs.pop('reboot', False)
        location = kwargs.pop('location', None)
        pre_cmd_host = kwargs.pop('pre_cmd_host', None)
        cmd = kwargs.pop('cmd', None)
        post_cmd_host = kwargs.pop('post_cmd_host', None)
        post_cmd = kwargs.pop('post_cmd', None)
        cleanup_cmd = kwargs.pop('cleanup_cmd', None)
        env = kwargs.pop('env', None)
        lan_network = kwargs.pop('lan_network', ipaddress.IPv4Network(u"192.168.1.0/24"))
        lan_gateway = kwargs.pop('lan_gateway', ipaddress.IPv4Address(u"192.168.1.1"))

        self.http_proxy = kwargs.pop('http_proxy', None)

        if pre_cmd_host is not None:
            sys.stdout.write("\tRunning pre_cmd_host.... ")
            sys.stdout.flush()
            phc = pexpect.spawn(command='bash', args=['-c', pre_cmd_host], env=env)
            phc.expect(pexpect.EOF, timeout=120)
            print("\tpre_cmd_host done")

        if ipaddr is not None:
            pexpect.spawn.__init__(self,
                                   command="ssh",
                                   args=['%s@%s' % (username, ipaddr),
                                         '-p', port,
                                         '-o', 'StrictHostKeyChecking=no',
                                         '-o', 'UserKnownHostsFile=/dev/null',
                                         '-o', 'ServerAliveInterval=60',
                                         '-o', 'ServerAliveCountMax=5'])

            self.ipaddr = ipaddr

        if cleanup_cmd is not None:
            self.cleanup_cmd = cleanup_cmd
            atexit.register(self.run_cleanup_cmd)

        if cmd is not None:
            sys.stdout.write("\tRunning cmd.... ")
            sys.stdout.flush()
            pexpect.spawn.__init__(self, command="bash", args=['-c', cmd], env=env)
            self.ipaddr = None
            print("\tcmd done")

        self.name = name
        self.color = color
        self.output = output
        self.username = username
        if username != "root":
            self.prompt.append('%s\\@.*:.*$' % username)
        self.password = password
        self.port = port
        self.location = location
        self.env=env
        self.lan_network = lan_network
        self.lan_gateway = lan_gateway
        self.tftp_device = self


        # we need to pick a non-conflicting private network here
        # also we want it to be consistant and not random for a particular
        # board
        if self.gw is None:
            if (lan_gateway - lan_network.num_addresses).is_private:
                self.gw = lan_gateway - lan_network.num_addresses
            else:
                self.gw = lan_gateway + lan_network.num_addresses

        self.gw_ng = ipaddress.IPv4Interface(str(self.gw).decode('utf-8') + '/' + str(lan_network.netmask))
        self.nw = self.gw_ng.network
        self.gw_prefixlen = self.nw.prefixlen

        # override above values if set in wan options
        if 'options' in kwargs:
            options = [x.strip() for x in kwargs['options'].split(',')]
            for opt in options:
                if opt.startswith('wan-static-ip:'):
                    value = opt.replace('wan-static-ip:', '')
                    self.gw = ipaddress.IPv4Address(value.split('/')[0])
                    if '/' not in value:
                        value = value + (u'/24')
                    # TODO: use IPv4 and IPv6 interface object everywhere in this class
                    self.gw_ng = ipaddress.IPv4Interface(value)
                    self.nw = self.gw_ng.network
                    self.gw_prefixlen = self.nw.prefixlen
                    self.static_ip = True
                if opt.startswith('wan-static-ipv6:'):
                    if "/" in opt:
                        ipv6_interface=ipaddress.IPv6Interface(opt.replace('wan-static-ipv6:', ''))
                        self.gwv6 = ipv6_interface.ip
                        self.ipv6_prefix = ipv6_interface._prefixlen
                    else:
                        self.gwv6 = ipaddress.IPv6Address(opt.replace('wan-static-ipv6:', ''))
                if opt.startswith('wan-static-route:'):
                    self.static_route = opt.replace('wan-static-route:', '').replace('-', ' via ')
                # TODO: remove wan-static-route at some point above
                if opt.startswith('static-route:'):
                    self.static_route = opt.replace('static-route:', '').replace('-', ' via ')
                if opt == 'wan-dhcp-client':
                    self.wan_dhcp = True
                if opt == 'wan-no-eth0':
                    self.wan_no_eth0 = True
                if opt == 'wan-no-dhcp-sever':
                    self.wan_dhcp_server = False
                if opt == 'wan-dhcp-client-v6':
                    self.wan_dhcpv6 = True
                if opt.startswith('mgmt-dns:'):
                    value = opt.replace('mgmt-dns:', '')
                    self.mgmt_dns = ipaddress.IPv4Address(value.split('/')[0])

        try:
            i = self.expect(["yes/no", "assword:", "Last login", username+".*'s password:"] + self.prompt, timeout=30)
        except pexpect.TIMEOUT:
            raise Exception("Unable to connect to %s." % name)
        except pexpect.EOF:
            if hasattr(self, "before"):
                print(self.before)
            raise Exception("Unable to connect to %s." % name)
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

        # attempts to fix the cli colums size
        self.set_cli_size(200)


        if ipaddr is None:
            self.sendline('hostname')
            self.expect('hostname')
            self.expect(self.prompt)
            ipaddr = self.ipaddr = self.before.strip()

        self.sendline('alias mgmt')
        idx = self.expect(['alias mgmt=', pexpect.TIMEOUT], timeout=10)
        if idx == 0:
            self.expect(self.prompt)
            self.sendline('alias apt="mgmt apt"; alias apt-get="mgmt apt-get"')
            self.expect_exact('alias apt="mgmt apt"; alias apt-get="mgmt apt-get"')
        self.expect(self.prompt)

        cmsg = '%s ' % ipaddr
        if self.port != 22:
            cmsg += '%s port ' % port
        cmsg += 'device console = '
        cmsg += colored('%s (%s)' % (color, name), color)
        cprint(cmsg, None, attrs=['bold'])

        if post_cmd_host is not None:
            sys.stdout.write("\tRunning post_cmd_host.... ")
            sys.stdout.flush()
            phc = pexpect.spawn(command='bash', args=['-c', post_cmd_host], env=env)
            i = phc.expect([pexpect.EOF, pexpect.TIMEOUT, 'password'])
            if i > 0:
                print("\tpost_cmd_host did not complete, it likely failed\n")
            else:
                print("\tpost_cmd_host done")

        if post_cmd is not None:
            sys.stdout.write("\tRunning post_cmd.... ")
            sys.stdout.flush()
            env_prefix=""
            for k, v in env.iteritems():
                env_prefix += "export %s=%s; " % (k, v)

            self.sendline(env_prefix + post_cmd)
            self.expect(self.prompt)
            print("\tpost_cmd done")

        if reboot:
            self.reset()

        self.logfile_read = output

    def run_cleanup_cmd(self):
        sys.stdout.write("Running cleanup_cmd on %s..." % self.name)
        sys.stdout.flush()
        cc = pexpect.spawn(command='bash', args=['-c', self.cleanup_cmd], env=self.env)
        cc.expect(pexpect.EOF, timeout=120)
        print("cleanup_cmd done.")

    def reset(self):
        self.sendline('reboot')
        self.expect(['going down','disconnected'])
        try:
            self.expect(self.prompt, timeout=10)
        except:
            pass
        time.sleep(15)  # Wait for the network to go down.
        for i in range(0, 20):
            try:
                pexpect.spawn('ping -w 1 -c 1 ' + self.name).expect('64 bytes', timeout=1)
            except:
                print(self.name + " not up yet, after %s seconds." % (i + 15))
            else:
                print("%s is back after %s seconds, waiting for network daemons to spawn." % (self.name, i + 14))
                time.sleep(15)
                break
        self.__init__(self.name, self.color,
                      self.output, self.username,
                      self.password, self.port,
                      reboot=False)

    def install_pkgs(self):
        if self.pkgs_installed == True:
            return

        self.sendline('echo "Acquire::ForceIPv4 "true";" > /etc/apt/apt.conf.d/99force-ipv4')
        self.expect(self.prompt)

        if not self.wan_no_eth0 and not self.wan_dhcp and not self.install_pkgs_after_dhcp and not getattr(self, 'standalone_provisioner', False):
            self.sendline('ifconfig %s down' % self.iface_dut)
            self.expect(self.prompt)

        pkgs = "isc-dhcp-server xinetd tinyproxy curl apache2-utils nmap psmisc vim-common tftpd-hpa pppoe isc-dhcp-server procps iptables lighttpd psmisc dnsmasq xxd"

        def _install_pkgs():
            self.sendline('apt-get update && apt-get -o DPkg::Options::="--force-confnew" -qy install %s' % pkgs)
            if 0 == self.expect(['Reading package', pexpect.TIMEOUT], timeout=60):
                self.expect(self.prompt, timeout=300)
            else:
                print("Failed to download packages, things might not work")
                self.sendcontrol('c')
                self.expect(self.prompt)

            self.pkgs_installed = True

        # TODO: use netns for all this?
        undo_default_route = None
        self.sendline('ping -4 -c1 deb.debian.org')
        i = self.expect(['ping: unknown host', 'connect: Network is unreachable', pexpect.TIMEOUT] + self.prompt, timeout=10)
        if 0 == i:
            # TODO: don't reference eth0, but the uplink iface
            self.sendline("echo SYNC; ip route list | grep 'via.*dev eth0' | awk '{print $3}'")
            self.expect_exact("SYNC\r\n")
            if 0 == self.expect(['(\d{1,3}.\d{1,3}.\d{1,3}.\d{1,3})\r\n'] + self.prompt, timeout=5):
                possible_default_gw = self.match.group(1)
                self.sendline("ip route add default via %s" % possible_default_gw)
                self.expect(self.prompt)
                self.sendline('ping -c1 deb.debian.org')
                self.expect(self.prompt)
                undo_default_route = possible_default_gw
                self.sendline('apt-get update && apt-get -o DPkg::Options::="--force-confnew" -qy install %s' % pkgs)
                if 0 == self.expect(['Reading package', pexpect.TIMEOUT], timeout=60):
                    self.expect(self.prompt, timeout=300)
                else:
                    print("Failed to download packages, things might not work")
                    self.sendcontrol('c')
                    self.expect(self.prompt)
        elif 1 == i:
            if self.install_pkgs_after_dhcp:
                _install_pkgs()
            else:
                self.install_pkgs_after_dhcp = True
            return
        elif 2 == i:
            self.sendcontrol('c')
            self.expect(self.prompt)
        else:
            _install_pkgs()

        if undo_default_route is not None:
            self.sendline("ip route del default via %s" % undo_default_route)
            self.expect(self.prompt)

    def turn_on_pppoe(self):
        self.sendline('cat > /etc/ppp/pppoe-server-options << EOF')
        self.sendline('noauth')
        self.sendline('ms-dns 8.8.8.8')
        self.sendline('ms-dns 8.8.4.4')
        self.sendline('EOF')
        self.expect(self.prompt)
        self.sendline('pppoe-server -k -I %s -L 192.168.2.1 -R 192.168.2.10 -N 4' % self.iface_dut)
        self.expect(self.prompt)

    def turn_off_pppoe(self):
        self.sendline("\nkillall pppoe-server pppoe pppd")
        self.expect("pppd")
        self.expect(self.prompt)

    def start_tftp_server(self):
        # we can call this first, before configure so we need to do this here
        # as well
        self.install_pkgs()
        # the entire reason to start tftp is to copy files to devices
        # which we do via ssh so let's start that as well
        self.start_sshd_server()

        try:
            eth1_addr = self.get_interface_ipaddr(self.iface_dut)
        except:
            eth1_addr = None

        # set WAN ip address, for now this will always be this address for the device side
        # TODO: fix gateway for non-WAN tftp_server
        if self.gw != eth1_addr:
            self.sendline('ifconfig %s %s' % (self.iface_dut, self.gw_ng))
            self.expect(self.prompt)
        self.sendline('ifconfig %s up' % self.iface_dut)
        self.expect(self.prompt)

        #configure tftp server
        self.sendline('/etc/init.d/tftpd-hpa stop')
        self.expect('Stopping')
        self.expect(self.prompt)
        if not self.shared_tftp_server:
            self.sendline('rm -rf '+self.tftp_dir)
            self.expect(self.prompt)
            self.sendline('rm -rf /srv/tftp')
            self.expect(self.prompt)
        self.sendline('mkdir -p /srv/tftp')
        self.expect(self.prompt)
        self.sendline('ln -sf /srv/tftp/ '+self.tftp_dir)
        self.expect(self.prompt)
        self.sendline('mkdir -p '+self.tftp_dir+'/tmp')
        self.expect(self.prompt)
        self.sendline('chmod a+w '+self.tftp_dir+'/tmp')
        self.expect(self.prompt)
        self.sendline('mkdir -p '+self.tftp_dir+'/crashdump')
        self.expect(self.prompt)
        self.sendline('chmod a+w '+self.tftp_dir+'/crashdump')
        self.expect(self.prompt)
        self.sendline('sed /TFTP_OPTIONS/d -i /etc/default/tftpd-hpa')
        self.expect(self.prompt)
        self.sendline('echo TFTP_OPTIONS=\\"--secure --create\\" >> /etc/default/tftpd-hpa')
        self.expect(self.prompt)
        self.sendline('sed /TFTP_ADDRESS/d -i /etc/default/tftpd-hpa')
        self.expect(self.prompt)
        self.sendline('echo TFTP_ADDRESS=\\":69\\" >> /etc/default/tftpd-hpa')
        self.expect(self.prompt)
        self.sendline('sed /TFTP_DIRECTORY/d -i /etc/default/tftpd-hpa')
        self.expect(self.prompt)
        self.sendline('echo TFTP_DIRECTORY=\\"/srv/tftp\\" >> /etc/default/tftpd-hpa')
        self.expect(self.prompt)
        self.sendline('/etc/init.d/tftpd-hpa restart')
        self.expect(self.prompt)

    def restart_tftp_server(self):
        self.sendline('\n/etc/init.d/tftpd-hpa restart')
        self.expect('Restarting')
        self.expect(self.prompt)

    def start_sshd_server(self):
        self.sendline('/etc/init.d/rsyslog start')
        self.expect(self.prompt)
        self.sendline('/etc/init.d/ssh start')
        self.expect(self.prompt)
        self.sendline('sed "s/.*PermitRootLogin.*/PermitRootLogin yes/g" -i /etc/ssh/sshd_config')
        self.expect(self.prompt)
        self.sendline('/etc/init.d/ssh reload')
        self.expect(self.prompt)

    def configure(self, kind, config=[]):
        # TODO: wan needs to enable on more so we can route out?
        self.enable_ipv6(self.iface_dut)
        self.install_pkgs()
        self.start_sshd_server()
        if kind == "wan_device":
            self.setup_as_wan_gateway()
        elif kind == "lan_device":
            self.setup_as_lan_device()

        if self.static_route is not None:
            # TODO: add some ppint handle this more robustly
            self.send('ip route del %s; ' % self.static_route.split(' via ')[0])
            self.sendline('ip route add %s' % self.static_route)
            self.expect(self.prompt)

    def setup_dhcp_server(self):
        if not self.wan_dhcp_server:
            return

        # configure DHCP server
        self.sendline('/etc/init.d/isc-dhcp-server stop')
        self.expect(self.prompt)
        self.sendline('sed s/INTERFACES=.*/INTERFACES=\\"%s\\"/g -i /etc/default/isc-dhcp-server' % self.iface_dut)
        self.expect(self.prompt)
        self.sendline('sed s/INTERFACESv4=.*/INTERFACESv4=\\"%s\\"/g -i /etc/default/isc-dhcp-server' % self.iface_dut)
        self.expect(self.prompt)
        self.sendline('sed s/INTERFACESv6=.*/INTERFACESv6=\\"%s\\"/g -i /etc/default/isc-dhcp-server' % self.iface_dut)
        self.expect(self.prompt)
        self.sendline('cat > /etc/dhcp/dhcpd.conf << EOF')
        self.sendline('ddns-update-style none;')
        self.sendline('option domain-name "bigfoot-test";')
        self.sendline('option domain-name-servers %s;' % self.gw)
        self.sendline('default-lease-time 600;')
        self.sendline('max-lease-time 7200;')
        # use the same netmask as the lan device
        self.sendline('subnet %s netmask %s {' % (self.nw.network_address, self.nw.netmask))
        self.sendline('          range %s %s;' % (self.nw.network_address + 10, self.nw.network_address + 100))
        self.sendline('          option routers %s;' % self.gw)
        self.sendline('}')
        self.sendline('EOF')
        self.expect(self.prompt)
        self.sendline('/etc/init.d/isc-dhcp-server start')
        self.expect(['Starting ISC DHCP(v4)? server.*dhcpd.', 'Starting isc-dhcp-server.*'])
        self.expect(self.prompt)

    def setup_dnsmasq(self):
        self.sendline('cat > /etc/dnsmasq.conf << EOF')
        self.sendline('server=8.8.4.4')
        self.sendline('listen-address=127.0.0.1')
        self.sendline('listen-address=%s' % self.gw)
        if self.gwv6 is not None:
            self.sendline('listen-address=%s' % self.gwv6)
        self.sendline('addn-hosts=/etc/dnsmasq.hosts') #all additional hosts will be added to dnsmasq.hosts
        self.sendline('EOF')
        self.add_hosts()
        self.sendline('/etc/init.d/dnsmasq restart')
        self.expect(self.prompt)
        self.sendline('echo "nameserver 127.0.0.1" > /etc/resolv.conf')
        self.expect(self.prompt)

    def add_hosts(self):
        #to add extra hosts(dict) to dnsmasq.hosts if dns has to run in wan container
        import config
        hosts={}
        for device in config.board['devices']:
            if 'ipaddr' in device:
                domain_name=str(getattr(config, device['name']).name)+'.boardfarm.com'
                device = getattr(config, device['name'])
                if not hasattr(device, 'ipaddr'):
                    continue
                hosts[domain_name] = str(device.ipaddr)
        if hosts is not None:
            self.sendline('cat > /etc/dnsmasq.hosts << EOF')
            for key, value in hosts.iteritems():
                self.sendline(key+" "+ value)
            self.sendline('EOF')

    def remove_hosts(self):
        self.sendline('rm  /etc/dnsmasq.hosts')
        self.expect(self.prompt)
        self.sendline('/etc/init.d/dnsmasq restart')
        self.expect(self.prompt)

    def setup_as_wan_gateway(self):

        self.setup_dnsmasq()

        self.sendline('killall iperf ab hping3')
        self.expect(self.prompt)

        # potential cleanup so this wan device works
        self.sendline('iptables -t nat -X')
        self.expect(self.prompt)
        self.sendline('iptables -t nat -F')
        self.expect(self.prompt)

        # set WAN ip address
        if self.wan_dhcp:
            self.sendline('/etc/init.d/isc-dhcp-server stop')
            self.expect(self.prompt)
            self.sendline('dhclient -r %s; dhclient %s' % (self.iface_dut, self.iface_dut))
            self.expect(self.prompt)
            self.gw = self.get_interface_ipaddr(self.iface_dut)
        elif not self.wan_no_eth0:
            self.sendline('ifconfig %s %s' % (self.iface_dut, self.gw_ng))
            self.expect(self.prompt)
            self.sendline('ifconfig %s up' % self.iface_dut)
            self.expect(self.prompt)
            if self.wan_dhcp_server:
                self.setup_dhcp_server()

        if self.wan_dhcpv6 == True:
            # we are bypass this for now (see http://patchwork.ozlabs.org/patch/117949/)
            self.sendline('sysctl -w net.ipv6.conf.%s.accept_dad=0' % self.iface_dut)
            self.expect(self.prompt)
            try:
                self.gwv6 = self.get_interface_ip6addr(self.iface_dut)
            except:
                self.sendline('dhclient -6 -i -r %s' % self.iface_dut)
                self.expect(self.prompt)
                self.sendline('dhclient -6 -i -v %s' % self.iface_dut)
                self.expect(self.prompt)
                self.sendline('ip -6 addr')
                self.expect(self.prompt)
                self.gwv6 = self.get_interface_ip6addr(self.iface_dut)
        elif self.gwv6 is not None:
            # we are bypass this for now (see http://patchwork.ozlabs.org/patch/117949/)
            self.sendline('sysctl -w net.ipv6.conf.%s.accept_dad=0' % self.iface_dut)
            self.expect(self.prompt)
            self.sendline('ip -6 addr add %s/%s dev %s' % (self.gwv6, self.ipv6_prefix, self.iface_dut))
            self.expect(self.prompt)


        # configure routing
        self.sendline('sysctl net.ipv4.ip_forward=1')
        self.expect(self.prompt)
        self.sendline('sysctl net.ipv6.conf.all.forwarding=0')
        self.expect(self.prompt)

        if self.wan_no_eth0 or self.wan_dhcp:
            wan_uplink_iface = self.iface_dut
        else:
            wan_uplink_iface = "eth0"

        wan_ip_uplink = self.get_interface_ipaddr(wan_uplink_iface)
        self.sendline('iptables -t nat -A POSTROUTING -o %s -j SNAT --to-source %s' % (wan_uplink_iface, wan_ip_uplink))
        self.expect(self.prompt)

        self.sendline('echo 0 > /proc/sys/net/ipv4/tcp_timestamps')
        self.expect(self.prompt)
        self.sendline('echo 0 > /proc/sys/net/ipv4/tcp_sack')
        self.expect(self.prompt)

        self.sendline('ifconfig %s' % self.iface_dut)
        self.expect(self.prompt)

        self.turn_off_pppoe()

    def setup_as_lan_device(self):
        # potential cleanup so this wan device works
        self.sendline('killall iperf ab hping3')
        self.expect(self.prompt)
        self.sendline('\niptables -t nat -X')
        self.expect('iptables -t')
        self.expect(self.prompt)
        self.sendline('sysctl net.ipv4.ip_forward=1')
        self.expect(self.prompt)
        self.sendline('iptables -t nat -F; iptables -t nat -X')
        self.expect(self.prompt)
        self.sendline('iptables -F; iptables -X')
        self.expect(self.prompt)
        self.sendline('iptables -t nat -A PREROUTING -p tcp --dport 222 -j DNAT --to-destination %s:22' % self.lan_gateway)
        self.expect(self.prompt)
        self.sendline('iptables -t nat -A POSTROUTING -o %s -p tcp --dport 22 -j MASQUERADE' % self.iface_dut)
        self.expect(self.prompt)
        self.sendline('echo 0 > /proc/sys/net/ipv4/tcp_timestamps')
        self.expect(self.prompt)
        self.sendline('echo 0 > /proc/sys/net/ipv4/tcp_sack')
        self.expect(self.prompt)
        self.sendline('pkill --signal 9 -f dhclient.*%s' % self.iface_dut)
        self.expect(self.prompt)

    def start_lan_client(self, wan_gw=None):
        # very casual try for ipv6 addr, if we don't get one don't fail for now
        try:
            self.enable_ipv6(self.iface_dut)
            # TODO: how to wait for stateless config?
            self.get_interface_ip6addr(self.iface_dut)
        except:
            self.sendline('dhclient -6 -i -r %s' % self.iface_dut)
            self.expect(self.prompt)
            self.sendline('dhclient -6 -i -v %s' % self.iface_dut)
            if 0 == self.expect([pexpect.TIMEOUT] + self.prompt, timeout=15):
                self.sendcontrol('c')
                self.expect(self.prompt)
            self.sendline('ip -6 addr')
            self.expect(self.prompt)

        # TODO: this should not be required (fix at some point...)
        self.sendline('sysctl -w net.ipv6.conf.%s.accept_dad=0' % self.iface_dut)
        self.sendline('ip link set down %s && ip link set up %s' % (self.iface_dut, self.iface_dut))
        self.expect(self.prompt)
        self.disable_ipv6('eth0')

        self.sendline('\nifconfig %s up' % self.iface_dut)
        self.expect('ifconfig %s up' % self.iface_dut)
        self.expect(self.prompt)
	self.sendline("dhclient -4 -r %s" % self.iface_dut)
        self.expect(self.prompt)
        self.sendline('\nifconfig %s 0.0.0.0' % self.iface_dut)
        self.expect(self.prompt)
        self.sendline('rm /var/lib/dhcp/dhclient.leases')
        self.expect(self.prompt)
        self.sendline("sed -e 's/mv -f $new_resolv_conf $resolv_conf/cat $new_resolv_conf > $resolv_conf/g' -i /sbin/dhclient-script")
        self.expect(self.prompt)

        if self.mgmt_dns is not None:
            self.sendline("sed '/append domain-name-servers %s/d' -i /etc/dhcp/dhclient.conf" % str(self.mgmt_dns))
            self.expect(self.prompt)
            self.sendline('echo "append domain-name-servers %s;" >> /etc/dhcp/dhclient.conf' % str(self.mgmt_dns))
            self.expect(self.prompt)

        # TODO: don't hard code eth0
        self.sendline('ip route del default dev eth0')
        self.expect(self.prompt)
        for attempt in range(3):
            try:
                self.sendline('dhclient -4 -v %s' % self.iface_dut)
                self.expect('DHCPOFFER', timeout=30)
                self.expect(self.prompt)
                break
            except:
                self.sendcontrol('c')
        else:
            raise Exception("Error: Device on LAN couldn't obtain address via DHCP.")

        self.sendline('cat /etc/resolv.conf')
        self.expect(self.prompt)
        self.sendline('ip addr show dev %s' % self.iface_dut)
        self.expect(self.prompt)
        self.sendline('ip route')
        # TODO: we should verify this so other way, because the they could be the same subnets
        # in theory
        i = self.expect(['default via %s dev %s' % (self.lan_gateway, self.iface_dut), pexpect.TIMEOUT], timeout=5)
        if i == 1:
            # bridged mode
            self.is_bridged = True
            # update gw
            self.sendline("ip route list 0/0 | awk '{print $3}'")
            self.expect_exact("ip route list 0/0 | awk '{print $3}'")
            self.expect(self.prompt)
            self.lan_gateway = ipaddress.IPv4Address(self.before.strip().decode())

            ip_addr = self.get_interface_ipaddr(self.iface_dut)
            self.sendline("ip route | grep %s | awk '{print $1}'" % ip_addr)
            self.expect_exact("ip route | grep %s | awk '{print $1}'" % ip_addr)
            self.expect(self.prompt)
            self.lan_network = ipaddress.IPv4Network(self.before.strip().decode())
        self.sendline('ip -6 route')
        self.expect(self.prompt)

        # Setup HTTP proxy, so board webserver is accessible via this device
        self.sendline('curl --version')
        self.expect_exact('curl --version')
        self.expect(self.prompt)
        self.sendline('ab -V')
        self.expect(self.prompt)
        self.sendline('nmap --version')
        self.expect(self.prompt)
        # TODO: determine which config file is the correct one... but for now just modify both
        for f in ['/etc/tinyproxy.conf', '/etc/tinyproxy/tinyproxy.conf']:
            self.sendline("sed -i 's/^Port 8888/Port 8080/' %s" % f)
            self.expect(self.prompt)
            self.sendline("sed 's/#Allow/Allow/g' -i %s" % f)
            self.expect(self.prompt)
            self.sendline("sed '/Listen/d' -i %s" % f)
            self.expect(self.prompt)
            self.sendline('echo "Listen 0.0.0.0" >> %s' % f)
            self.expect(self.prompt)
            self.sendline('echo "Listen ::" >> %s' % f)
            self.expect(self.prompt)
        self.sendline('/etc/init.d/tinyproxy restart')
        self.expect('Restarting')
        self.expect(self.prompt)
        # Write a useful ssh config for routers
        self.sendline('mkdir -p ~/.ssh')
        self.sendline('cat > ~/.ssh/config << EOF')
        self.sendline('Host %s' % self.lan_gateway)
        self.sendline('StrictHostKeyChecking no')
        self.sendline('UserKnownHostsFile=/dev/null')
        self.sendline('')
        self.sendline('Host krouter')
        self.sendline('Hostname %s' % self.lan_gateway)
        self.sendline('StrictHostKeyChecking no')
        self.sendline('UserKnownHostsFile=/dev/null')
        self.sendline('EOF')
        self.expect(self.prompt)
        # Copy an id to the router so people don't have to type a password to ssh or scp
        self.sendline('nc %s 22 -w 1 | cut -c1-3' % self.lan_gateway)
        self.expect_exact('nc %s 22 -w 1 | cut -c1-3' % self.lan_gateway)
        if 0 == self.expect(['SSH'] + self.prompt, timeout=5) and not self.is_bridged:
            self.sendcontrol('c')
            self.expect(self.prompt)
            self.sendline('[ -e /root/.ssh/id_rsa ] || ssh-keygen -N "" -f /root/.ssh/id_rsa')
            if 0 != self.expect(['Protocol mismatch.'] + self.prompt):
                self.sendline('scp ~/.ssh/id_rsa.pub %s:/etc/dropbear/authorized_keys' % self.lan_gateway)
                if 0 == self.expect(['assword:'] + self.prompt):
                    self.sendline('password')
                    self.expect(self.prompt)
        else:
            self.sendcontrol('c')
            self.expect(self.prompt)

        if self.install_pkgs_after_dhcp:
            self.install_pkgs()

        if wan_gw is not None and 'options' in self.kwargs and \
            'lan-fixed-route-to-wan' in self.kwargs['options']:
                self.sendline('ip route add %s via %s' % (wan_gw, self.lan_gateway))
                self.expect(self.prompt)

    def tftp_server_ip_int(self):
        '''Returns the DUT facing side tftp server ip'''
        return self.gw

    def tftp_server_ipv6_int(self):
        '''Returns the DUT facing side tftp server ipv6'''
        return self.gwv6

if __name__ == '__main__':
    # Example use
    try:
        ipaddr, port = sys.argv[1].split(':')
    except:
        raise Exception("First argument should be in form of ipaddr:port")
    dev = DebianBox(ipaddr=ipaddr,
                    color='blue',
                    username="root",
                    password="bigfoot1",
                    port=port)
    dev.sendline('echo Hello')
    dev.expect('Hello', timeout=4)
    dev.expect(dev.prompt)

    if sys.argv[2] == "setup_as_lan_device":
        dev.configure("lan_device")
    if sys.argv[2] == "setup_as_wan_gateway":
        dev.configure("wan_device")
    if sys.argv[2] == "test_voip":
        sys.path.insert(0, os.getcwd())
        sys.path.insert(0, os.getcwd() + '/tests')
        from lib import installers

        installers.install_asterisk(dev)
