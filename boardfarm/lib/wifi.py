# Copyright (c) 2015
#
# All rights reserved.
#
# This file is distributed under the Clear BSD license.
# The full text can be found in LICENSE in the root directory.
# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4
"""Global Functions related to wifi."""
import logging
import random
import re
import string
import time

from boardfarm.lib.wifi_lib.stubs import WiFiClientStub, WiFiStub

logger = logging.getLogger("bft")
wlan_iface = None
wifi_stub = WiFiStub
wifi_client_stub = WiFiClientStub


def wifi_interface(console):
    """wifi_interface : Returns the wifi interface.

    :param console: CM console object
    :type console: object
    :returns: The wlan_iface of the modem wlan0/ath0 or None
    :rtype: string
    """
    global wlan_iface

    if wlan_iface is None:
        console.sendline("uci show wireless | grep wireless.*0.*type=")
        i = console.expect(["type='?mac80211'?", "type='?qcawifi'?"])
        if i == 0:
            wlan_iface = "wlan0"
        elif i == 1:
            wlan_iface = "ath0"
        else:
            wlan_iface = None

    return wlan_iface


def randomSSIDName():
    """Return the random SSID name used to set on CM.

    :returns: The SSID generated randomly
    :rtype: string
    """
    random_val = random.sample(string.ascii_lowercase, 8) + random.sample(
        string.digits, 2
    )
    random.shuffle(random_val)
    return "WIFI-" + "".join(random_val)


def uciSetWifiSSID(console, ssid):
    """Set the WiFi SSID on the CM.

    :param console: CM console object
    :type console: object
    :param ssid: SSID to be used to set on CM
    :type ssid: string
    """
    console.sendline(
        f"uci set wireless.@wifi-iface[0].ssid={ssid}; uci commit wireless; wifi"
    )
    console.expect_prompt()


def uciSetWifiMode(console, radio, hwmode):
    """Set the WiFi hwmode as per the radio over CM.

    :param console: CM console object
    :type console: object
    :param radio: radio to set hwmode
    :type radio: string
    :param hwmode: hwmode to be set over the CM
    :type hwmode: string
    """
    console.sendline(
        f"uci set wireless.wifi{radio}.hwmode={hwmode}; uci commit wireless"
    )
    console.expect_prompt()


def uciSetChannel(console, radio, channel):
    """Set the channel as per the radio over CM.

    :param console: CM console object
    :type console: object
    :param radio: radio to set hwmode
    :type radio: string
    :param channel: channel to be set over the CM
    :type channel: string
    """
    console.sendline(
        f"uci set wireless.wifi{radio}.channel={channel}; uci commit wireless"
    )
    console.expect_prompt()


def enable_wifi(board, index=0):
    """Enable the WiFi as per the index specified.

    :param board: board object
    :type board: object
    :param index: index to be used to enable, defaults to 0
    :type index: int
    """
    board.sendline(
        f"\nuci set wireless.@wifi-device[{index}].disabled=0; uci commit wireless"
    )
    board.expect("uci set")
    board.expect_prompt()
    board.sendline("wifi")
    board.expect("wifi")
    board.expect_prompt(timeout=50)
    time.sleep(20)


def enable_all_wifi_interfaces(board):
    """Enable all the WiFi interface available over the board.

    :param board: board object
    :type board: object
    """
    board.sendline("\nuci show wireless | grep disabled")
    board.expect("grep disabled")
    board.expect_prompt()
    """
    The following re.findall should return list of settings:
    ['wireless.radio0.disabled', 'wireless.radio1.disabled']
    """
    settings = re.findall(r"([\w\.]+)=\d", board.before)
    for s in settings:
        board.sendline(f"uci set {s}=0")
        board.expect_prompt()
    board.sendline("uci commit wireless")
    board.expect_prompt()
    board.sendline("wifi")
    board.expect_prompt(timeout=50)


def disable_wifi(board, wlan_iface="ath0"):
    """Disables the WiFi over the interface specified.

    :param board: board object
    :type board: object
    :param wlan_iface: the WiFi interface to be disabled defaults to "ath0"
    :type wlan_iface: string
    """
    board.sendline("uci set wireless.@wifi-device[0].disabled=1; uci commit wireless")
    board.expect("uci set")
    board.expect_prompt()
    board.sendline("wifi")
    board.expect_prompt()
    board.sendline(f"iwconfig {wlan_iface}")
    board.expect_prompt()


def wifi_on(board):
    """Return the WiFi enabled status over the CM.

    True if enabled else False.

    :param board: board object
    :type board: object
    :returns: The WiFi enabled status of the CM
    :rtype: boolean
    """
    board.sendline("\nuci show wireless.@wifi-device[0].disabled")
    try:
        board.expect("disabled=0", timeout=5)
        board.expect_prompt()
        return True
    except Exception:
        return False


