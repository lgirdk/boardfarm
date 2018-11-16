# Copyright (c) 2017
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import os, datetime, pexpect
import rootfs_boot
from devices import board, wan, lan, prompt
from lib.installers import install_snmp
from cbnlib import now_short

class SSIDSetSnmp(rootfs_boot.RootFSBootTest):
    '''Setting unique SSID'''
    log_to_file = ""
    set_ssid_name = None
    index = None
    def runTest(self):
        install_snmp(wan)
        wan_ip = board.get_interface_ipaddr(board.wan_iface)
        """"setting ssid for wifi"""
        wifi_name = ['wifi_2g','wifi_5g']
        for wifi_device in wifi_name:
            if wifi_device == 'wifi_2g':
                self.index = '.32'
                self.set_ssid_name = 'SSIDwifi_2G'
            elif wifi_device == 'wifi_5g':
                self.index = '.92'
                self.set_ssid_name = 'SSIDwifi_5G'

            """Set SSID via SNMP"""
            ssid_name = self.config.board['station']+self.set_ssid_name
            wan.sendline("snmpset -v 2c -c private -t 30 -r 3 "+wan_ip+" "+board.mib["wifiMgmtBssSsid"]+self.index+" s "+str(ssid_name))
            assert 0 != wan.expect(['Timeout: No Response from'] + ['STRING: "(.*)"\r\n'])
            wan.expect(prompt)
            wan.sendline("snmpget -v 2c -c public -t 30 -r 3 "+wan_ip+" "+board.mib["wifiMgmtBssSsid"]+self.index)
            assert 0 != wan.expect(['Timeout: No Response from'] + [ssid_name])
            wan.expect(prompt)
            self.log_to_file += now_short()+"Ssid = %s\r\n" %ssid_name
