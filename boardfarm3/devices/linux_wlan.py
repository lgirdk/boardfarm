# ruff: noqa: SIM103,EM102,TRY003,PGH003,PLW2901,PLR0913,TC001,EM101,TRY300

"""Boardfarm WLAN device module."""

from __future__ import annotations

import logging
import re
from argparse import Namespace
from ipaddress import IPv4Interface, IPv4Network
from typing import TYPE_CHECKING

import jc
import pexpect

from boardfarm3 import hookimpl
from boardfarm3.devices.base_devices import LinuxDevice
from boardfarm3.exceptions import WifiError
from boardfarm3.lib.boardfarm_config import BoardfarmConfig
from boardfarm3.lib.boardfarm_pexpect import BoardfarmPexpect
from boardfarm3.lib.multicast import Multicast
from boardfarm3.templates.cpe import CPE
from boardfarm3.templates.wlan import WLAN

if TYPE_CHECKING:
    from ipaddress import IPv4Address

    from boardfarm3.lib.device_manager import DeviceManager


_LOGGER = logging.getLogger(__name__)


class LinuxWLAN(LinuxDevice, WLAN):  # pylint: disable=too-many-public-methods
    """Boardfarm WLAN device."""

    _wlan_interface = "wlan1"

    def __init__(self, config: dict, cmdline_args: Namespace) -> None:
        """Initialize linux device.

        :param config: device configuration
        :type config: dict
        :param cmdline_args: command line arguments
        :type cmdline_args: Namespace
        """
        super().__init__(config, cmdline_args)
        self._multicast: Multicast = None

    @hookimpl
    def boardfarm_attached_device_boot(self) -> None:
        """Boardfarm hook implementation to boot WLAN device."""
        _LOGGER.info("Booting %s(%s) device", self.device_name, self.device_type)
        self._connect()

    @hookimpl
    async def boardfarm_attached_device_boot_async(self) -> None:
        """Boardfarm hook implementation to boot WLAN device."""
        _LOGGER.info("Booting %s(%s) device", self.device_name, self.device_type)
        await self._connect_async()

    @hookimpl
    def boardfarm_shutdown_device(self) -> None:
        """Boardfarm hook implementation to shutdown WLAN device."""
        _LOGGER.info("Shutdown %s(%s) device", self.device_name, self.device_type)
        self._disconnect()

    @hookimpl
    def boardfarm_skip_boot(self) -> None:
        """Boardfarm hook implementation to initialize WLAN device."""
        _LOGGER.info("Initializing %s(%s) device", self.device_name, self.device_type)
        self._connect()

    @hookimpl
    def boardfarm_attached_device_configure(
        self, device_manager: DeviceManager, config: BoardfarmConfig
    ) -> None:
        """Configure boardfarm attached device.

        :param device_manager: device manager
        :type device_manager: DeviceManager
        :param config: contains both environment and inventory config
        :type config: BoardfarmConfig
        """
        wifi = device_manager.get_device_by_type(
            CPE  # type: ignore[type-abstract]
        ).sw.wifi
        if not all([self.band, self.network, self.protocol, self.authentication]):
            _LOGGER.error(
                "Unable to get all client details from environment config"
                "Please check that band, network, protocol and authentication keys are present"
            )
            return
        ssid, bssid, passphrase = wifi.enable_wifi(self.network, self.band)
        # Connect appropriate client to the network
        self.wifi_client_connect(
            ssid_name=ssid,
            password=passphrase,
            bssid=bssid,
            security_mode=self.authentication,
        )
        self._setup_static_routes()
        if config.get_prov_mode() in ["ipv4"]:
            self.start_ipv4_wlan_client()
        else:
            self.start_ipv4_wlan_client()
            self.start_ipv6_wlan_client()

    @property
    def band(self) -> str:
        """Wifi band supported by the wlan device.

        :return: type of band i.e. 2.4, 5, dual
        :rtype: str
        """
        return self._config.get("band")

    @property
    def network(self) -> str:
        """Wifi network to which wlan device should connect.

        :return: type of network i.e. private, guest, community
        :rtype: str
        """
        return self._config.get("network")

    @property
    def authentication(self) -> str:
        """Wifi authentication through which wlan device should connect.

        :return: authentication method, eg: WPA-PSK, WPA2, etc
        :rtype: str
        """
        return self._config.get("authentication")

    @property
    def protocol(self) -> str:
        """Wifi protocol using which wlan device should connect.

        :return: wifi protocol, eg: 802.11ac, 802.11, etc
        :rtype: str
        """
        return self._config.get("protocol")

    @property
    def http_proxy(self) -> str:
        """SOCKS5 dante proxy address.

        :return: http proxy address, eg: http://{proxy_ip}:{proxy_port}/
        :rtype: str
        """
        return self._config.get("http_proxy")

    @property
    def iface_dut(self) -> str:
        """Name of the interface that is connected to DUT.

        :return: interface connected to dut
        :rtype: str
        """
        return self._wlan_interface

    @property
    def lan_network(self) -> IPv4Network:
        """IPv4 WLAN Network.

        :return: IPv4 address network
        :rtype: IPv4Network
        """
        # TODO: resolve lan network dynamically
        return IPv4Interface(
            self._config.get("lan_network", "192.168.178.0/24")
        ).network

    @property
    def lan_gateway(self) -> IPv4Address:
        """WLAN gateway address.

        :return: Ipv4 wlan gateway address
        :rtype: IPv4Address
        """
        # TODO: resolve lan gateway address dynamically
        return IPv4Interface(self._config.get("lan_gateway", "192.168.178.1/24")).ip

    @property
    def multicast(self) -> Multicast:
        """Return multicast component instance.

        :return: multicast component instance
        :rtype: Multicast
        """
        return self._multicast

    @property
    def console(self) -> BoardfarmPexpect:
        """Return wan console.

        :return: console
        :rtype: BoardfarmPexpect
        """
        return self._console

    def reset_wifi_iface(self) -> None:
        """Disable and enable wifi interface.

        Set the interface link to "down" and then to "up".
        This calls the disable wifi and enable wifi methods
        """
        self.disable_wifi()
        self.enable_wifi()

    def disable_wifi(self) -> None:
        """Disabling the wifi interface.

        Set the interface link to "down"
        """
        self._console.execute_command(f"rm /etc/wpa_supplicant/{self.iface_dut}")
        self._console.execute_command("killall wpa_supplicant")
        self.set_link_state(self.iface_dut, "down")

    def enable_wifi(self) -> None:
        """Enable the wifi interface.

        Set the interface link to "up"
        """
        self.set_link_state(self.iface_dut, "up")

    def dhcp_release_wlan_iface(self) -> None:
        """DHCP release of the wifi interface."""
        self.release_dhcp(self.iface_dut)

    def start_ipv4_wlan_client(self) -> bool:
        """Restart ipv4 dhclient to obtain an IP.

        :return: True if renew is success else False
        :rtype: bool
        """
        # Remove static ip if any
        self._console.execute_command(f"ifconfig {self.iface_dut} 0.0.0.0")
        # remove default route
        self._console.execute_command("ip route flush default")
        # Clean IP lease if any
        self._console.execute_command(f"dhclient -r {self.iface_dut}")
        # Kill dhcp client
        self._console.execute_command("kill -9 $(pgrep dhclient)")
        try:
            self.renew_dhcp(self.iface_dut)
            return True
        except pexpect.TIMEOUT:
            self._console.sendcontrol("c")
            self._console.expect(self._shell_prompt)
            self._console.execute_command("killall dhclient")
            return False

    def start_ipv6_wlan_client(self) -> None:
        """Restart ipv6 dhclient to obtain IP."""
        # flush default ipv6 route
        self._console.execute_command("ip -6 route flush default")

        self._console.execute_command(f"dhclient -6 -r {self.iface_dut}")
        self._console.execute_command(f"dhclient -6 -v {self.iface_dut}")
        self.disable_ipv6()
        self.enable_ipv6()

    def set_wlan_scan_channel(self, channel: str) -> None:
        """Change wifi client scan channel.

        :param channel: name of the wifi channel
        :type channel: str
        """
        self._console.execute_command(f"iwconfig {self.iface_dut} channel {channel}")

    def iwlist_supported_channels(self, wifi_band: str) -> list[str]:
        """Get the list of wifi client support channels.

        :param wifi_band: wifi frequency ['2.4' or '5']
        :type wifi_band: str
        :return: list of channel in wifi mode
        :rtype: list[str]
        """
        out = self._console.execute_command(f"iwlist {self.iface_dut} channel")
        channel_list = []
        for line in out.splitlines():
            match = re.search(rf"Channel\ \d+\ \:\ {wifi_band}.\d+\ GHz", line)
            if match:
                channel_list.append(match.group().split(" ")[1])
        return channel_list

    def list_wifi_ssids(self) -> list[str]:
        """Return available WiFi SSID's.

        :raises WifiError: WLAN card was blocked due to some process.
        :return: List of Wi-FI SSIDs
        :rtype: list[str]
        """
        cmd = (
            f"iw dev {self.iface_dut} scan | grep SSID: | sed 's/[[:space:]]*SSID: //g'"
        )
        for _ in range(3):
            out = self._console.execute_command(cmd)
            if "Device or resource busy" not in out:
                # out can be completely empty
                # we only run the loop again if wlan card was busy
                return out.splitlines()
            if not self.is_wlan_connected():
                # run rfkill only if device is not connected to any WiFi SSID.
                self._console.execute_command("rfkill unblock all")
        raise WifiError("Device failed to scan for SSID due to resource busy!")

    def _wifi_connect(  # pylint: disable=too-many-arguments
        self,
        ssid_name: str,
        password: str,
        security_mode: str,
        hotspot_id: str,
        hotspot_pwd: str,
        broadcast: bool,
        bssid: str,
    ) -> bool:
        """Initialise wpa supplicant file.

        :param ssid_name: SSID name
        :type ssid_name: str
        :param password: wifi password, defaults to None
        :type password: str
        :param security_mode: Security mode for the wifi, [NONE|WPA-PSK|WPA-EAP]
        :type security_mode: str
        :param hotspot_id: identity of hotspot
        :type hotspot_id: str
        :param hotspot_pwd: password of hotspot
        :type hotspot_pwd: str
        :param broadcast: Enable/Disable broadcast for ssid scan
        :type broadcast: bool
        :param bssid: Network BSSID
        :type bssid: str
        :return: True or False
        :rtype: bool
        """
        # Setup config of wpa_supplicant connect
        config: dict[str, str | int] = {}
        config["ssid"] = ssid_name
        config["key_mgmt"] = security_mode
        if security_mode == "WPA-EAP":
            config["eap"] = "PEAP"
            config["identity"] = hotspot_id
            config["password"] = hotspot_pwd
        config["scan_ssid"] = int(not broadcast)
        if bssid:
            config["bssid"] = bssid
        config_str = ""
        for key, value in config.items():
            if key in ["ssid", "psk", "identity", "password"]:
                value = f'"{value}"'
            config_str += f"{key}={value}\n"
        final_config = f"""ctrl_interface=DIR="/etc/wpa_supplicant GROUP=root
        network=\n{config_str}"""
        # Create wpa_supplicant config.
        self._console.execute_command(f"rm {ssid_name}.conf")
        if security_mode in ["WPA-PSK", "WPA2-PSK"]:
            self._console.execute_command(
                f"wpa_passphrase '{ssid_name}' '{password}'"
                " | sed -e '/^network[[:space:]]*=/a\\"
                f"\\tkey_mgmt={security_mode}\\n\\tbssid={bssid}' > {ssid_name}.conf"
            )
        else:
            self._console.execute_command(
                f"echo -e '{final_config}' > {ssid_name}.conf"
            )
        self._console.execute_command(f"cat {ssid_name}.conf")
        # Generate WPA supplicant connect.
        return "Daemonize.." in self._console.execute_command(
            f"wpa_supplicant -B -D nl80211 -i {self.iface_dut} -c {ssid_name}.conf -d"
        )

    def is_wlan_connected(self) -> bool:
        """Verify wifi is in the connected state.

        :return: True if wlan is connected, False otherwise
        :rtype: bool
        """
        return "Connected" in self._console.execute_command(f"iw {self.iface_dut} link")

    def disconnect_wpa(self) -> None:
        """Disconnect the wpa supplicant initialisation."""
        self._console.execute_command("killall wpa_supplicant")

    def wifi_disconnect(self) -> None:
        """Disconnect wifi connectivity."""
        self.disconnect_wpa()
        self._console.execute_command(f"iw dev {self.iface_dut} disconnect")

    def change_wifi_region(self, country: str) -> None:
        """Change the region of the wifi.

        :param country: region to be set
        :type country: str
        :raises WifiError: Raises error if region could not be changed
        """
        self._console.execute_command(f"iw reg set {country}")
        if country not in self._console.execute_command("iw reg get"):
            raise WifiError(f"Wifi region could not be changed to: {country}")

    def wifi_client_connect(
        self,
        ssid_name: str,
        password: str | None = None,
        security_mode: str | None = None,
        bssid: str | None = None,
    ) -> None:
        """Scan for SSID and verify wifi connectivity.

        :param ssid_name: SSID name
        :type ssid_name: str
        :param password: wifi password, defaults to None
        :type password: str | None
        :param security_mode: Security mode for the wifi, defaults to None
        :type security_mode: str | None
        :param bssid: BSSID of the desired network.
            Used to differentialte between 2.4/5 GHz networks with same SSID
        :type bssid: str | None
        :raises WifiError: raises exception if ssid is not found on a network
        :raises WifiError: raises exception if wlan client could not be connected to dut
        """
        self.reset_wifi_iface()
        self._console.expect(pexpect.TIMEOUT, timeout=20)
        output = ssid_name in self.list_wifi_ssids()
        if not output:
            raise WifiError(
                f"{ssid_name} network is not found. Aborting connection process"
            )

        self._wifi_connect(
            ssid_name, password, security_mode, "cbn", "cbn", True, bssid
        )
        self._console.expect(pexpect.TIMEOUT)
        verify_connect = self.is_wlan_connected()
        if not verify_connect:
            raise WifiError(f"Wlan client failed to connect to {ssid_name} network")
        self.start_ipv4_wlan_client()

    def enable_ipv6(self) -> None:
        """Enable ipv6 on the connected client interface."""
        self._console.execute_command(
            f"sysctl net.ipv6.conf.{self.iface_dut}.accept_ra=2"
        )
        self._console.execute_command(
            f"sysctl net.ipv6.conf.{self.iface_dut}.disable_ipv6=0"
        )

    def disable_ipv6(self) -> None:
        """Disable ipv6 on the connected client interface."""
        self._console.execute_command(
            f"sysctl net.ipv6.conf.{self.iface_dut}.disable_ipv6=1"
        )
        self._console.execute_command(
            f"sysctl net.ipv6.conf.{self.iface_dut}.disable_ipv6=1"
        )

    def get_interface_mtu_size(self, interface: str) -> int:
        """Get the MTU size of the interface in bytes.

        :param interface: name of the interface
        :type interface: str
        :return: size of the MTU in bytes
        :rtype: int
        :raises ValueError: when ifconfig data is not available
        """
        if ifconfig_data := jc.parse(
            "ifconfig",
            self._console.execute_command(f"ifconfig {interface}"),
        ):
            return ifconfig_data[0]["mtu"]  # type: ignore
        raise ValueError(f"ifconfig {interface} is not available")

    def enable_monitor_mode(self) -> None:
        """Enable monitor mode on WLAN interface.

        Set the type to monitor
        """
        self.disable_wifi()
        self._console.execute_command(f"iw dev {self.iface_dut} set type monitor")
        self.enable_wifi()

    def disable_monitor_mode(self) -> None:
        """Disable monitor mode on WLAN interface.

        Set the type to managed
        """
        self.disable_wifi()
        self._console.execute_command(f"iw dev {self.iface_dut} set type managed")
        self.enable_wifi()

    def is_monitor_mode_enabled(self) -> bool:
        """Check if monitor mode is enabled on WLAN interface.

        :return: Status of monitor mode
        :rtype: bool
        """
        output = self._console.execute_command(f"iw dev {self.iface_dut} info")
        if "type monitor" in output:
            return True
        return False

    def get_hostname(self) -> str:
        """Get the hostname of the device.

        :return: hostname of the device
        :rtype: str
        """
        return self.hostname()


if __name__ == "__main__":
    # stubbed instantation of the device
    # this would throw a linting issue in case the device does not follow the template
    LinuxWLAN(config={}, cmdline_args=Namespace())
