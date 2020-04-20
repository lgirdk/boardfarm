import re

import pexpect

from .wifi import wifi_stub


class wifi_acs(wifi_stub):
    """Class for wifi acs methods
    Inherits the wifi stub from lib/wifi.py
    """
    # for acs connect func it is required
    log_to_file = ""

    def __init__(self, wan, board, acs_server):
        """Constructor method to initialise and get
        wan ip, and acs serverserial number and acs
        data object
        """
        self.wan = wan
        self.board = board
        self.wan_ip = board.get_interface_ipaddr(board.wan_iface)
        self.acs_server = acs_server
        self.cpeid = board.get_cpeid().replace('-', ':')
        self.acs_data = self.board.wifi_acs_file

    def prepare(self):
        """Getting boot file name via ACS to ensure connectivity exist or not
           If it returns none , ACS connectivity happens
        """
        acs_value = self.acs_server.get(self.cpeid,
                                        'Device.DeviceInfo.SerialNumber')
        if acs_value == None:
            self.board.restart_tr069(self.wan, self.wan_ip)

    def _check_acspath_spectrum(self, wifi_mode, ssid_flag=0):
        """Check and get the acs data object
        based on wifi mode and ssid flag

        :param wifi_mode: wifi network mode eg:private_2.4 or private_5
                                             or guest_2.4 or guest_5
        :type wifi_mode: string
        :param ssid_flag: ssid flag to get the acs path(0 or 1 or 2), defaults to 0
        :type ssid_flag: Integer, optional
        :return: acs data object path
        :rtype: string
        """
        acs_path = "Device.WiFi."
        if ssid_flag == 0:
            if "2.4" in wifi_mode:
                table_path = acs_path + "Radio." + self.acs_data['wifi_path'][
                    'Radio_2.4']
            elif "5" in wifi_mode:
                table_path = acs_path + "Radio." + self.acs_data['wifi_path'][
                    'Radio_5']
        elif ssid_flag == 1:
            table_path = acs_path + "SSID." + self.acs_data['wifi_path'][
                wifi_mode]
        elif ssid_flag == 2:
            table_path = acs_path + "AccessPoint." + self.acs_data[
                'wifi_path'][wifi_mode]
        return table_path

    def enable_wifi(self, wifi_mode):
        """Enable wifi via acs

        :param wifi_mode: wifi network mode eg:private_2.4 or private_5
                                             or guest_2.4 or guest_5
        :type wifi_mode: string
        :return: ACS value or None
        :rtype: string or boolean
        """
        # importing self.acs_server for each func, because global import not working
        table_path = self._check_acspath_spectrum(wifi_mode, ssid_flag=1)
        acs_value = self.acs_server.set(self.cpeid,
                                        table_path + '.' + 'Enable', 1)
        # timeout requires for all func as it takes time to set in acs server
        self.board.expect(pexpect.TIMEOUT, timeout=20)
        return acs_value

    def disable_wifi(self, wifi_mode):
        """Disable wifi via acs

        :param wifi_mode: wifi network mode eg:private_2.4 or private_5
                                             or guest_2.4 or guest_5
        :type wifi_mode: string
        :return: ACS value or None
        :rtype: string or boolean
        """
        table_path = self._check_acspath_spectrum(wifi_mode)
        acs_value = self.acs_server.set(self.cpeid,
                                        table_path + '.' + 'Enable', 0)
        self.board.expect(pexpect.TIMEOUT, timeout=20)
        return acs_value

    def set_channel_number(self, wifi_mode, channel_number):
        """Set wifi channel number via acs

        :param wifi_mode: wifi network mode eg:private_2.4 or private_5
                                             or guest_2.4 or guest_5
        :type wifi_mode: string
        :param channel_number: wifi channel number
        :type channel_number: string
        :return: ACS value or None
        :rtype: string or boolean
        """
        print("Setting the channel mode")
        table_path = self._check_acspath_spectrum(wifi_mode)
        if int(channel_number) > 0:
            acs_value = self.acs_server.set(self.cpeid,
                                            table_path + '.' + 'Channel',
                                            int(channel_number))
        else:
            acs_value = self.acs_server.set(
                self.cpeid, table_path + '.' + 'AutoChannelEnable', 1)
        self.board.expect(pexpect.TIMEOUT, timeout=30)
        return acs_value

    def set_bandwidth(self, wifi_mode, bandwidth, channel_number):
        """Set wifi bandwidth via acs

        :param wifi_mode: wifi network mode eg:private_2.4 or private_5
                                             or guest_2.4 or guest_5
        :type wifi_mode: string
        :param bandwidth: wifi bandwidth
        :type bandwidth: string
        :param channel_number: wifi channel number
        :type channel_number: string
        :return: ACS value or None
        :rtype: string or boolean
        """
        print("setting bandwidth")
        bandwidth = re.sub(' ', '', bandwidth)
        table_path = self._check_acspath_spectrum(wifi_mode)
        acs_value = self.acs_server.set(
            self.cpeid, table_path + '.' + 'OperatingChannelBandwidth',
            bandwidth)
        self.board.expect(pexpect.TIMEOUT, timeout=20)
        return acs_value

    def set_operating_mode(self, wifi_mode, operating_mode):
        """Set wifi operating mode via acs

        :param wifi_mode: wifi network mode eg:private_2.4 or private_5
                                             or guest_2.4 or guest_5
        :type wifi_mode: string
        :param operating_mode: wifi operating mode
        :type operating_mode: string
        :return: ACS value or None
        :rtype: string or boolean
        """
        print("setting operating mode")
        if "2.4" in wifi_mode:
            if operating_mode == "802.11n":
                spectrummode = self.acs_data['operating_mode']['802.11n']
            elif operating_mode == "802.11g/n mixed":
                spectrummode = self.acs_data['operating_mode']['802.11g/n']
            elif operating_mode == "802.11b/g/n mixed":
                spectrummode = self.acs_data['operating_mode']['802.11b/g/n']
        elif "5" in wifi_mode:
            if operating_mode == "802.11ac":
                spectrummode = self.acs_data['operating_mode']['802.11ac']
            elif operating_mode == "802.11n/ac mixed":
                spectrummode = self.acs_data['operating_mode']['802.11n/ac']
            elif operating_mode == "802.11a/n/ac mixed":
                spectrummode = self.acs_data['operating_mode']['802.11a/n/ac']
        table_path = self._check_acspath_spectrum(wifi_mode)
        acs_value = self.acs_server.set(
            self.cpeid, table_path + '.' + 'OperatingStandards', spectrummode)
        self.board.expect(pexpect.TIMEOUT, timeout=20)
        return acs_value

    def set_ssid(self, wifi_mode, ssid_name):
        """Set wifi ssid name via acs

        :param wifi_mode: wifi network mode eg:private_2.4 or private_5
                                             or guest_2.4 or guest_5
        :type wifi_mode: string
        :param ssid_name: wifi ssid name to be set
        :type ssid_name: string
        :return: ACS value or None
        :rtype: string or boolean
        """
        print("Setting ssid name")
        table_path = self._check_acspath_spectrum(wifi_mode, ssid_flag=1)
        acs_value = self.acs_server.set(self.cpeid, table_path + '.' + 'SSID',
                                        ssid_name)
        self.board.expect(pexpect.TIMEOUT, timeout=20)
        return acs_value

    def set_password(self, wifi_mode, password):
        """Set wifi password via acs

        :param wifi_mode: wifi network mode eg:private_2.4 or private_5
                                             or guest_2.4 or guest_5
        :type wifi_mode: string
        :param password: wifi password to be set
        :type password: string
        :return: ACS value or None
        :rtype: string or boolean
        """
        print("setting the password")
        table_path = self._check_acspath_spectrum(wifi_mode, ssid_flag=2)
        acs_value = self.acs_server.set(
            self.cpeid, table_path + '.' + 'Security' + '.' + 'KeyPassphrase',
            password)
        self.board.expect(pexpect.TIMEOUT, timeout=20)
        return acs_value

    def set_broadcast(self, wifi_mode):
        """Wifi broadcast enable via acs

        :param wifi_mode: wifi network mode eg:private_2.4 or private_5
                                             or guest_2.4 or guest_5
        :type wifi_mode: string
        :return: ACS value or None
        :rtype: string or boolean
        """
        print("setting the broadcast")
        table_path = self._check_acspath_spectrum(wifi_mode, ssid_flag=2)
        acs_value = self.acs_server.set(
            self.cpeid, table_path + '.' + 'SSIDAdvertisementEnabled', 1)
        self.board.expect(pexpect.TIMEOUT, timeout=20)
        return acs_value

    def set_security(self, wifi_mode, security):
        """Set wifisecurity via acs

        :param wifi_mode: wifi network mode eg:private_2.4 or private_5
                                             or guest_2.4 or guest_5
        :type wifi_mode: string
        :param security: wifi security to be set
        :type security: string
        :return: ACS value or None
        :rtype: string or boolean
        """
        print("setting security")
        table_path = self._check_acspath_spectrum(wifi_mode, ssid_flag=2)
        if security == "Disabled":
            security_value = self.acs_data['security_mode']['Disabled']
        elif security == "WPA2-PSK":
            security_value = self.acs_data['security_mode']['WPA2-PSK']
        elif security == "WPA-PSK/WPA2-PSK":
            security_value = self.acs_data['security_mode']['WPA-PSK/WPA2-PSK']
        acs_value = self.acs_server.set(
            self.cpeid, table_path + '.' + 'Security' + '.' + 'ModeEnabled',
            security_value)
        self.board.expect(pexpect.TIMEOUT, timeout=20)
        return acs_value

    def get_wifi_enabled(self, wifi_mode):
        """Check wifi enabled via acs

        :param wifi_mode: wifi network mode eg:private_2.4 or private_5
                                             or guest_2.4 or guest_5
        :type wifi_mode: string
        :return: ACS value or None
        :rtype: string or boolean
        """
        table_path = self._check_acspath_spectrum(wifi_mode)
        acs_value = self.acs_server.get(self.cpeid,
                                        table_path + '.' + 'Enable')
        return acs_value

    def get_channel_number(self, wifi_mode):
        """Get wifi channel number via acs

        :param wifi_mode: wifi network mode eg:private_2.4 or private_5
                                             or guest_2.4 or guest_5
        :type wifi_mode: string
        :return: ACS value or None
        :rtype: string or boolean
        """
        print("Getting the channel number")
        table_path = self._check_acspath_spectrum(wifi_mode)
        acs_value = self.acs_server.get(self.cpeid,
                                        table_path + '.' + 'Channel')
        return acs_value

    def get_bandwidth(self, wifi_mode):
        """Get wifi bandwidth via acs

        :param wifi_mode: wifi network mode eg:private_2.4 or private_5
                                             or guest_2.4 or guest_5
        :type wifi_mode: string
        :return: ACS value or None
        :rtype: string or boolean
        """
        print("Getting bandwidth")
        table_path = self._check_acspath_spectrum(wifi_mode)
        acs_value = self.acs_server.get(
            self.cpeid, table_path + '.' + 'OperatingChannelBandwidth')
        return acs_value

    def get_operating_mode(self, wifi_mode):
        """Get wifi operating mode via acs

        :param wifi_mode: wifi network mode eg:private_2.4 or private_5
                                             or guest_2.4 or guest_5
        :type wifi_mode: string
        :return: ACS value or None
        :rtype: string or boolean
        """
        print("Getting operating mode")
        table_path = self._check_acspath_spectrum(wifi_mode)
        acs_value = self.acs_server.get(
            self.cpeid, table_path + '.' + 'OperatingStandards')
        return acs_value

    def get_ssid(self, wifi_mode):
        """Get wifi ssid via acs

        :param wifi_mode: wifi network mode eg:private_2.4 or private_5
                                             or guest_2.4 or guest_5
        :type wifi_mode: string
        :return: ACS value or None
        :rtype: string or boolean
        """
        print("Getting ssid name")
        table_path = self._check_acspath_spectrum(wifi_mode, ssid_flag=1)
        acs_value = self.acs_server.get(self.cpeid, table_path + '.' + 'SSID')
        return acs_value

    def get_password(self, wifi_mode):
        """Get wifi password via acs

        :param wifi_mode: wifi network mode eg:private_2.4 or private_5
                                             or guest_2.4 or guest_5
        :type wifi_mode: string
        :return: ACS value or None
        :rtype: string or boolean
        """
        print("Getting password")
        table_path = self._check_acspath_spectrum(wifi_mode, ssid_flag=2)
        vendor_path = self.acs_data['password_object']['password_data']
        acs_value = self.acs_server.get(
            self.cpeid, table_path + '.' + 'Security' + '.' + vendor_path)
        return acs_value

    def get_broadcast(self, wifi_mode):
        """Get wifi broadcast via acs

        :param wifi_mode: wifi network mode eg:private_2.4 or private_5
                                             or guest_2.4 or guest_5
        :type wifi_mode: string
        :return: ACS value or None
        :rtype: string or boolean
        """
        print("Getting the broadcast")
        table_path = self._check_acspath_spectrum(wifi_mode, ssid_flag=2)
        acs_value = self.acs_server.get(
            self.cpeid, table_path + '.' + 'SSIDAdvertisementEnabled')
        return acs_value

    def get_security(self, wifi_mode):
        """Get wifi security via acs

        :param wifi_mode: wifi network mode eg:private_2.4 or private_5
                                             or guest_2.4 or guest_5
        :type wifi_mode: string
        :return: ACS value or None
        :rtype: string or boolean
        """
        print("Getting security")
        table_path = self._check_acspath_spectrum(wifi_mode, ssid_flag=2)
        acs_value = self.acs_server.get(
            self.cpeid, table_path + '.' + 'Security' + '.' + 'ModeEnabled')
        return acs_value
