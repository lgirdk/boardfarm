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
import base_cmts
from lib.regexlib import AllValidIpv6AddressesRegex, ValidIpv4AddressRegex




class ArrisCMTS(base_cmts.BaseCmts):
    '''
    Connects to and configures a Arris CMTS
    '''

    prompt = [ 'arris(.*)>', 'arris(.*)#', 'arris\(.*\)> ', 'arris\(.*\)# ']
    model = "arris_cmts"

    class ArrisCMTSDecorators():

        @classmethod
        def mac_to_cmts_type_mac_decorator(cls, function):
            def wrapper(*args, **kwargs):
                #import pdb; pdb.set_trace()
                args = list(args)
                if ':' in args[1]:
                    tmp = args[1].lower().replace(":", "")
                    args[1] = tmp[:4]+"."+ tmp[4:8]+"."+tmp[8:]
                return function(*args)
            return wrapper

    def __init__(self,
                 *args,
                 **kwargs):
        conn_cmd = kwargs.get('conn_cmd', None)
        connection_type = kwargs.get('connection_type', 'local_serial')
        self.username = kwargs.get('username', 'boardfarm')
        self.password = kwargs.get('password', 'boardfarm')
        self.password_admin = kwargs.get('password_admin', 'boardfarm')
        self.mac_domain = kwargs.get('mac_domain', None)

        if conn_cmd is None:
            # TODO: try to parse from ipaddr, etc
            raise Exception("No command specified to connect to Arris CMTS")

        self.connection = connection_decider.connection(connection_type, device=self, conn_cmd=conn_cmd)
        self.connection.connect()
        self.connect()
        self.logfile_read = sys.stdout

        self.name = kwargs.get('name', self.model)

    def connect(self):
        try:
            try:
                self.expect_exact("Escape character is '^]'.", timeout=5)
            except:
                pass
            self.sendline()
            if 1 != self.expect(['\r\nLogin:', pexpect.TIMEOUT], timeout=10):
                self.sendline(self.username)
                self.expect('assword:')
                self.sendline(self.password)
                self.expect(self.prompt)
            else:
                # Over telnet we come in at the right prompt
                # over serial we could have a double login
                # not yet implemented
                raise('Failed to connect to Arris via telnet')
            self.sendline('enable')
            if 0 == self.expect(['Password:'] + self.prompt):
                self.sendline(self.password_admin)
                self.expect(self.prompt)
            self.sendline('config')
            self.expect('Enter configuration commands, one per line. End with exit or quit or CTRL Z')
            self.expect(self.prompt)
            self.sendline('pagination')
            self.expect(self.prompt)
            return
        except:
            raise Exception("Unable to get prompt on CASA device")

    def logout(self):
        self.sendline('exit')
        self.sendline('exit')

    @ArrisCMTSDecorators.mac_to_cmts_type_mac_decorator
    def check_online(self, cmmac):
        """
        Function checks the encrytion mode and returns True if online
        Args: cmmac 
        Return: True if the CM is operational and BPI encryption is enabled
                False if any of the 2 conditions is not fullfilled
        """
        self.sendline('show cable modem  %s detail' % cmmac)
        self.expect(self.prompt)
        if 'State=Operational' in self.before and 'Privacy=Ready  Ver=BPI' in self.before:
            return True
        else:
            return False

    @ArrisCMTSDecorators.mac_to_cmts_type_mac_decorator
    def clear_offline(self, cmmac):
        """
        Reset a modem
        Args: cmmac
        """
        self.sendline('exit')
        self.expect(self.prompt)
        self.sendline('clear cable modem %s offline' % cmmac)
        self.expect(self.prompt)
        self.sendline('configure')
        self.expect(self.prompt)

    @ArrisCMTSDecorators.mac_to_cmts_type_mac_decorator
    def clear_cm_reset(self, cmmac):
        """
        Reset a modem
        Args: cmmac
        """
        self.sendline('exit')
        self.expect(self.prompt)
        """ NB: this command does not reboot the CM, but forces it to reinitialise """
        self.sendline("clear cable modem %s reset" %cmmac)
        self.expect(self.prompt)
        self.sendline('configure')
        self.expect(self.prompt)


    @ArrisCMTSDecorators.mac_to_cmts_type_mac_decorator
    def get_mtaip(self, cmmac, mtamac):
        """
        Gets the mta ip address
        Args: cmmac, mtamac(not used)
        Return: mta ip or None if not found
        """
        self.sendline('show cable modem %s detail | include MTA' % (cmmac))
        self.expect('CPE\(MTA\)\s+.*IPv4=(' + ValidIpv4AddressRegex + ')\r\n')
        result = self.match.group(1)
        if self.match != None:
            output = result
        else:
            output = "None"
        self.expect(self.prompt)
        return output

    @ArrisCMTSDecorators.mac_to_cmts_type_mac_decorator
    def get_ip_from_regexp(self, cmmac, ip_regexpr):
        """
        Gets an ip address according to a regexpr (helper function)
        Args: cmmac, ip_regexpr
        Return: ip addr (ipv4/6 according to regexpr) or None if not found
        """
        self.sendline('show cable modem | include %s' % cmmac)
        if 1 == self.expect([cmmac + '\s+(' + ip_regexpr + ')', pexpect.TIMEOUT], timeout=2):
            output = "None"
        else:
            result = self.match.group(1)
            if self.match != None:
                output = result
            else:
                output = "None"
        self.expect(self.prompt)
        return output

    def get_cmip(self, cmmac):
        """
        Returns the CM mgmt ipv4 address 
        Args: cmmac 
        Return: ip addr (ipv4) or None if not found
        """
        return self.get_ip_from_regexp(cmmac, ValidIpv4AddressRegex)

    def get_cmipv6(self, cmmac):
        """
        Returns the CM mgmt ipv6 address 
        Args: cmmac
        Return: ip addr (ipv4) or None if not found
        """
        return self.get_ip_from_regexp(cmmac, AllValidIpv6AddressesRegex)

    @ArrisCMTSDecorators.mac_to_cmts_type_mac_decorator
    def get_cm_mac_domain(self,cm_mac):
        """
        Returns the Mac-domain of Cable modem
        Args: cm_mac
        Return: ip addr (ipv4) or None if not found
        """
        mac_domain = None
        self.sendline('show cable modem %s detail | include Cable-Mac='% cm_mac)
        if 0 == self.expect(['Cable-Mac= ([0-9]{1,3}),', pexpect.TIMEOUT], timeout=5):
            mac_domain = self.match.group(1)
        self.expect(self.prompt)
        return mac_domain

    '''
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

    def DUT_chnl_lock(self,cm_mac):
        """Check the CM channel locks with 24*8 """
        self.sendline("show cable modem %s bonding" % cm_mac)
        index = self.expect(["256\(8\*24\)"]+ self.prompt)
        chnl_lock = self.match.group()
        if 0 == index:
            self.expect(self.prompt)
            return True
        else:
            return False

    def get_cm_bundle(self,mac_domain):
        """Get the bundle id from mac-domain """
        self.sendline('show interface docsis-mac '+mac_domain+' | i "ip bundle"')
        index = self.expect(['(ip bundle)[ ]{1,}([0-9]|[0-9][0-9])'] + self.prompt)
        if index !=0:
            assert 0, "ERROR:Failed to get the CM bundle id from CMTS"
        bundle = self.match.group(2)
        self.expect(self.prompt)
        return bundle

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

    # Function:   get_cm_mac_cmts_format(mac)
    # Parameters: mac        (mac address XX:XX:XX:XX:XX:XX)
    # returns:    the cm_mac in cmts format xxxx.xxxx.xxxx (lowercase)
    def get_cm_mac_cmts_format(self, mac):
        if mac == None:
            return None
        # the mac cmts syntax format example is 3843.7d80.0ac0
        tmp = mac.replace(':', '')
        mac_cmts_format = tmp[:4]+"."+tmp[4:8]+"."+tmp[8:]
        return mac_cmts_format.lower()

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
    '''

