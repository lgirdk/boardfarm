# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

import random
import re
import string
import time

wlan_iface = None

def wifi_interface(console):
    global wlan_iface

    if wlan_iface is None:
        console.sendline('uci show wireless | grep wireless.*0.*type=')
        i = console.expect(["type='?mac80211'?", "type='?qcawifi'?"])
        if i == 0:
            wlan_iface = "wlan0"
        elif i == 1:
            wlan_iface = "ath0"
        else:
            wlan_iface = None

    return wlan_iface

def randomSSIDName():
    return 'WIFI-' + ''.join(random.sample(string.lowercase+string.digits,10))

def uciSetWifiSSID(console, ssid):
    console.sendline('uci set wireless.@wifi-iface[0].ssid=%s; uci commit wireless; wifi' % ssid)
    console.expect_prompt()

def uciSetWifiMode(console, radio, hwmode):
    console.sendline('uci set wireless.wifi%s.hwmode=%s; uci commit wireless' % (radio, hwmode))
    console.expect_prompt()

def uciSetChannel(console, radio, channel):
    console.sendline('uci set wireless.wifi%s.channel=%s; uci commit wireless' % (radio, channel))
    console.expect_prompt()

def enable_wifi(board, index=0):
    board.sendline('\nuci set wireless.@wifi-device[%s].disabled=0; uci commit wireless' % index)
    board.expect('uci set')
    board.expect_prompt()
    board.sendline('wifi')
    board.expect('wifi')
    board.expect_prompt(timeout=50)
    time.sleep(20)

def enable_all_wifi_interfaces(board):
    '''Find all wireless interfaces, and enable them.'''
    board.sendline('\nuci show wireless | grep disabled')
    board.expect('grep disabled')
    board.expect_prompt()
    # The following re.findall should return list of settings:
    # ['wireless.radio0.disabled', 'wireless.radio1.disabled']
    settings = re.findall('([\w\.]+)=\d', board.before)
    for s in settings:
        board.sendline('uci set %s=0' % s)
        board.expect_prompt()
    board.sendline('uci commit wireless')
    board.expect_prompt()
    board.sendline('wifi')
    board.expect_prompt(timeout=50)

def disable_wifi(board, wlan_iface="ath0"):
    board.sendline('uci set wireless.@wifi-device[0].disabled=1; uci commit wireless')
    board.expect('uci set')
    board.expect_prompt()
    board.sendline('wifi')
    board.expect_prompt()
    board.sendline('iwconfig %s' % wlan_iface)
    board.expect_prompt()

def wifi_on(board):
    '''Return True if WiFi is enabled.'''
    board.sendline('\nuci show wireless.@wifi-device[0].disabled')
    try:
        board.expect('disabled=0', timeout=5)
        board.expect_prompt()
        return True
    except:
        return False

def wifi_get_info(board, wlan_iface):
    try:
        if "ath" in wlan_iface:
            board.sendline('iwconfig %s' % wlan_iface)
            board.expect('ESSID:"(.*)"')
            essid = board.match.group(1)
            board.expect("Frequency:([^ ]+)")
            freq = board.match.group(1)
            essid = board.match.group(1)
            board.expect('Bit Rate[:=]([^ ]+) ')
            rate = float(board.match.group(1))
            board.expect_prompt()
            # TODO: determine channel
            channel = -1.0
        elif "wlan" in wlan_iface:
            board.sendline("iwinfo wlan0 info")
            board.expect('ESSID: "(.*)"')
            essid = board.match.group(1)
            board.expect('Channel:\s*(\d+)\s*\(([\d\.]+)\s*GHz')
            channel = int(board.match.group(1))
            freq = float(board.match.group(2))
            board.expect('Bit Rate: ([^ ]+)')
            try:
                rate = float(board.match.group(1))
            except:
                rate = -1.0
            board.expect_prompt()
        else:
            print("Unknown wireless type")
    except:
        board.sendline('dmesg')
        board.expect_prompt()
        raise

    return essid, channel, rate, freq

def wait_wifi_up(board, num_tries=10, sleep=15, wlan_iface="ath0"):
    '''Wait for WiFi Bit Rate to be != 0.'''
    for i in range(num_tries):
        time.sleep(sleep)
        essid, channel, rate, freq = wifi_get_info(board, wlan_iface)
        if "ath" in wlan_iface and rate > 0:
            return
        if "wlan" in wlan_iface == "wlan0" and essid != "" and channel != 0 and freq != 0.0:
            return

    if rate == 0:
        print("\nWiFi did not come up. Bit Rate still 0.")
        assert False

def wifi_add_vap(console, phy, ssid):
    console.sendline('uci add wireless wifi-iface')
    console.expect_prompt()
    console.sendline('uci set wireless.@wifi-iface[-1].device="%s"' % phy)
    console.expect_prompt()
    console.sendline('uci set wireless.@wifi-iface[-1].network="lan"')
    console.expect_prompt()
    console.sendline('uci set wireless.@wifi-iface[-1].mode="ap"')
    console.expect_prompt()
    console.sendline('uci set wireless.@wifi-iface[-1].ssid="%s"' % ssid)
    console.expect_prompt()
    console.sendline('uci set wireless.@wifi-iface[-1].encryption="none"')
    console.expect_prompt()
    console.sendline('uci commit')
    console.expect_prompt()

