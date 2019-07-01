# Copyright (c) 2018
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.
#!/usr/bin/env python

import pexpect
import sys
import base
import re
import connection_decider
from lib.regexlib import ValidIpv6AddressRegex, ValidIpv4AddressRegex, AllValidIpv6AddressesRegex
import base_cmts

class CasaCMTS(base_cmts.BaseCmts):
    '''
    Connects to and configures a CASA CMTS
    '''

    prompt = ['CASA-C3200>', 'CASA-C3200#', 'CASA-C3200\(.*\)#', 'CASA-C10G>', 'CASA-C10G#', 'CASA-C10G\(.*\)#']
    model = "casa_cmts"
    variant = None

    def __init__(self,
                 *args,
                 **kwargs):
        conn_cmd = kwargs.get('conn_cmd', None)
        connection_type = kwargs.get('connection_type', 'local_serial')
        self.username = kwargs.get('username', 'root')
        self.password = kwargs.get('password', 'casa')
        self.password_admin = kwargs.get('password_admin', 'casa')
        self.mac_domain = kwargs.get('mac_domain', None)

        if conn_cmd is None:
            # TODO: try to parse from ipaddr, etc
            raise Exception("No command specified to connect to Casa CMTS")

        self.connection = connection_decider.connection(connection_type, device=self, conn_cmd=conn_cmd)
        self.connection.connect()
        self.connect()
        self.logfile_read = sys.stdout

        self.name = kwargs.get('name', 'casa_cmts')

    def connect(self):
        try:
            try:
                self.expect_exact("Escape character is '^]'.", timeout=30)
            except:
                pass
            if 2 != self.expect(['\r\n(.*) login:', '(.*) login:', pexpect.TIMEOUT], timeout=10):
                hostname = self.match.group(1).replace('\n', '').replace('\r', '').strip()
                self.prompt.append(hostname + '>')
                self.prompt.append(hostname + '#')
                self.prompt.append(hostname + '\(.*\)#')
                self.sendline(self.username)
                self.expect('assword:')
                self.sendline(self.password)
                self.expect(self.prompt)
            else:
                # Over telnet we come in at the right prompt
                # over serial it could be stale so we try to recover
                self.sendline('q')
                self.sendline('exit')
                self.expect([pexpect.TIMEOUT] + self.prompt, timeout=20)
            self.sendline('enable')
            if 0 == self.expect(['Password:'] + self.prompt):
                self.sendline(self.password_admin)
                self.expect(self.prompt)
            self.sendline('config')
            self.expect(self.prompt)
            self.sendline('page-off')
            self.expect(self.prompt)
            self.get_cmts_variant()
            return
        except:
            raise Exception("Unable to get prompt on CASA device")

    def logout(self):
        self.sendline('exit')
        self.sendline('exit')

    def get_cmts_variant(self):
        '''Function to get the cmt type'''
        self.sendline("show system | include Product")
        self.expect(['Product: ([0-9A-Z]+)'])
        self.variant = self.after

    def check_online(self, cmmac):
        """Function checks the encrytion mode and returns True if online"""
        """Function returns actual status if status other than online"""
        self.sendline('show cable modem %s' % cmmac)
        self.expect('.+ranging cm \d+')
        result = self.match.group()
        match = re.search('\d+/\d+/\d+\**\s+([^\s]+)\s+\d+\s+.+\d+\s+(\w+)\r\n', result)
        if match:
            status = match.group(1)
            encrytion = match.group(2)
            if status == "online(pt)" and encrytion == "yes":
                output = True
            elif status == "online" and encrytion == "no":
                output = True
            elif "online" not in status and status != None:
                output = status
            else:
                assert 0, "ERROR: incorrect cmstatus \""+status+"\" in cmts for bpi encrytion \""+encrytion+"\""
        else:
            assert 0, "ERROR: Couldn't fetch CM status from cmts"
        self.expect(self.prompt)
        return output

    def clear_offline(self, cmmac):
        self.sendline('clear cable modem %s offline' % cmmac)
        self.expect(self.prompt)

    def clear_cm_reset(self, cmmac):
        self.sendline("clear cable modem %s reset" %cmmac)
        self.expect(self.prompt)

    def check_PartialService(self, cmmac):
        self.sendline('show cable modem %s' % cmmac)
        self.expect('(\d+/\d+\.\d+/\d+(\*|\#)\s+\d+/\d+/\d+(\*|\#))\s+online')
        result = self.match.group(1)
        match = re.search('\#', result)
        if match != None:
            output = 1
        else:
            output = 0
        self.expect(self.prompt)
        return output

    def get_cmip(self, cmmac):
	tmp = cmmac.replace(":", "").lower()
	cmmac_cmts = tmp[:4]+"."+ tmp[4:8]+"."+tmp[8:]
        self.sendline('show cable modem %s' % cmmac)
        self.expect(cmmac_cmts + '\s+([\d\.]+)')
        result = self.match.group(1)
        if self.match != None:
            output = result
        else:
            output = "None"
        self.expect(self.prompt)
        return output

    def get_cmipv6(self, cmmac):
        self.sendline('show cable modem %s' % cmmac)
        self.expect(self.prompt)
        match = re.search(AllValidIpv6AddressesRegex, self.before)
        if match:
            output = match.group(0)
        else:
            output = "None"
        return output

    def get_mtaip(self, cmmac, mtamac):
        if ':' in mtamac:
            mtamac = self.get_cm_mac_cmts_format(mtamac)
        self.sendline('show cable modem %s cpe' % cmmac)
        self.expect('([\d\.]+)\s+dhcp\s+' + mtamac)
        result = self.match.group(1)
        if self.match != None:
            output = result
        else:
            output = "None"
        self.expect(self.prompt)
        return output

    def DUT_chnl_lock(self,cm_mac):
        """Check the CM channel locks based on cmts type"""
        streams = ['Upstream', 'Downstream']
        channel_list = []
        for stream in streams:
            self.sendline("show cable modem %s verbose | inc \"%s Channel Set\"" % (cm_mac, stream))
            if stream == 'Upstream':
                self.expect(['(\d+/\d+.\d+/\d+).*'])
                match = re.search('(\d+/\d+.\d+/\d+).*', self.after)
            elif stream == 'Downstream':
                self.expect(['(\d+/\d+/\d+).*'])
                match = re.search('(\d+/\d+/\d+).*', self.after)
            channel = len(match.group().split(","))
            channel_list.append(channel)
        return channel_list

    def get_cm_bundle(self,mac_domain):
        """Get the bundle id from mac-domain """
        self.sendline('show interface docsis-mac '+mac_domain+' | i "ip bundle"')
        index = self.expect(['(ip bundle)[ ]{1,}([0-9]|[0-9][0-9])'] + self.prompt)
        if index !=0:
            assert 0, "ERROR:Failed to get the CM bundle id from CMTS"
        bundle = self.match.group(2)
        self.expect(self.prompt)
        return bundle

    def get_cm_mac_domain(self,cm_mac):
        """Get the Mac-domain of Cable modem """
        self.sendline('show cable modem '+cm_mac+' verbose | i "MAC Domain"')
        idx = self.expect(['(MAC Domain)[ ]{2,}\:([0-9]|[0-9][0-9])'] + self.prompt)
        if idx != 0:
            assert 0,"ERROR: Failed to get the CM Mac Domain from the CMTS"
        mac_domain = self.match.group(2)
        self.expect(self.prompt)
        return mac_domain
    
    def get_cmts_ip_bundle(self,bundle):
        """get the CMTS bundle IP"""
        self.sendline('show interface ip-bundle %s | i "secondary"' % bundle)
        index = self.expect(['ip address ([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+) ([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+) secondary'] + self.prompt)
        if index != 0:
            assert 0,"ERROR: Failed to get the CMTS bundle IP"
        cmts_ip = self.match.group(1)
        self.expect(self.prompt)
        return cmts_ip

    def reset(self):
        self.sendline('exit')
        self.expect(self.prompt)
        self.sendline('del startup-config')
        self.expect('Please type YES to confirm deleting startup-config:')
        self.sendline('YES')
        self.expect(self.prompt)
        self.sendline('system reboot')
        if 0 == self.expect(['Proceed with reload\? please type YES to confirm :', 'starting up console shell ...'], timeout=180):
            self.sendline('YES')
            self.expect('starting up console shell ...', timeout=150)
        self.sendline()
        self.expect(self.prompt)
        self.sendline('page-off')
        self.expect(self.prompt)
        self.sendline('enable')
        self.expect('Password:')
        self.sendline(self.password)
        self.expect(self.prompt)
        self.sendline('config')
        self.expect(self.prompt)

    def wait_for_ready(self):
        self.sendline('show system')
        while 0 == self.expect(['NotReady'] + self.prompt):
            self.expect(self.prompt)
            self.expect(pexpect.TIMEOUT, timeout=5)
            self.sendline('show system')

    def save_running_to_startup_config(self):
        self.sendline('exit')
        self.expect(self.prompt)
        self.sendline('copy running-config startup-config')
        self.expect(self.prompt)
        self.sendline('config')
        self.expect(self.prompt)

    def save_running_config_to_local(self, filename):
        self.sendline('show running-config')
        self.expect('show running-config')
        self.expect(self.prompt)

        f = open(filename, "w")
        f.write(self.before)
        f.close()

    def set_iface_ipaddr(self, iface, ipaddr):
        self.sendline('interface %s' % iface)
        self.expect(self.prompt)
        self.sendline('ip address %s' % ipaddr)
        self.expect(self.prompt)
        self.sendline('no shutdown')
        self.expect(self.prompt)
        self.sendline('exit')
        self.expect(self.prompt)

    def set_iface_ipv6addr(self, iface, ipaddr):
        self.sendline('interface %s' % iface)
        self.expect(self.prompt)
        self.sendline('ipv6 address %s' % ipaddr)
        self.expect(self.prompt)
        self.sendline('no shutdown')
        self.expect(self.prompt)
        self.sendline('exit')
        self.expect(self.prompt)

    def add_ip_bundle(self, index, helper_ip, ip, secondary_ips=[]):
        self.sendline('interface ip-bundle %s' % index)
        self.expect(self.prompt)
        self.sendline('ip address %s 255.255.255.0' % ip)
        self.expect(self.prompt)
        for ip2 in secondary_ips:
            self.sendline('ip address %s 255.255.255.0 secondary' % ip2)
            self.expect(self.prompt)
        self.sendline('cable helper-address %s cable-modem' % helper_ip)
        self.expect(self.prompt)
        self.sendline('cable helper-address %s mta' % helper_ip)
        self.expect(self.prompt)
        self.sendline('cable helper-address %s host' % helper_ip)
        self.expect(self.prompt)
        self.sendline('exit')
        self.expect(self.prompt)

    def add_ipv6_bundle_addrs(self, index, helper_ip, ip, secondary_ips=[]):
        self.sendline('interface ip-bundle %s' % index)
        self.expect(self.prompt)
        self.sendline('ipv6 address %s' % ip)
        self.expect(self.prompt)
        for ip2 in secondary_ips:
            self.sendline('ipv6 address %s secondary' % ip2)
            self.expect(self.prompt)
        self.sendline('cable helper-ipv6-address %s' % helper_ip)
        self.expect(self.prompt)
        self.sendline('exit')
        self.expect(self.prompt)

    def add_route(self, net, mask, gw):
        self.sendline('route net %s %s gw %s' % (net, mask, gw))
        self.expect(self.prompt)

    def add_route6(self, net, gw):
        self.sendline('route6 net %s gw %s' % (net, gw))
        self.expect(self.prompt)

    def get_qam_module(self):
        self.sendline('show system')
        self.expect(self.prompt)
        return re.findall('Module (\d+) QAM', self.before)[0]

    def get_ups_module(self):
        self.sendline('show system')
        self.expect(self.prompt)
        return re.findall('Module (\d+) UPS', self.before)[0]

    def set_iface_qam(self, index, sub, annex, interleave, power):
        self.sendline('interface qam %s/%s' % (index, sub))
        self.expect(self.prompt)
        self.sendline('annex %s' % annex)
        self.expect(self.prompt)
        self.sendline('interleave %s' % interleave)
        self.expect(self.prompt)
        self.sendline('power %s' % power)
        self.expect(self.prompt)
        self.sendline('no shutdown')
        self.expect(self.prompt)
        self.sendline('exit')
        self.expect(self.prompt)

    def set_iface_qam_freq(self, index, sub, channel, freq):
        self.sendline('interface qam %s/%s' % (index, sub))
        self.expect(self.prompt)
        self.sendline('channel %s freq %s' % (channel, freq))
        self.expect(self.prompt)
        self.sendline('no channel %s shutdown' % channel)
        self.expect(self.prompt)
        self.sendline('exit')
        self.expect(self.prompt)

    def set_iface_upstream(self, ups_idx, ups_ch, freq, width, power):
        self.sendline('interface upstream %s/%s' % (ups_idx, ups_ch))
        self.expect(self.prompt)
        self.sendline('frequency %s' % freq)
        self.expect(self.prompt)
        self.sendline('channel-width %s' % width)
        self.expect(self.prompt)
        self.sendline('power-level %s' % power)
        self.expect(self.prompt)
        self.sendline('ingress-cancellation')
        self.expect(self.prompt)
        self.sendline('logical-channel 0 profile 3')
        self.expect(self.prompt)
        self.sendline('logical-channel 0 minislot 1')
        self.expect(self.prompt)
        self.sendline('no logical-channel 0 shutdown')
        self.expect(self.prompt)
        self.sendline('logical-channel 1 shutdown')
        self.expect(self.prompt)
        self.sendline('no shutdown')
        self.expect(self.prompt)
        self.sendline('exit')
        self.expect(self.prompt)

    def add_iface_docsis_mac(self, index, ip_bundle, qam_idx, qam_sub, qam_ch, ups_idx, ups_ch):
        self.sendline('interface docsis-mac %s' % index)
        self.expect(self.prompt)
        self.sendline('no shutdown')
        self.expect(self.prompt)
        self.sendline('early-authentication-encryption ranging')
        self.expect(self.prompt)
        self.sendline('no dhcp-authorization')
        self.expect(self.prompt)
        self.sendline('no multicast-dsid-forward')
        self.expect(self.prompt)
        self.sendline('no tftp-enforce')
        self.expect(self.prompt)
        self.sendline('tftp-proxy')
        self.expect(self.prompt)
        self.sendline('ip bundle %s' % ip_bundle)
        self.expect(self.prompt)
        self.sendline('ip-provisioning-mode dual-stack')
        self.expect(self.prompt)
        count = 1;
        for ch in qam_ch:
            self.sendline('downstream %s interface qam %s/%s/%s' % (count, qam_idx, qam_sub, ch))
            self.expect(self.prompt)
            count += 1
        count = 1;
        for ch in ups_ch:
            self.sendline('upstream %s interface upstream %s/%s/0' % (count, ups_idx, ch))
            self.expect(self.prompt)
            count += 1
        self.sendline('exit')
        self.expect(self.prompt)

    def modify_docsis_mac_ip_provisioning_mode(self, index, ip_pvmode='dual-stack'):
        self.sendline('interface docsis-mac %s' % index)
        self.expect(self.prompt)
        self.sendline('ip-provisioning-mode %s' % ip_pvmode)
        self.expect(self.prompt)

    def add_service_class(self, index, name, max_rate, max_burst, downstream=False):
        self.sendline('cable service-class %s' % index)
        self.expect(self.prompt)
        self.sendline('name %s' % name)
        self.expect(self.prompt)
        self.sendline('max-traffic-rate %s' % max_rate)
        self.expect(self.prompt)
        self.sendline('max-traffic-burst %s' % max_burst)
        self.expect(self.prompt)
        self.sendline('max-concat-burst 0')
        self.expect(self.prompt)
        if downstream:
            self.sendline('downstream')
            self.expect(self.prompt)
        self.sendline('exit')
        self.expect(self.prompt)

    def add_service_group(self, index, qam_idx, qam_sub, qam_channels, ups_idx, ups_channels):
        self.sendline('service group %s' % index)
        self.expect(self.prompt)
        for ch in qam_channels:
            self.sendline('qam %s/%s/%s' % (qam_idx, qam_sub, ch))
            self.expect(self.prompt)
        for ch in ups_channels:
            self.sendline('upstream %s/%s' % (ups_idx, ch))
            self.expect(self.prompt)
        self.sendline('exit')
        self.expect(self.prompt)

    def mirror_traffic(self, macaddr=""):
        self.sendline('diag')
        self.expect('Password:')
        self.sendline('casadiag')
        self.expect(self.prompt)
        self.sendline('mirror cm traffic 127.1.0.7 %s' % macaddr)
        if 0 == self.expect(['Please type YES to confirm you want to mirror all CM traffic:'] + self.prompt):
            self.sendline("YES")
            self.expect(self.prompt)
        self.sendline('exit')
        self.expect(self.prompt)

    def unmirror_traffic(self):
        self.sendline('diag')
        self.expect('Password:')
        self.sendline('casadiag')
        self.expect(self.prompt)
        self.sendline('mirror cm traffic 0')
        self.expect(self.prompt)
        self.sendline('exit')
        self.expect(self.prompt)

    def run_tcpdump(self, time, iface='any', opts=""):
        self.sendline('diag')
        self.expect('Password:')
        self.sendline('casadiag')
        self.expect(self.prompt)
        self.sendline('tcpdump "-i%s %s"' % (iface, opts))
        self.expect(self.prompt + [pexpect.TIMEOUT], timeout=time)
        self.sendcontrol('c')
        self.expect(self.prompt)
        self.sendline('exit')
        self.expect(self.prompt)

    def del_file(self, f):
        self.sendline('del %s' % f)
        self.expect(self.prompt)

    # Parameters: cm_mac        (CM mac address)
    # This function assumes the CM is online
    # returns:
    #   True      if the cmts does NOT see the CM eRouter
    #             (i.e. theCM mode is in bridge mode)
    #   False     if the cmts sees the CM eRouter
    #             (i.e. theCM mode is in gateway mode)
    def is_cm_bridged(self, cm_mac):
        self.sendline("show cable modem "+cm_mac+" cpe")
        if 0==self.expect(['eRouter']+self.prompt):
            self.expect(self.prompt)
            return False
        else:
            return True

    def check_docsis_mac_ip_provisioning_mode(self, index):
        self.sendline('show interface docsis-mac %s' % index)
        self.expect('ip-provisioning-mode (\w+\-\w+)')
        result = self.match.group(1)
        if self.match != None:
            return result

    def get_ertr_ipv4(self, mac):
        self.sendline("show cable modem %s cpe" % mac)
        self.expect(self.prompt)
        ertr_ipv4 = re.search('(%s) .*(eRouter)'% ValidIpv4AddressRegex ,self.before)
        if ertr_ipv4:
            ipv4 =ertr_ipv4.group(1)
            return ipv4
        else:
            return None

    def get_ertr_ipv6(self, mac):
        self.sendline("show cable modem %s cpe" % mac)
        self.expect(self.prompt)
        ertr_ipv6 = re.search(ValidIpv6AddressRegex ,self.before)
        if ertr_ipv6:
            ipv6 = ertr_ipv6.group()
            return ipv6
        else:
            return None

    def get_center_freq(self, mac_domain=None):
        return "512000000"

        # TODO: fix below
        if mac_domain is None:
            mac_domain = self.mac_domain

        assert mac_domain is not None, "get_center_freq() requires mac_domain to be set"

        self.sendline('show interface docsis-mac %s | inc downstream\s1\s' % mac_domain)
        self.expect_exact('show interface docsis-mac %s | inc downstream\s1\s' % mac_domain)
        self.expect(self.prompt)
        assert 'downstream 1 interface qam' in self.before

        major, minor, sub = self.before.strip().split(' ')[-1].split('/')

        self.sendline('show interface qam %s/%s | inc channel\s%s\sfreq' % (major, minor, sub))
        self.expect_exact('show interface qam %s/%s | inc channel\s%s\sfreq' % (major, minor, sub))

        self.expect(self.prompt)
        assert 'channel %s frequency' % sub in self.before

        return str(int(self.before.split(' ')[-1]))

