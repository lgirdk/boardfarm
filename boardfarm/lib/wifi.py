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
    """This method returns the wifi interface

    :param console: CM console object
    :type console: object
    :returns: The wlan_iface of the modem wlan0/ath0 or None
    :rtype: string
    """
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
    """This method returns the random SSID name used to set on CM

    :returns: The SSID generated randomly
    :rtype: string
    """
    return 'WIFI-' + ''.join(random.sample(string.ascii_lowercase + string.digits, 10))

def uciSetWifiSSID(console, ssid):
    """This method sets the WiFi SSID on the CM

    :param console: CM console object
    :type console: object
    :param ssid: SSID to be used to set on CM
    :type ssid: string
    """
    console.sendline('uci set wireless.@wifi-iface[0].ssid=%s; uci commit wireless; wifi' % ssid)
    console.expect_prompt()

def uciSetWifiMode(console, radio, hwmode):
    """This method sets the WiFi hwmode as per the radio over CM

    :param console: CM console object
    :type console: object
    :param radio: radio to set hwmode
    :type radio: string
    :param hwmode: hwmode to be set over the CM
    :type hwmode: string
    """
    console.sendline('uci set wireless.wifi%s.hwmode=%s; uci commit wireless' % (radio, hwmode))
    console.expect_prompt()

def uciSetChannel(console, radio, channel):
    """This method sets the channel as per the radio over CM

    :param console: CM console object
    :type console: object
    :param radio: radio to set hwmode
    :type radio: string
    :param channel: channel to be set over the CM
    :type channel: string
    """
    console.sendline('uci set wireless.wifi%s.channel=%s; uci commit wireless' % (radio, channel))
    console.expect_prompt()

def enable_wifi(board, index=0):
    """This method enables the WiFi as per the index specified.

    :param board: board object
    :type board: object
    :param index: index to be used to enable, defaults to 0
    :type index: int
    """
    board.sendline('\nuci set wireless.@wifi-device[%s].disabled=0; uci commit wireless' % index)
    board.expect('uci set')
    board.expect_prompt()
    board.sendline('wifi')
    board.expect('wifi')
    board.expect_prompt(timeout=50)
    time.sleep(20)

def enable_all_wifi_interfaces(board):
    """This method enables all the WiFi interface available over the board

    :param board: board object
    :type board: object
    """
    board.sendline('\nuci show wireless | grep disabled')
    board.expect('grep disabled')
    board.expect_prompt()
    # The following re.findall should return list of settings:
    # ['wireless.radio0.disabled', 'wireless.radio1.disabled']
    settings = re.findall(r'([\w\.]+)=\d', board.before)
    for s in settings:
        board.sendline('uci set %s=0' % s)
        board.expect_prompt()
    board.sendline('uci commit wireless')
    board.expect_prompt()
    board.sendline('wifi')
    board.expect_prompt(timeout=50)

def disable_wifi(board, wlan_iface="ath0"):
    """This method disables the WiFi over the interface specified

    :param board: board object
    :type board: object
    :param wlan_iface: the WiFi interface to be disabled defaults to "ath0"
    :type wlan_iface: string
    """
    board.sendline('uci set wireless.@wifi-device[0].disabled=1; uci commit wireless')
    board.expect('uci set')
    board.expect_prompt()
    board.sendline('wifi')
    board.expect_prompt()
    board.sendline('iwconfig %s' % wlan_iface)
    board.expect_prompt()

def wifi_on(board):
    """This method returns the WiFi enabled status over the CM True if enabled else False

    :param board: board object
    :type board: object
    :returns: The WiFi enabled status of the CM
    :rtype: boolean
    """
    board.sendline('\nuci show wireless.@wifi-device[0].disabled')
    try:
        board.expect('disabled=0', timeout=5)
        board.expect_prompt()
        return True
    except:
        return False

def wifi_get_info(board, wlan_iface):
    """This method gets the WiFi information about the board like essid, channel, rate, freq

    :param board: board object
    :type board: object
    :param wlan_iface: The WiFi interface to be used to get details.
    :type wlan_iface: string
    :raises: Assert Exception
    """
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
            board.expect(r'Channel:\s*(\d+)\s*\(([\d\.]+)\s*GHz')
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
    """This method waits for the WiFi Bit Rate to be != 0 default 10 trials with a wait of 15 seconds for each trial.

    :param board: board object
    :type board: object
    :param num_tries: number of trials, defaults to 10
    :type num_tries: int
    :param sleep: number of seconds to wait, defaults to 15
    :type sleep: int
    :param wlan_iface: Wireless interface to wait for, defaults to "ath0"
    :type wlan_iface: string
    :raises: Assert Exception
    """
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
    """This method adds virtual access point on the interface specified as per the ssid provided.

    :param console: console object
    :type console: object
    :param phy: physical interface to be used
    :type phy: string
    :param ssid: ssid to be set for VAP
    :type ssid: string
    """
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
    """This method deletes virtual access point on the interface specified as per the index provided.

    :param console: console object
    :type console: object
    :param index: index to be used
    :type index: int
    """
    console.sendline('uci delete wireless.@wifi-iface[%s]' % index)
    console.expect_prompt()
    console.sendline('uci commit')
    console.expect_prompt()

