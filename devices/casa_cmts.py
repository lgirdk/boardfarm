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

class CasaCMTS(base.BaseDevice):
    '''
    Connects to and configures a CASA CMTS
    '''

    prompt = ['CASA-C3200>', 'CASA-C3200#', 'CASA-C3200\(.*\)#', 'CASA-C10G>', 'CASA-C10G#', 'CASA-C10G\(.*\)#']
    model = "casa_cmts"

    def __init__(self,
                 *args,
                 **kwargs):
        conn_cmd = kwargs.get('conn_cmd', None)
        connection_type = kwargs.get('connection_type', 'local_serial')
        self.username = kwargs.get('username', 'root')
        self.password = kwargs.get('password', 'casa')

        if conn_cmd is None:
            # TODO: try to parse from ipaddr, etc
            raise Exception("No command specified to connect to Casa CMTS")

        self.connection = connection_decider.connection(connection_type, device=self, conn_cmd=conn_cmd)
        self.connection.connect()
        self.connect()
        self.logfile_read = sys.stdout

    def connect(self):
        try:
            if 0 == self.expect(['login:', pexpect.TIMEOUT], timeout=10):
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
                self.sendline(self.password)
                self.expect(self.prompt)
            self.sendline('config')
            self.expect(self.prompt)
            self.sendline('page-off')
            self.expect(self.prompt)
            return
        except:
            raise Exception("Unable to get prompt on CASA device")

    def logout(self):
        self.sendline('exit')
        self.sendline('exit')

    def check_online(self, cmmac):
        output = "offline"
        self.sendline('show cable modem %s' % cmmac)
        self.expect('.+ranging cm \d+')
        result = self.match.group()
        match = re.search('\d+/\d+/\d+\**\s+([^\s]+)', result)
        if match != None:
            output = match.group(1)
        else:
            output = "offline"
        self.expect(self.prompt)
        return output

    def clear_offline(self, cmmac):
        self.sendline('clear cable modem %s offline' % cmmac)
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
        self.sendline('show cable modem %s' % cmmac)
        self.expect(cmmac + '\s+([\d\.]+)')
        result = self.match.group(1)
        if self.match != None:
            output = result
        else:
            output = "None"
        self.expect(self.prompt)
        return output

    def get_mtaip(self, cmmac, mtamac):
        self.sendline('show cable modem %s cpe' % cmmac)
        self.expect('([\d\.]+)\s+dhcp\s+' + mtamac)
        result = self.match.group(1)
        if self.match != None:
            output = result
        else:
            output = "None"
        self.expect(self.prompt)
        return output

    def reset(self):
        self.sendline('exit')
        self.expect(self.prompt)
        self.sendline('del startup-config')
        self.expect('Please type YES to confirm deleting startup-config:')
        self.sendline('YES')
        self.expect(self.prompt)
        self.sendline('system reboot')
        if 0 == self.expect(['Proceed with reload\? please type YES to confirm :', 'starting up console shell ...'], timeout=150):
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

    def add_ip_bundle(self, index, ip1, ip2, helper_ip):
        self.sendline('interface ip-bundle %s' % index)
        self.expect(self.prompt)
        self.sendline('ip address %s 255.255.255.0' % ip1)
        self.expect(self.prompt)
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

    def add_route(self, net, mask, gw):
        self.sendline('route net %s %s gw %s' % (net, mask, gw))
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

    def run_tcpdump(self, time, opts=""):
        self.sendline('diag')
        self.expect('Password:')
        self.sendline('casadiag')
        self.expect(self.prompt)
        self.sendline('tcpdump "-i any %s"' % opts)
        self.expect(pexpect.TIMEOUT, timeout=time)
        self.sendcontrol('c')
        self.expect(self.prompt)
        self.sendline('exit')
        self.expect(self.prompt)

    def del_file(self, f):
        self.sendline('del %s' % f)
        self.expect(self.prompt)

if __name__ == '__main__':
    import time

    connection_type = "local_cmd"
    cmts = CasaCMTS(conn_cmd=sys.argv[1], connection_type=connection_type)
    cmts.connect()

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
    cmts.add_ip_bundle(1, "192.168.200.1", "192.168.201.1", "192.168.3.1")

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
