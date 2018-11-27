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
from cbnlib import now_short
from wifi import WifiScan
from ssid_set_snmp import SSIDSetSnmp
from lib.logging import logfile_assert_message

class scan_ssid_wifi(rootfs_boot.RootFSBootTest):
    log_to_file = ""

    def WifiTest(self):
        board.expect(pexpect.TIMEOUT, timeout=60)
        
        """"Checking wifi connectivity"""
        wifi_name = ['wifi_2G','wifi_5G']
        for wifi_device in wifi_name:
            '''Scanning for SSID'''
            output = WifiScan(self).runTest()
            
            '''Matching the unique SSID'''
            match = re.search(ssid_name,output)
            logfile_assert_message(self, match!=None,'SSID value check in WLAN container')

            '''Checking for interface status'''
            self.link_up()
            
            '''Generate WPA supplicant file and execute it'''
            self.wpa_connect(ssid_name,pass_word)

            '''Check wlan connectivity'''
            self.wlan_connect(ssid_name)

            '''Ping gateway test'''
            self.ping_gateway()

            '''Ping hostname test'''
            self.ping_hostname()

            wlan.sendline("killall wpa_supplicant")
            wlan.expect(prompt)
           
    def wpa_connect(self,ssid_name,pass_word):
         '''Generate WPA supplicant file and execute it'''
         wlan.sendline("rm /etc/"+ssid_name+".conf")
         wlan.expect(prompt)
         wlan.sendline("wpa_passphrase "+ssid_name+ " >> /etc/"+ssid_name+".conf")
         wlan.expect("")
         wlan.sendline(pass_word)
         wlan.expect(prompt)
         wlan.sendline("cat /etc/"+ssid_name+".conf")
         wlan.expect(prompt)
         wlan.sendline("wpa_supplicant  -B -Dnl80211 -iwlan1 -c/etc/"+ssid_name+".conf")
         wlan.expect(prompt)
            
    def wlan_connect(self,ssid_val):
        board.expect(pexpect.TIMEOUT, timeout=25)
        '''Connection state verify'''
        wlan.sendline("iw wlan1 link")
        wlan.expect(prompt)
        conn_state = wlan.before
        match = re.search('Connected',conn_state)
        logfile_assert_message(self, match!=None,'Connection establishment in WIFI')
        match = re.search(ssid_val,conn_state)
        logfile_assert_message(self, match!=None,'Connection establishment - SSID verify')
        wlan.sendline("dhclient -v wlan1")
        wlan.expect(prompt,timeout=40)
        
    def ping_hostname(self):
        '''Ping test'''
        hostname = "google.com"
        wlan.sendline("ping -c 1 " + hostname)
        wlan.expect(prompt)
        ping_result = wlan.before
        match = re.search("1 packets transmitted, 1 received, 0% packet loss",ping_result)
        logfile_assert_message(self, match!=None,'Host Ping status')
    
     def ping_gateway(self):
        wlan.sendline("ifconfig wlan1")
        wlan.expect(prompt)
        ifconfig_res = wlan.before
        match = re.search(r'inet ([0-9]+\.[0-9]+\.[0-9]+)\.([0-9]+).*',ifconfig_res)
        logfile_assert_message(self, match!=None,'Ifconfig wlan IP fetch')
        gateway_ip = match.group(1) + ".1"
        ip = match.group(2)
        value = range(2,255)
        match = re.search(ip,str(value))
        logfile_assert_message(self, match!=None,'Ifconfig wlan IP verify')
        wlan.sendline("ping -c 1 " + gateway_ip)
        wlan.expect(prompt)
        ping_res = wlan.before
        match = re.search("1 packets transmitted, 1 received, 0% packet loss",ping_res)
        logfile_assert_message(self, match!=None,'Gateway Ping status')
        
    def link_up(self):
        wlan.sendline("ip link show wlan1")
        wlan.expect(prompt)
        link_state = wlan.before
        match = re.search('NO-CARRIER,BROADCAST,MULTICAST,UP',link_state)
        if match:
            self.log_to_file += now_short()+"Interface is UP: PASS\r\n"
        else:
            wlan.sendline("ip link set wlan1 up")
            wlan.expect(prompt)
            self.log_to_file += now_short()+"Interface is set UP\r\n"

           