if __name__ == '__main__':
    import time

    connection_type = "local_cmd"
    cmts = CasaCMTS(conn_cmd=sys.argv[1], connection_type=connection_type)

    if len(sys.argv) > 2 and sys.argv[2] == "setup_ipv6":
        print "Setting up IPv6 address, bundles, routes, etc"
        cmts.set_iface_ipv6addr('gige 0', '2001:dead:beef:1::cafe/64')
        cmts.add_route6('::/0', '2001:dead:beef:1::1')
        # TODO: casa 3200 cmts only supports one ip bundle for ipv6....
        # so we use a ipv6 address 2001:dead:beef:4::cafe/62 for that which means we can bump
        # these up too
        cmts.add_ipv6_bundle_addrs(1, "2001:dead:beef:1::1", "2001:dead:beef:4::cafe/64",
                                  secondary_ips=["2001:dead:beef:5::cafe/64", "2001:dead:beef:6::cafe/64"])
        sys.exit(0)

    # TODO: example for now, need to parse args
    if False:
        cmts.mirror_traffic()
        cmts.run_tcpdump(15, opts="-w dump.pcap")
        # TODO: extract pcap from CMTS
        cmts.del_file("dump.pcap")
        cmts.unmirror_traffic()
        sys.exit(0)

    cmts.save_running_to_startup_config()
    cmts.save_running_config_to_local("saved-casa-config-" + time.strftime("%Y%m%d-%H%M%S") + ".cfg")
    cmts.reset()
    cmts.wait_for_ready()

    cmts.set_iface_ipaddr('eth 0', '172.19.17.136 255.255.255.192')
    cmts.set_iface_ipaddr('gige 0', '192.168.3.222 255.255.255.0')
    # TODO: add third network for open
    cmts.add_ip_bundle(1, "192.168.3.1", "192.168.200.1", secondary_ips=["192.168.201.1", "192.168.202.1"])

    cmts.add_route("0.0.0.0", "0", "192.168.3.1")

    qam_idx = cmts.get_qam_module()
    ups_idx = cmts.get_ups_module()

    cmts.set_iface_qam(qam_idx, 0, 'A', 12, 550)
    cmts.set_iface_qam_freq(qam_idx, 0, 0, 235000000)
    cmts.set_iface_qam_freq(qam_idx, 0, 1, 243000000)
    cmts.set_iface_qam_freq(qam_idx, 0, 2, 251000000)
    cmts.set_iface_qam_freq(qam_idx, 0, 3, 259000000)

    cmts.add_service_class(1, 'UNLIMITED_down', 100000, 10000, downstream=True)
    cmts.add_service_class(2, 'UNLIMITED_up', 100000, 16320)

    cmts.add_service_group(1, qam_idx, 0, range(4), ups_idx, [0.0, 1.0])

    cmts.add_iface_docsis_mac(1, 1, qam_idx, 0, range(4), ups_idx, [0.0, 1.0])

    cmts.set_iface_upstream(ups_idx, 0.0, 47000000, 6400000, 6)

    print
    print("Press Control-] to exit interact mode")
    print("=====================================")
    cmts.interact()
    print
