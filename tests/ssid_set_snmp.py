# Copyright (c) 2017
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import os, datetime, pexpect, config
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
                set_ssid_name = 'SSIDwifi_2G'
            elif wifi_device == 'wifi_5g':
                self.index = '.92'
                set_ssid_name = 'SSIDwifi_5G'
            """Set SSID via SNMP"""
            ssid_name = config.board['station']+set_ssid_name
            wifi_pass = config.wifi_password[0]
            wan.sendline("snmpset -v 2c -c private -t 30 -r 3 "+wan_ip+" "+board.mib["wifiMgmtBssSsid"]+self.index+" s "+str(ssid_name))
            idx = wan.expect(['Timeout: No Response from'] + ['STRING: "(.*)"\r\n'])
            logfile_assert_message(self, idx==0,'Setting the SSID using mib wifiMgmtBssSsid)')
            wan.expect(prompt)
            """Set Password via SNMP"""
            wan.sendline("snmpset -v 2c -c private -t 30 -r 3 "+wan_ip+" "+board.mib["wifiMgmtBssWpaPreSharedKey"]+self.index+" s "+str(wifi_pass))
            idx = wan.expect(['Timeout: No Response from'] + ['STRING: "(.*)"'])
            logfile_assert_message(self, idx==0,'Setting the passowrd using mib wifiMgmtBssWpaPreSharedKey)')
            wan.expect(prompt)
            """Get SSID via SNMP"""
            wan.sendline("snmpget -v 2c -c public -t 30 -r 3 "+wan_ip+" "+board.mib["wifiMgmtBssSsid"]+self.index)
            idx = wan.expect(['Timeout: No Response from'] + [ssid_name])
            logfile_assert_message(self, idx==0,'Getting the SSID using mib wifiMgmtBssSsid)')
            wan.expect(prompt)
            self.log_to_file += now_short()+"Ssid = %s\r\n" %ssid_name
            """Get Password via SNMP"""
            wan.sendline("snmpget -v 2c -c public -t 30 -r 3 "+wan_ip+" "+board.mib["wifiMgmtBssWpaPreSharedKey"]+self.index)
            idx = wan.expect(['Timeout: No Response from'] + [wifi_pass])
            logfile_assert_message(self, idx==0,'Getting the SSID using mib wifiMgmtBssWpaPreSharedKey)')
            wan.expect(prompt)
        """Apply the settings globally"""
        wan.sendline("snmpset -v 2c -c private -t 30 -r 3 "+wan_ip+" "+board.mib["wifiMgmtApplySettings"]+'.0'+" i "+'1')
        idx = wan.expect(['Timeout: No Response from'] + ['INTEGER: 1'],timeout=120)
        logfile_assert_message(self, idx==0,'Setting the SSID using mib wifiMgmtApplySettings)')
        wan.expect(prompt)
        board.expect(pexpect.TIMEOUT, timeout=25)
        return wifi_pass