def wifi_del_vap(console, index):
    console.sendline('uci delete wireless.@wifi-iface[%s]' % index)
    console.expect_prompt()
    console.sendline('uci commit')
    console.expect_prompt()

def uciSetWifiSecurity(board, vap_iface, security):
    if security.lower() in ['none']:
        print("Setting security to none.")
        board.sendline('uci set wireless.@wifi-iface[%s].encryption=none' % vap_iface)
        board.expect_prompt()
    elif security.lower() in ['wpa-psk']:
        print("Setting security to WPA-PSK.")
        board.sendline('uci set wireless.@wifi-iface[%s].encryption=psk+tkip' % vap_iface)
        board.expect_prompt()
        board.sendline('uci set wireless.@wifi-iface[%s].key=1234567890abcdexyz' % vap_iface)
        board.expect_prompt()
    elif security.lower() in ['wpa2-psk']:
        print("Setting security to WPA2-PSK.")
        board.sendline('uci set wireless.@wifi-iface[%s].encryption=psk2+ccmp' % vap_iface)
        board.expect_prompt()
        board.sendline('uci set wireless.@wifi-iface[%s].key=1234567890abcdexyz' % vap_iface)
        board.expect_prompt()

class wifi_stub():
    apply_changes_no_delay = True
    # The above variable can tweak the behavior of the below functions
    # If it is set to True, it will apply the changes after setting wifi parameters
    # If it is set to False, it will not save any changes & apply_changes() will be skipped
    def enable_wifi(self, *args, **kwargs):
        raise Exception("Not implemented!")
    def set_ssid(self, *args, **kwargs):
        raise Exception("Not implemented!")
    def set_broadcast(self, *args, **kwargs):
        raise Exception("Not implemented!")
    def set_security(self, *args, **kwargs):
        raise Exception("Not implemented!")
    def set_password(self, *args, **kwargs):
        raise Exception("Not implemented!")
    def enable_channel_utilization(self, *args, **kwargs):
        raise Exception("Not implemented!")
    def set_operating_mode(self, *args, **kwargs):
        raise Exception("Not implemented!")
    def set_bandwidth(self, *args, **kwargs):
        raise Exception("Not implemented!")
    def set_channel_number(self, *args, **kwargs):
        raise Exception("Not implemented!")
    def get_wifi_enabled(self, *args, **kwargs):
        raise Exception("Not implemented!")
    def get_ssid(self, *args, **kwargs):
        raise Exception("Not implemented!")
    def get_security(self, *args, **kwargs):
        raise Exception("Not implemented!")
    def get_password(self, *args, **kwargs):
        raise Exception("Not implemented!")
    def get_channel_utilization(self, *args, **kwargs):
        raise Exception("Not implemented!")
    def get_operating_mode(self, *args, **kwargs):
        raise Exception("Not implemented!")
    def get_bandwidth(self, *args, **kwargs):
        raise Exception("Not implemented!")
    def get_broadcast(self, *args, **kwargs):
        raise Exception("Not implemented!")
    def get_channel_number(self, *args, **kwargs):
        raise Exception("Not implemented!")
    def prepare(self):
        pass
    def cleanup(self):
        pass
    def apply_changes(self):
        '''This function used to save the configs to be modified'''
        pass

class wifi_client_stub():
    def enable_wifi(self):
        '''Function to make the wifi interface UP'''
        raise Exception("Not implemented!")
    def disable_wifi(self):
        '''Function to make the wifi interface DOWN'''
        raise Exception("Not implemented!")
    def disable_and_enable_wifi(self):
        '''Function to make the wifi interface DOWN and UP'''
        raise Exception("Not implemented!")
    def wifi_scan(self):
        '''Function that scans for SSIDs on a particular radio, and return a list of SSID'''
        raise Exception("Not implemented!")
        # this code does not execute, but rather serves as an example for the API
        return "SSID: <ssid_name1> \
                SSID: <ssid_name2>.."
    def wifi_check_ssid(self, ssid_name):
        '''Function that scans for a particular SSID
           Takes ssid to be scanned as an argument'''
        raise Exception("Not implemented!")
        # this code does not execute, but rather serves as an example for the API
        return True  # if found
        return False # if not found
    def wifi_connect(self, ssid_name, password, security_mode):
        '''Function to connect to wifi either with ssid name and password or with ssid name alone
           Takes arguments as SSID and (password,security) if required'''
        raise Exception("Not implemented!")
    def wifi_connectivity_verify(self):
        '''Function to verify wifi connectivity
           Returns True or False based on connectivity'''
        raise Exception("Not implemented!")
        # this code does not execute, but rather serves as an example for the API
        return "True or False"
    def wifi_disconnect(self):
        '''Function to disconnect wifi'''
        raise Exception("Not implemented!")
    def wifi_change_region(self, country):
        '''Function to change the country
           Takes country name as an argument Eg:Germany
           Return the country code Eg: Germany as DE'''
        raise Exception("Not implemented!")
        return "DE"
