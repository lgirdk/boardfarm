# Copyright (c) 2017
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import os, datetime, pexpect, config, re
import rootfs_boot
from devices import board, wan, lan, prompt
from lib.installers import install_snmp
from cbnlib import now_short
from lib.logging import logfile_assert_message

class snmp_mibs(rootfs_boot.RootFSBootTest):
    '''Setting and getting snmp mibs for Wi-Fi'''
    '''mib_name has to be passed with mib name'''
    '''index has to passed with a . value ex:.32'''
    '''set_arg,get_arg can be passed as set or get respectively'''
    '''set_value is the value to be set for the mib'''

    log_to_file = ""
    set_ssid_name = None
    index = None
    def mib_parameter(self,mib_name,index,set_arg,get_arg,set_value):
        install_snmp(wan)
        wan_ip = board.get_interface_ipaddr(board.wan_iface)
        if mib_name == "wifiMgmtBssSecurityMode" \
           or mib_name == "wifiMgmtWpsMethod" or mib_name == "wifiMgmtBssNetMode" \
           or mib_name == "wifiMgmtBssEnable" or mib_name == "wifiMgmtBandWidth" \
           or mib_name == "wifiMgmtBssAccessMode":
            set_type = "i"
        elif mib_name == "wifiMgmtBssSsid" or mib_name == "wifiMgmtBssWpaPreSharedKey":
            set_type = "s"
        if set_type == "i":
            set_var = "INTEGER"
            idx = re.search(r'([a-zA-Z])',str(set_value))
            logfile_assert_message(self, idx==None,'Setting the mib %s'% mib_name)
        elif set_type == "s":
            set_var = "STRING"
            if set_arg == "set":
                if mib_name == "wifiMgmtBssWpaPreSharedKey":
                    idx = re.search('(?=\S{10})(?=.*?[a-z])(?=.*?[A-Z])(?=.*?[0-9])',str(set_value))
                    logfile_assert_message(self, idx!=None,'Setting the mib %s'% mib_name)
                else:
                    idx = re.search(r'([0-9])',str(set_value))
                    logfile_assert_message(self, idx==None,'Setting the mib %s'% mib_name)
        if set_arg == "set":
            get_arg = "get"
            wan.sendline("snmpset -v 2c -c private -t 30 -r 3 "+wan_ip+" "+board.mib[mib_name]+index+" "+set_type+" "+str(set_value))
            idx = wan.expect(['Timeout: No Response from'] + [set_var+': (.*)\r\n'])
            logfile_assert_message(self, idx!=0,'Setting the mib %s'% mib_name)
            wan.expect(prompt)
        if get_arg == "get":
            """Get Password via SNMP"""
            wan.sendline("snmpget -v 2c -c public -t 30 -r 3 "+wan_ip+" "+board.mib[mib_name]+index)
            idx = wan.expect(['Timeout: No Response from'] + [set_var+': (.*)\r\n'])
            logfile_assert_message(self, idx!=0,'Getting the mib %s'% mib_name)
            wan.expect(prompt)
