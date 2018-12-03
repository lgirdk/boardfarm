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
    ssid_name = None
    pass_word = None

    def setupTest(self):
        try:
            self.ssid_name = self.config.board['common']['ssid_name']
            self.pass_word = self.config.board['common']['pass_word']
        except:
            logfile_assert_message (self, False, "ssid_name and password must be specified in the .json 'common' section")

    def runTest(self):

        self.setupTest()

        board.expect(pexpect.TIMEOUT, timeout=50)
        """"Checking wifi connectivity"""
        wifi_name = ['wifi_2G','wifi_5G']
        for wifi_device in wifi_name:
            '''Scanning for SSID'''
            output = WifiScan(self).runTest()
            '''Matching the unique SSID'''
            match = re.search(self.ssid_name,output)
            logfile_assert_message(self, match!=None,'SSID value check in WLAN container')

            '''Checking for interface status'''
            link = wlan.link_up()
            if match==None:
                wlan.sendline("ip link set wlan up")
                wlan.expect(prompt)
                logfile_assert_message(self, True,'Setting Link up')
            else:
                logfile_assert_message(self, True,'Link is up')

            '''Generate WPA supplicant file and execute it'''
            conn_wpa = wlan.wpa_connect(self.ssid_name,self.pass_word)
            logfile_assert_message(self, conn_wpa!=None,'WPA supplicant initiation')

            '''Check wlan connectivity'''
            board.expect(pexpect.TIMEOUT, timeout=20)
            conn_wlan = wlan.wlan_connect(self.ssid_name)
            logfile_assert_message(self, conn_wlan!=None,'Connection establishment in WIFI')
            wlan.sendline("dhclient -v wlan1")
            wlan.expect(prompt,timeout=40)

            '''Ping gateway test'''
            wlan.sendline("ifconfig wlan1")
            wlan.expect(prompt)
            if_config_res = wlan.before
            match = re.search(r'inet ([0-9]+\.[0-9]+\.[0-9]+)\.([0-9]+).*',if_config_res)
            logfile_assert_message(self, match!=None,'Ifconfig wlan IP fetch')
            gateway_ip = match.group(1) + ".1"
            ip = match.group(2)
            value = range(2,255)
            match = re.search(ip,str(value))
            logfile_assert_message(self, match!=None,'Ifconfig wlan IP verify')

            for host in {gateway_ip,"google.com"}:
                wlan.sendline("ping -c 1 %s" % host)
                wlan.expect(prompt)
                ping_res = wlan.before
                match = re.search('1 packets transmitted, 1 received, 0% packet loss' , ping_res)
                logfile_assert_message(self, match!=None,'Ping status')

            '''Kill the wpa supplicant'''
            wlan.kill_supplicant()

            self.cleanupTest()

    def cleanupTest(self):
        self.recover()
        logfile_assert_message(self, True, "Nothing to do with cleanup")

    def recover(self):
        '''Kill the wpa supplicant'''
        wlan.kill_supplicant()