def wifi_get_info(board, wlan_iface):
    """Get the WiFi information about the board.

     like essid, channel, rate, freq
    :param board: board object
    :type board: object
    :param wlan_iface: The WiFi interface to be used to get details.
    :type wlan_iface: string
    :raises: Assert Exception
    """
    try:
        if "ath" in wlan_iface:
            board.sendline(f"iwconfig {wlan_iface}")
            board.expect('ESSID:"(.*)"')
            essid = board.match.group(1)
            board.expect("Frequency:([^ ]+)")
            freq = board.match.group(1)
            essid = board.match.group(1)
            board.expect("Bit Rate[:=]([^ ]+) ")
            rate = float(board.match.group(1))
            board.expect_prompt()
            # TODO: determine channel
            channel = -1.0
        elif "wlan" in wlan_iface:
            board.sendline("iwinfo wlan0 info")
            board.expect('ESSID: "(.*)"')
            essid = board.match.group(1)
            board.expect(r"Channel:\s*(\d+)\s*\(([\d\.]+)\s*GHz")
            channel = int(board.match.group(1))
            freq = float(board.match.group(2))
            board.expect("Bit Rate: ([^ ]+)")
            try:
                rate = float(board.match.group(1))
            except Exception:
                rate = -1.0
            board.expect_prompt()
        else:
            logger.error("Unknown wireless type")
    except Exception:
        board.sendline("dmesg")
        board.expect_prompt()
        raise

    return essid, channel, rate, freq


def wait_wifi_up(board, num_tries=10, sleep=15, wlan_iface="ath0"):
    """Wait for the WiFi Bit Rate to be != 0.

     default 10 trials with a wait of 15 seconds for each trial.

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
    for _ in range(num_tries):
        time.sleep(sleep)
        essid, channel, rate, freq = wifi_get_info(board, wlan_iface)
        if "ath" in wlan_iface and rate > 0:
            return
        if (
            "wlan" in wlan_iface == "wlan0"
            and essid != ""
            and channel != 0
            and freq != 0.0
        ):
            return

    if rate == 0:
        logger.error("\nWiFi did not come up. Bit Rate still 0.")
        raise AssertionError(False)


def wifi_add_vap(console, phy, ssid):
    """Add virtual access point on the interface.

     specified as per the ssid provided.

    :param console: console object
    :type console: object
    :param phy: physical interface to be used
    :type phy: string
    :param ssid: ssid to be set for VAP
    :type ssid: string
    """
    console.sendline("uci add wireless wifi-iface")
    console.expect_prompt()
    console.sendline(f'uci set wireless.@wifi-iface[-1].device="{phy}"')
    console.expect_prompt()
    console.sendline('uci set wireless.@wifi-iface[-1].network="lan"')
    console.expect_prompt()
    console.sendline('uci set wireless.@wifi-iface[-1].mode="ap"')
    console.expect_prompt()
    console.sendline(f'uci set wireless.@wifi-iface[-1].ssid="{ssid}"')
    console.expect_prompt()
    console.sendline('uci set wireless.@wifi-iface[-1].encryption="none"')
    console.expect_prompt()
    console.sendline("uci commit")
    console.expect_prompt()


def wifi_del_vap(console, index):
    """Delete virtual access point on the interface specified as per the index provided.

    :param console: console object
    :type console: object
    :param index: index to be used
    :type index: int
    """
    console.sendline(f"uci delete wireless.@wifi-iface[{index}]")
    console.expect_prompt()
    console.sendline("uci commit")
    console.expect_prompt()


def uciSetWifiSecurity(board, vap_iface, security):
    """Set the WiFi security on the VAP interface on the board.

    :param board: board object
    :type board: object
    :param vap_iface: interface to be used
    :type vap_iface: string
    :param security: security to be set
    :type security: string
    """
    if security.lower() in ["none"]:
        logger.debug("Setting security to none.")
        board.sendline(f"uci set wireless.@wifi-iface[{vap_iface}].encryption=none")
        board.expect_prompt()
    elif security.lower() in ["wpa-psk"]:
        logger.debug("Setting security to WPA-PSK.")
        board.sendline(f"uci set wireless.@wifi-iface[{vap_iface}].encryption=psk+tkip")
        board.expect_prompt()
        board.sendline(
            f"uci set wireless.@wifi-iface[{vap_iface}].key=1234567890abcdexyz"
        )
        board.expect_prompt()
    elif security.lower() in ["wpa2-psk"]:
        logger.debug("Setting security to WPA2-PSK.")
        board.sendline(
            f"uci set wireless.@wifi-iface[{vap_iface}].encryption=psk2+ccmp"
        )
        board.expect_prompt()
        board.sendline(
            f"uci set wireless.@wifi-iface[{vap_iface}].key=1234567890abcdexyz"
        )
        board.expect_prompt()
