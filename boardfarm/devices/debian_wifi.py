"""Extension of Debian class with wifi functions."""
import ipaddress
import re

import pexpect
import pycountry
from debtcollector import moves

from boardfarm.lib.dns import DNS
from boardfarm.lib.installers import install_iw
from boardfarm.lib.linux_nw_utility import DHCP
from boardfarm.lib.wifi import wifi_client_stub

from . import debian_lan


class DebianWifi(debian_lan.DebianLAN, wifi_client_stub):
    """Extension of Debian class with wifi functions.

    wifi_client_stub is inherited from lib/wifi.py.
    """

    model = "debianwifi"

    def __init__(self, *args, **kwargs):
        """Initialise wifi interface."""

        # WLAN parameters
        self.band = kwargs.get("band", None)
        self.authentication = "NONE"

        self.parse_device_options(*args, **kwargs)
        self.iface_dut = self.iface_wifi = self.kwargs.get("dut_interface", "wlan1")

        # introducing same hack as lan_clients till json schema does not get updated
        if not self.dev_array:
            self.legacy_add = True
            self.dev_array = "wlan_clients"

        # This is being maintained for backward compatibility.
        # Ideally LAN network should be decided after connecting to SSID
        self.lan_network = ipaddress.IPv4Interface(
            kwargs.pop("lan_network", "192.168.1.0/24")
        ).network
        self.lan_gateway = ipaddress.IPv4Interface(
            kwargs.pop("lan_gateway", "192.168.1.1/24")
        ).ip

        self.dns = DNS(self, {}, {})
        self.dhcp = DHCP.get_dhcp_object("client", self)

    @moves.moved_method("reset_wifi_iface")
    def disable_and_enable_wifi(self):
        self.reset_wifi_iface()

    def reset_wifi_iface(self):
        """Disable and enable wifi interface.

        i.e., set the interface link to "down" and then to "up"
        This calls the disable wifi and enable wifi methods
        """
        self.disable_wifi()
        self.enable_wifi()

    def disable_wifi(self):
        """Disabling the wifi interface.

        setting the interface link to "down"
        """
        self.sudo_sendline("rm /etc/wpa_supplicant/{}".format(self.iface_wifi))
        self.expect(self.prompt)
        self.sudo_sendline("killall wpa_supplicant")
        self.expect(self.prompt)
        self.set_link_state(self.iface_wifi, "down")

    def enable_wifi(self):
        """Enable the wifi interface.

        setting the interface link to "up"
        """
        self.set_link_state(self.iface_wifi, "up")

    @moves.moved_method("dhcp_release_wlan_iface")
    def release_wifi(self):
        self.dhcp_release_wlan_iface()

    def dhcp_release_wlan_iface(self):
        """DHCP release of the wifi interface."""
        self.release_dhcp(self.iface_wifi)

    @moves.moved_method("dhcp_renew_wlan_iface")
    def renew_wifi(self):
        return self.dhcp_renew_wlan_iface()

    def dhcp_renew_wlan_iface(self):
        """DHCP renew of the wifi interface."""
        # Remove static ip if any
        self.sendline(f"ifconfig {self.iface_wifi} 0.0.0.0")
        self.expect(self.prompt)
        # Kill dhcp client
        self.sudo_sendline("kill -9 $(pgrep dhclient)")
        self.expect(self.prompt)

        try:
            self.renew_dhcp(self.iface_wifi)
            return True
        except pexpect.TIMEOUT:
            self.sendcontrol("c")
            self.expect(self.prompt)
            self.sudo_sendline("killall dhclient")
            self.expect(self.prompt)
            return False

    @moves.moved_method("set_wlan_scan_channel")
    def change_channel(self, channel):
        self.set_wlan_scan_channel(channel)

    def set_wlan_scan_channel(self, channel):
        """Change wifi client scan channel."""
        install_iw(self)

        self.sudo_sendline(f"iwconfig {self.iface_wifi} channel {channel}")
        self.expect(self.prompt)

    @moves.moved_method("iwlist_supported_channels")
    def wifi_support_channel(self, wifi_frequency):
        return self.list_wifi_supported_channels(self, wifi_frequency)

    def iwlist_supported_channels(self, wifi_band):
        """list of wifi client support channel.

        :param wifi_mode: wifi frequency ['2' or '5']
        :type wifi_mode: string
        :return: list of channel in wifi mode
        :rtype: list
        """
        install_iw(self)

        self.sudo_sendline(f"iwlist {self.iface_wifi} channel")
        self.expect(self.prompt)
        channel_list = []
        for line in self.before.split("\r\n"):
            match = re.search(r"Channel\ \d+\ \:\ %s.\d+\ GHz" % (wifi_band), line)
            if match:
                channel_list.append(match.group().split(" ")[1])
        return channel_list

    @moves.moved_method("list_wifi_ssids")
    def wifi_scan(self):
        self.list_wifi_ssids()

    def list_wifi_ssids(self):
        """Scan the SSID associated with the wifi interface.

        :return: List of SSID
        :rtype: string
        """
        cmd = f"iw dev {self.iface_wifi} scan | grep SSID: | sed 's/[[:space:]]*SSID: //g'"
        self.sudo_sendline(cmd)
        self.expect_exact(cmd)
        self.expect(self.prompt)
        return self.before.strip().splitlines()

    def wifi_check_ssid(self, ssid_name):
        """Check the SSID provided is present in the scan list.

        :param ssid_name: SSID name to be verified
        :type ssid_name: string
        :return: True or False
        :rtype: boolean
        """
        return ssid_name in self.list_wifi_ssids()

    def wifi_connect(
        self,
        ssid_name,
        password=None,
        security_mode="NONE",
        hotspot_id="cbn",
        hotspot_pwd="cbn",
        broadcast=True,
        bssid=None,
    ):
        """Initialise wpa supplicant file.

        :param ssid_name: SSID name
        :type ssid_name: string
        :param password: wifi password, defaults to None
        :type password: string, optional
        :param security_mode: Security mode for the wifi, [NONE|WPA-PSK|WPA-EAP]
        :type security_mode: string, optional
        :param hotspot_id: identity of hotspot
        :type hotspot_id: string
        :param hotspot_pwd: password of hotspot
        :type hotspot_pwd: string
        :param broadcast: Enable/Disable broadcast for ssid scan
        :type broadcast: bool
        :param bssid: Network BSSID
        :type bssid: string, optional
        :return: True or False
        :rtype: boolean
        """
        """Setup config of wpa_supplicant connect."""
        config = dict()
        config["ssid"] = ssid_name
        config["key_mgmt"] = security_mode

        if security_mode in ["WPA-PSK", "WPA2-PSK"]:
            config["psk"] = password
        elif security_mode == "WPA-EAP":
            config["eap"] = "PEAP"
            config["identity"] = hotspot_id
            config["password"] = hotspot_pwd
        config["scan_ssid"] = int(not broadcast)

        if bssid:
            config["bssid"] = bssid

        config_str = ""
        for k, v in config.items():
            if k in ["ssid", "psk", "identity", "password"]:
                v = '"{}"'.format(v)
            config_str += "{}={}\n".format(k, v)
        final_config = "ctrl_interface=DIR=/etc/wpa_supplicant GROUP=root\nnetwork={{\n{}}}".format(
            config_str
        )
        """Create wpa_supplicant config."""
        self.sudo_sendline("rm {}.conf".format(ssid_name))
        self.expect(self.prompt)
        self.sudo_sendline("echo -e '{}' > {}.conf".format(final_config, ssid_name))
        self.expect(self.prompt)
        self.sendline("cat {}.conf".format(ssid_name))
        self.expect(self.prompt)
        """Generate WPA supplicant connect."""
        driver_name = "wext"
        self.sudo_sendline(
            "wpa_supplicant -B -D{} -i {} -c {}.conf -d".format(
                driver_name, self.iface_wifi, ssid_name
            )
        )
        self.expect(self.prompt)
        match = re.search("Daemonize..", self.before)
        return bool(match)

    def wifi_connectivity_verify(self):
        """Backward compatibility"""
        return self.is_connected

    @property
    def is_connected(self):
        """Verify wifi is in the connected state.

        :return: True or False
        :rtype: boolean
        """
        self.sendline("iw %s link" % self.iface_wifi)
        self.expect(self.prompt)
        match = re.search("Connected", self.before)
        if match:
            return True
        else:
            return False

    def wifi_connect_check(self, ssid_name, password=None):
        """Connect to a SSID and verify WIFI connectivity.

        :param ssid_name: SSID name
        :type ssid_name: string
        :param password: wifi password, defaults to None
        :type password: string, optional
        :return: True or False
        :rtype: boolean
        """
        for _ in range(5):
            self.wifi_connect(ssid_name, password)
            self.expect(pexpect.TIMEOUT, timeout=10)
            verify_connect = self.wifi_connectivity_verify()
            if verify_connect:
                break
            else:
                self.wifi_disconnect()
        return verify_connect

    def disconnect_wpa(self):
        """Disconnect the wpa supplicant initialisation."""
        self.sudo_sendline("killall wpa_supplicant")
        self.expect(self.prompt)

    def wlan_ssid_disconnect(self):
        """Disconnect the wifi connectivity if connected through iwconfig method using ssid alone."""
        self.sudo_sendline("iw dev %s disconnect" % self.iface_wifi)
        self.expect(self.prompt)

    def wifi_disconnect(self):
        """Disconnect wifi connectivity.

        by disconnecting wpa supplicant initialisation as well as
        iwconfig disconnection
        """
        self.disconnect_wpa()
        self.wlan_ssid_disconnect()

    def wifi_change_region(self, country):
        """Change the region of the wifi.

        :param country: region to be set
        :type country: string
        :return: country name if matched else None
        :rtype: string or boolean
        """
        country = pycountry.countries.get(name=country).alpha_2
        self.sudo_sendline("iw reg set %s" % (country))
        self.expect(self.prompt)
        self.sendline("iw reg get")
        self.expect(self.prompt)
        match = re.search(country, self.before)
        if match:
            return match.group(0)
        else:
            return None

    def wifi_client_connect(
        self, ssid_name, password=None, security_mode=None, bssid=None
    ):
        """Scan for SSID and verify wifi connectivity.

        :param ssid_name: SSID name
        :type ssid_name: string
        :param password: wifi password, defaults to None
        :type password: string, optional
        :param security_mode: Security mode for the wifi, defaults to None
        :param bssid: BSSID of the desired network. Used to differentialte between 2.4\5 GHz networks with same SSID
        :type bssid: string, optional
        :type security_mode: string, optional
        :raise assertion: If SSID value check in WLAN container fails,
                          If connection establishment in WIFI fails
        """
        self.disable_and_enable_wifi()
        self.expect(pexpect.TIMEOUT, timeout=20)
        output = self.wifi_check_ssid(ssid_name)
        assert (
            output is True
        ), f"{ssid_name} network is not found. Aborting connection process"

        self.wifi_connect(ssid_name, password, bssid=bssid, security_mode=security_mode)
        self.expect(pexpect.TIMEOUT)
        verify_connect = self.wifi_connectivity_verify()
        assert (
            verify_connect is True
        ), f"Wlan client failed to connect to {ssid_name} network"
        self.dhcp_renew_wlan_iface()

    def set_authentication(self, auth_type):
        pass
