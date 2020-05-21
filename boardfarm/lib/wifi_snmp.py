import pexpect

from . import SnmpHelper
from .common import retry_on_exception, snmp_mib_get, snmp_mib_set
from .wifi import wifi_stub


class wifi_snmp(wifi_stub):
    """Class for wifi settings via SNMP.
    Inherits wifi_stub from lib/wifi.py
    """
    def __init__(self, device, board):
        """To get the mib names for wifi.
        This mib name has to be provided via a vendor specific json file
        and initialised in the board method
        """
        self.device = device
        self.board = board
        self.mib_value = self.board.wifi_snmp_file
        self.parser = SnmpHelper.SnmpMibs.default_mibs
        self.iface_ip = None

    def enable_wifi(self, wifi_mode):
        """To enable wifi network via SNMP.

        :param wifi_mode: wifi network mode eg:private_2.4, guest_5
        :type wifi_mode: string
        :raises assertion: Mib query return value for enable wifi
        """
        index = self.mib_value["mib_index"][wifi_mode]
        mib_out = snmp_mib_set(
            self.device,
            self.parser,
            self.iface_ip,
            self.mib_value["mib_name"]["Wifi_enable"],
            index,
            "i",
            "1",
        )
        if self.apply_changes_no_delay:
            self.apply_changes()
            mib_out = snmp_mib_get(
                self.device,
                self.parser,
                self.iface_ip,
                self.mib_value["mib_name"]["Wifi_enable"],
                index,
            )
        assert mib_out == "1", "Mib query return value for enable wifi: %s" % mib_out

    def set_ssid(self, wifi_mode, ssid_name):
        """To set wifi ssid via SNMP.

        :param wifi_mode: wifi network mode eg:private_2.4, guest_5
        :type wifi_mode: string
        :param ssid_name: Name for wifi ssid
        :type ssid_name: string
        :raises assertion: Mib query return value for setting the SSID
        """
        index = self.mib_value["mib_index"][wifi_mode]
        mib_out = snmp_mib_set(
            self.device,
            self.parser,
            self.iface_ip,
            self.mib_value["mib_name"]["SSID_set"],
            index,
            "s",
            ssid_name,
        )
        if self.apply_changes_no_delay:
            self.apply_changes()
            mib_out = snmp_mib_get(
                self.device,
                self.parser,
                self.iface_ip,
                self.mib_value["mib_name"]["SSID_set"],
                index,
            )
        assert mib_out == ssid_name, (
            "Mib query return value for setting the SSID: %s" % mib_out)

    def set_security(self, wifi_mode, security):
        """To set wifi security via SNMP.

        :param wifi_mode: wifi network mode eg:private_2.4, guest_5
        :type wifi_mode: string
        :param security: security string eg:WPA-PSK/WPA2-PSK
        :type security: string
        :raises assertion: Mib query return value for setting the security mode
        """
        index = self.mib_value["mib_index"][wifi_mode]
        security_mode = self.mib_value["security_mode"][security]
        mib_out = snmp_mib_set(
            self.device,
            self.parser,
            self.iface_ip,
            self.mib_value["mib_name"]["Security_mode"],
            index,
            "i",
            security_mode,
        )
        if self.apply_changes_no_delay:
            self.apply_changes()
            mib_out = snmp_mib_get(
                self.device,
                self.parser,
                self.iface_ip,
                self.mib_value["mib_name"]["Security_mode"],
                index,
            )
        assert mib_out == security_mode, (
            "Mib query return value for setting the security mode: %s" %
            mib_out)

    def set_password(self, wifi_mode, password):
        """To set wifi password via SNMP.

        :param wifi_mode: wifi network mode eg:private_2.4, guest_5
        :type wifi_mode: string
        :param password: wifi password
        :type password: string
        :raises assertion: Mib query return value for setting the password
        """
        index = self.mib_value["mib_index"][wifi_mode]
        mib_out = snmp_mib_set(
            self.device,
            self.parser,
            self.iface_ip,
            self.mib_value["mib_name"]["Password_set"],
            index,
            "s",
            password,
        )
        if self.apply_changes_no_delay:
            self.apply_changes()
            mib_out = snmp_mib_get(
                self.device,
                self.parser,
                self.iface_ip,
                self.mib_value["mib_name"]["Password_set"],
                index,
            )
        assert mib_out == password, (
            "Mib query return value for setting the password: %s" % mib_out)

    def enable_channel_utilization(self, wifi_mode):
        """To enable channel utilization via SNMP.

        :param wifi_mode: wifi network mode eg:private_2.4, guest_2.4,
                                               private_5, guest_5
        :type wifi_mode: string
        :raises assertion: Mib query return value for setting the channel utilisation
        """
        mib_out = snmp_mib_set(
            self.device,
            self.parser,
            self.iface_ip,
            self.mib_value["mib_name"]["Channel_Util"],
            "0",
            "i",
            "2",
        )
        if self.apply_changes_no_delay:
            self.apply_changes()
            mib_out = snmp_mib_get(
                self.device,
                self.parser,
                self.iface_ip,
                self.mib_value["mib_name"]["Channel_Util"],
                "0",
            )
        assert mib_out == "2", (
            "Mib query return value for setting the channel utilisation: %s" %
            mib_out)

    def set_operating_mode(self, wifi_mode, operating_mode):
        """To set wifi operating mode via SNMP.

        :param wifi_mode: wifi network mode eg:private_2.4, guest_2.4,
                                               private_5, guest_5
        :type wifi_mode: string
        :param operating_mode: wifi operating mode eg:802.11b/g mixed
        :type operating_mode: string
        :raises assertion: Mib query return value for setting the operating mode
        """
        index = self.mib_value["mib_index"][wifi_mode]
        operating_mode = self.mib_value["operating_mode"][operating_mode]
        mib_out = snmp_mib_set(
            self.device,
            self.parser,
            self.iface_ip,
            self.mib_value["mib_name"]["Operating_mode"],
            index,
            "i",
            operating_mode,
        )
        if self.apply_changes_no_delay:
            self.apply_changes()
            mib_out = snmp_mib_get(
                self.device,
                self.parser,
                self.iface_ip,
                self.mib_value["mib_name"]["Operating_mode"],
                index,
            )
        assert mib_out == operating_mode, (
            "Mib query return value for setting the operating mode: %s" %
            mib_out)

    def set_bandwidth(self, wifi_mode, bandwidth, channel_number=0):
        """To set wifi bandwidth via SNMP.

        :param wifi_mode: wifi network mode eg:private_2.4, guest_2.4,
                                               private_5, guest_5
        :type wifi_mode: string
        :param bandwidth: wifi bandwidth eg:20/40 MHz
        :type bandwidth: string
        :param channel_number: Always 0 in snmp, defaults to 0
        :type channel_number: Integer, optional
        :raises assertion: Mib query return value for setting the bandwidth
        """
        index = self.mib_value["mib_index"][wifi_mode]
        bandwidth = self.mib_value["bandwidth"][bandwidth]
        mib_out = snmp_mib_set(
            self.device,
            self.parser,
            self.iface_ip,
            self.mib_value["mib_name"]["Bandwidth"],
            index,
            "i",
            bandwidth,
        )
        if self.apply_changes_no_delay:
            self.apply_changes()
            mib_out = snmp_mib_get(
                self.device,
                self.parser,
                self.iface_ip,
                self.mib_value["mib_name"]["Bandwidth"],
                index,
            )
        assert mib_out == bandwidth, (
            "Mib query return value for setting the bandwidth: %s" % mib_out)

    def set_channel_number(self, wifi_mode, channel_number):
        """To set wifi channel number via SNMP.

        :param wifi_mode: wifi network mode eg:private_2.4, guest_2.4,
                                               private_5, guest_5
        :type wifi_mode: string
        :param channel_number: Wifi channel number
        :type channel_number: string
        :raises assertion: Mib query return value for setting the channel number
        """
        index = self.mib_value["mib_index"][wifi_mode]
        mib_out = snmp_mib_set(
            self.device,
            self.parser,
            self.iface_ip,
            self.mib_value["mib_name"]["Channel_mode"],
            index,
            "u",
            channel_number,
        )
        if self.apply_changes_no_delay:
            self.apply_changes()
            mib_out = snmp_mib_get(
                self.device,
                self.parser,
                self.iface_ip,
                self.mib_value["mib_name"]["Channel_mode"],
                index,
            )
        assert mib_out == channel_number, (
            "Mib query return value for setting the channel number: %s" %
            mib_out)

    def set_broadcast(self, wifi_mode, broadcast="enable"):
        """To set wifi broadcast via SNMP.

        :param wifi_mode: wifi network mode eg:private_2.4, guest_2.4,
                                               private_5, guest_5
        :type wifi_mode: string
        :param broadcast: enable or disable, defaults to enable
        :type broadcast: string, optional
        :raises assertion: Mib query return value for setting the broadcast for SSID
        """
        if broadcast == "enable":
            broadcast_value = "2"
        elif broadcast == "disable":
            broadcast_value = "1"
        index = self.mib_value["mib_index"][wifi_mode]
        mib_out = snmp_mib_set(
            self.device,
            self.parser,
            self.iface_ip,
            self.mib_value["mib_name"]["Broadcast"],
            index,
            "i",
            broadcast_value,
        )
        if self.apply_changes_no_delay:
            self.apply_changes()
            mib_out = snmp_mib_get(
                self.device,
                self.parser,
                self.iface_ip,
                self.mib_value["mib_name"]["Broadcast"],
                index,
            )
        assert mib_out == broadcast_value, (
            "Mib query return value for setting the broadcast for SSID: %s" %
            mib_out)

    def apply_changes(self):
        """To apply changes to the wifi settings.

        :return: True or False
        :rtype: boolean
        """
        retry_on_exception(
            snmp_mib_set,
            (
                self.device,
                self.parser,
                self.iface_ip,
                self.mib_value["mib_name"]["Wifi_Apply_setting"],
                "0",
                "i",
                "1",
            ),
        )
        for _ in range(4):
            self.board.expect(pexpect.TIMEOUT, timeout=20)
            try:
                mib_out = snmp_mib_set(
                    self.device,
                    self.parser,
                    self.iface_ip,
                    self.mib_value["mib_name"]["Wifi_diag_command"],
                    "0",
                    "s",
                    '"echo 1"',
                )
                mib_out = snmp_mib_get(
                    self.device,
                    self.parser,
                    self.iface_ip,
                    self.mib_value["mib_name"]["Wifi_diag_result"],
                    "0",
                )
                if mib_out != "1":
                    continue
                wifi_2G_channel = snmp_mib_get(
                    self.device,
                    self.parser,
                    self.iface_ip,
                    self.mib_value["mib_name"]["Current_channel"],
                    "32",
                )
                wifi_5G_channel = snmp_mib_get(
                    self.device,
                    self.parser,
                    self.iface_ip,
                    self.mib_value["mib_name"]["Current_channel"],
                    "92",
                )
                if wifi_2G_channel != "0" and wifi_5G_channel != "0":
                    return True
                    break
            except Exception:
                pass
        return False

    def get_wifi_enabled(self, wifi_mode):
        """To verify wifi enabled via SNMP.

        :param wifi_mode: wifi network mode eg:private_2.4, guest_2.4,
                                               private_5, guest_5
        :type wifi_mode: string
        :return: mib output wifi enabled or not
        :rtype: string
        """
        index = self.mib_value["mib_index"][wifi_mode]
        mib_out = snmp_mib_get(
            self.device,
            self.parser,
            self.iface_ip,
            self.mib_value["mib_name"]["Wifi_enable"],
            index,
        )
        return mib_out

    def get_ssid(self, wifi_mode):
        """To get ssid via SNMP.

        :param wifi_mode: wifi network mode eg:private_2.4, guest_2.4,
                                               private_5, guest_5
        :type wifi_mode: string
        :return: wifi ssid
        :rtype: string
        """
        index = self.mib_value["mib_index"][wifi_mode]
        mib_out = snmp_mib_get(
            self.device,
            self.parser,
            self.iface_ip,
            self.mib_value["mib_name"]["SSID_set"],
            index,
        )
        return mib_out

    def get_security(self, wifi_mode):
        """To get security via SNMP.

        :param wifi_mode: wifi network mode eg:private_2.4, guest_2.4,
                                               private_5, guest_5
        :type wifi_mode: string
        :return: wifi security
        :rtype: string
        """
        index = self.mib_value["mib_index"][wifi_mode]
        mib_out = snmp_mib_get(
            self.device,
            self.parser,
            self.iface_ip,
            self.mib_value["mib_name"]["Security_mode"],
            index,
        )
        return mib_out

    def get_password(self, wifi_mode):
        """To get password via SNMP.

        :param wifi_mode: wifi network mode eg:private_2.4, guest_2.4,
                                               private_5, guest_5
        :type wifi_mode: string
        :return: wifi password
        :rtype: string
        """
        index = self.mib_value["mib_index"][wifi_mode]
        mib_out = snmp_mib_get(
            self.device,
            self.parser,
            self.iface_ip,
            self.mib_value["mib_name"]["Password_set"],
            index,
        )
        return mib_out

    def get_channel_utilization(self):
        """To get channel utilization via SNMP.

        :param wifi_mode: wifi network mode eg:private_2.4, guest_2.4,
                                               private_5, guest_5
        :type wifi_mode: string
        :return: wifi channel utilization
        :rtype: string
        """
        mib_out = snmp_mib_get(
            self.device,
            self.parser,
            self.iface_ip,
            self.mib_value["mib_name"]["Channel_Util"],
            "0",
        )
        return mib_out

    def get_operating_mode(self, wifi_mode):
        """To get operating mode via SNMP.

        :param wifi_mode: wifi network mode eg:private_2.4, guest_2.4,
                                               private_5, guest_5
        :type wifi_mode: string
        :return: wifi operating mode
        :rtype: string
        """
        index = self.mib_value["mib_index"][wifi_mode]
        mib_out = snmp_mib_get(
            self.device,
            self.parser,
            self.iface_ip,
            self.mib_value["mib_name"]["Operating_mode"],
            index,
        )
        return mib_out

    def get_bandwidth(self, wifi_mode):
        """To get bandwidth via SNMP.

        :param wifi_mode: wifi network mode eg:private_2.4, guest_2.4,
                                               private_5, guest_5
        :type wifi_mode: string
        :return: wifi bandwidth
        :rtype: string
        """
        index = self.mib_value["mib_index"][wifi_mode]
        mib_out = snmp_mib_get(
            self.device,
            self.parser,
            self.iface_ip,
            self.mib_value["mib_name"]["Bandwidth"],
            index,
        )
        return mib_out

    def get_broadcast(self, wifi_mode):
        """To get broadcast via SNMP.

        :param wifi_mode: wifi network mode eg:private_2.4, guest_2.4,
                                               private_5, guest_5
        :type wifi_mode: string
        :return: wifi broadcast
        :rtype: string
        """
        index = self.mib_value["mib_index"][wifi_mode]
        mib_out = snmp_mib_get(
            self.device,
            self.parser,
            self.iface_ip,
            self.mib_value["mib_name"]["Broadcast"],
            index,
        )
        return mib_out

    def get_channel_number(self, wifi_mode):
        """To get channel number via SNMP.

        :param wifi_mode: wifi network mode eg:private_2.4, guest_2.4,
                                               private_5, guest_5
        :type wifi_mode: string
        :return: wifi channel number
        :rtype: string
        """
        index = self.mib_value["mib_index"][wifi_mode]
        mib_out = snmp_mib_get(
            self.device,
            self.parser,
            self.iface_ip,
            self.mib_value["mib_name"]["Current_channel"],
            index,
        )
        return mib_out
