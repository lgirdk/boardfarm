# Copyright (c) 2017
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.

import os, datetime, pexpect, config, re
import rootfs_boot
from devices import board, wan, lan, wlan, prompt
from lib.installers import install_snmp
from wifi import WifiScan
from lib.logging import logfile_assert_message

class scan_ssid_wifi(rootfs_boot.RootFSBootTest):
    log_to_file = ""

    def WifiTest(self,ssid_name,pass_word):
        board.expect(pexpect.TIMEOUT, timeout=50)

        """"Checking wifi connectivity"""
        wifi_name = ['wifi_2G','wifi_5G']
        for wifi_device in wifi_name:
            '''Scanning for SSID'''
            output = WifiScan(self).runTest()
            '''Matching the unique SSID'''
            match = re.search(ssid_name,output)
            logfile_assert_message(self, match!=None,'SSID value check in WLAN container')

            '''Checking for interface status'''
            wlan.link_up()

            '''Generate WPA supplicant file and execute it'''
            wlan.wpa_connect(ssid_name,pass_word)

            '''Check wlan connectivity'''
            wlan.wlan_connect(ssid_name)

            '''Ping gateway test'''
            wlan.ping_gateway()

            '''Ping hostname test'''
            wlan.ping_hostname()

            '''Kill the wpa supplicant'''
            wlan.kill_supplicant()