def uciSetWifiSecurity(board, vap_iface, security):
    """This method sets the WiFi security on the VAP interface on the board

    :param board: board object
    :type board: object
    :param vap_iface: interface to be used
    :type vap_iface: string
    :param security: security to be set
    :type security: string
    """
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
        """This method is stub for enabling wifi on CM

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def set_ssid(self, *args, **kwargs):
        """This method is stub to set SSID

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def set_broadcast(self, *args, **kwargs):
        """This method is stub to set boardcast

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def set_security(self, *args, **kwargs):
        """This method is stub to set security

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def set_password(self, *args, **kwargs):
        """This method is stub to set password

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def enable_channel_utilization(self, *args, **kwargs):
        """This method is stub to enable channel utilization

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def set_operating_mode(self, *args, **kwargs):
        """This method is stub to set operating mode

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def set_bandwidth(self, *args, **kwargs):
        """This method is stub to set bandwidth

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def set_channel_number(self, *args, **kwargs):
        """This method is stub to enable channel utilization

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def get_wifi_enabled(self, *args, **kwargs):
        """This method is stub to get WiFi enabled

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def get_ssid(self, *args, **kwargs):
        """This method is stub to get SSID

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def get_security(self, *args, **kwargs):
        """This method is stub to get security mode

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def get_password(self, *args, **kwargs):
        """This method is stub to get password

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def get_channel_utilization(self, *args, **kwargs):
        """This method is stub to get channel utilization

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def get_operating_mode(self, *args, **kwargs):
        """This method is stub to get operating mode

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def get_bandwidth(self, *args, **kwargs):
        """This method is stub to get bandwidth

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def get_broadcast(self, *args, **kwargs):
        """This method is stub to get the broadcast

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def get_channel_number(self, *args, **kwargs):
        """This method is stub to get the channel number

        :param self: self object
        :type self: object
        :param args: arguments to be used if any
        :type args: NA
        :param kwargs: extra arguments to be used
        :type kwargs: NA
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def prepare(self):
        """This method is stub

        :param self: self object
        :type self: object
        """
        pass

    def cleanup(self):
        """This method is stub

        :param self: self object
        :type self: object
        """
        pass

    def apply_changes(self):
        """This method is stub used to save the configs to be modified

        :param self: self object
        :type self: object
        """
        pass

class wifi_client_stub():
    def enable_wifi(self):
        """This method is WiFi client stub used to enable WiFi/ make the WiFi interface UP

        :param self: self object
        :type self: object
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def disable_wifi(self):
        """This method is WiFi client stub used to enable WiFi/ make the WiFi interface DOWN

        :param self: self object
        :type self: object
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def disable_and_enable_wifi(self):
        """This method is WiFi client stub used to disbale and enable WiFi/ make the WiFi interface DOWN and UP

        :param self: self object
        :type self: object
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def wifi_scan(self):
        """This method is WiFi client stub used to scan for SSIDs on a particular radio, and return a list of SSID

        :param self: self object
        :type self: object
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")
        # this code does not execute, but rather serves as an example for the API
        return "SSID: <ssid_name1> \
                SSID: <ssid_name2>.."

    def wifi_check_ssid(self, ssid_name):
        """This method is WiFi client stub used to scan for paticular SSID

        :param self: self object
        :type self: object
        :param ssid_name: ssid name to be scanned for
        :type ssid_name: string
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")
        # this code does not execute, but rather serves as an example for the API
        return True  # if found
        return False  # if not found

    def wifi_connect(self, ssid_name, password, security_mode):
        """This method is WiFi client stub used to connect to wifi either with ssid name and password or with ssid name alone

        :param self: self object
        :type self: object
        :param ssid_name: ssid name to be scanned for
        :type ssid_name: string
        :param password: password to be used to connect to SSID
        :type password: string
        :param security_mode: security mode of WiFi
        :type security_mode: string
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def wifi_connectivity_verify(self):
        """This method is WiFi client stub used to verify wifi connectivity

        :param self: self object
        :type self: object
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")
        # this code does not execute, but rather serves as an example for the API
        return "True or False"

    def wifi_disconnect(self):
        """This method is WiFi client stub used to disconnect WiFi

        :param self: self object
        :type self: object
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")

    def wifi_change_region(self, country):
        """This method is WiFi client stub used to change the country

        :param self: self object
        :type self: object
        :param country: country to change to
        :type country: string
        :raises: Exception "Not implemented"
        """
        raise Exception("Not implemented!")
        return "DE"
