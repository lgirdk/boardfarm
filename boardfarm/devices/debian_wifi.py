"""Extension of Debian class with wifi functions
"""
import re
from . import debian
import pexpect
from countrycode import countrycode
from boardfarm.lib.wifi import wifi_client_stub


class DebianWifi(debian.DebianBox, wifi_client_stub):
    """Extension of Debian class with wifi functions
    wifi_client_stub is inherited from lib/wifi.py
    """
    model = ('debianwifi')

    def __init__(self, *args, **kwargs):
        """Constructor method to initialise wifi interface
        """
        super(DebianWifi, self).__init__(*args, **kwargs)
        self.iface_dut = self.iface_wifi = self.kwargs.get(
            'dut_interface', 'wlan1')

    def disable_and_enable_wifi(self):
        """Disable and enable wifi interface
        i.e., set the interface link to "down" and then to "up"
        This calls the disable wifi and enable wifi methods
        """
        self.disable_wifi()
        self.enable_wifi()

    def disable_wifi(self):
        """Disabling the wifi interface
        setting the interface link to "down"
        """
        self.set_link_state(self.iface_wifi, "down")

    def enable_wifi(self):
        """Enabling the wifi interface
        setting the interface link to "up"
        """
        self.set_link_state(self.iface_wifi, "up")

    def release_wifi(self):
        """DHCP release of the wifi interface
        """
        iface = self.iface_wifi
        self.release_dhcp(iface)

    def wifi_scan(self):
        """Scanning the SSID associated with the wifi interface

        :return: List of SSID
        :rtype: string
        """
        from boardfarm.lib.installers import install_iw
        install_iw(self)

        self.sudo_sendline('iw %s scan | grep SSID:' % self.iface_wifi)
        self.expect(self.prompt)
        return self.before

    def wifi_check_ssid(self, ssid_name):
        """Check the SSID provided is present in the scan list

        :param ssid_name: SSID name to be verified
        :type ssid_name: string
        :return: True or False
        :rtype: boolean
        """
        from boardfarm.lib.installers import install_iw
        install_iw(self)

        self.sudo_sendline('iw %s scan | grep "SSID: %s"' %
                           (self.iface_wifi, ssid_name))
        self.expect(self.prompt)
        match = re.search(r"%s\"\s+.*(%s)" % (ssid_name, ssid_name),
                          self.before)
        if match:
            return True
        else:
            return False

    def wifi_connect(self, ssid_name, password=None, security_mode=None):
        """Initialise wpa supplicant file if wifi has password else
        connect the wifi through iwconfig

        :param ssid_name: SSID name
        :type ssid_name: string
        :param password: wifi password, defaults to None
        :type password: string, optional
        :param security_mode: Security mode for the wifi, defaults to None
        :type security_mode: string, optional
        :return: True or False
        :rtype: boolean
        """
        if password == None:
            self.sudo_sendline("iwconfig %s essid %s" %
                               (self.iface_wifi, ssid_name))
        else:
            '''Generate WPA supplicant file and execute it'''
            self.sudo_sendline("rm " + ssid_name + ".conf")
            self.expect(self.prompt)
            self.sudo_sendline("wpa_passphrase " + ssid_name + " " + password +
                               " >> " + ssid_name + ".conf")
            self.expect(self.prompt)
            self.sendline("cat " + ssid_name + ".conf")
            self.expect(self.prompt)
            self.sudo_sendline("wpa_supplicant  -B -Dnl80211 -i" +
                               self.iface_wifi + " -c" + ssid_name + ".conf")
            self.expect(self.prompt)
            match = re.search('Successfully initialized wpa_supplicant',
                              self.before)
            if match:
                return True
            else:
                return False

    def wifi_connectivity_verify(self):
        """Verify wifi is in teh connected state

        :return: True or False
        :rtype: boolean
        """
        self.sendline("iw %s link" % self.iface_wifi)
        self.expect(self.prompt)
        match = re.search('Connected', self.before)
        if match:
            return True
        else:
            return False

    def wifi_connect_check(self, ssid_name, password=None):
        """Connect to a SSID and verify
            WIFI connectivity

        :param ssid_name: SSID name
        :type ssid_name: string
        :param password: wifi password, defaults to None
        :type password: string, optional
        :return: True or False
        :rtype: boolean
        """
        for i in range(5):
            self.wifi_connect(ssid_name, password)
            self.expect(pexpect.TIMEOUT, timeout=10)
            verify_connect = self.wifi_connectivity_verify()
            if verify_connect:
                break
            else:
                self.wifi_disconnect()
        return verify_connect

    def disconnect_wpa(self):
        """Disconnect the wpa supplicant initialisation
        """
        self.sudo_sendline("killall wpa_supplicant")
        self.expect(self.prompt)

    def wlan_ssid_disconnect(self):
        """Disconnect the wifi connectivity if connected
        through iwconfig method using ssid alone
        """
        self.sudo_sendline("iw dev %s disconnect" % self.iface_wifi)
        self.expect(self.prompt)

    def wifi_disconnect(self):
        """Common method to disconnect wifi connectivity
        by disconnecting wpa supplicant initialisation as well as
        iwconfig disconnection
        """
        self.disconnect_wpa()
        self.wlan_ssid_disconnect()

    def wifi_change_region(self, country):
        """Change the region of the wifi

        :param country: region to be set
        :type country: string
        :return: country name if matched else None
        :rtype: string or boolean
        """
        country = countrycode(country, origin='country_name', target='iso2c')
        self.sudo_sendline("iw reg set %s" % (country))
        self.expect(self.prompt)
        self.sendline("iw reg get")
        self.expect(self.prompt)
        match = re.search(country, self.before)
        if match:
            return match.group(0)
        else:
            return None

    def start_lan_client(self):
        """Start_lan_method execution for the wifi interface
        """
        self.iface_dut = self.iface_wifi
        super(DebianWifi, self).start_lan_client()

    def wifi_client_connect(self,
                            ssid_name,
                            password=None,
                            security_mode=None):
        """Scan for SSID and verify wifi connectivity

        :param ssid_name: SSID name
        :type ssid_name: string
        :param password: wifi password, defaults to None
        :type password: string, optional
        :param security_mode: Security mode for the wifi, defaults to None
        :type security_mode: string, optional
        :raise assertion: If SSID value check in WLAN container fails,
                          If connection establishment in WIFI fails
        """
        self.disable_and_enable_wifi()
        self.expect(pexpect.TIMEOUT, timeout=20)
        output = self.wifi_check_ssid(ssid_name)
        assert output == True, 'SSID value check in WLAN container'

        self.wifi_connect(ssid_name, password)
        self.expect(pexpect.TIMEOUT, timeout=20)
        verify_connect = self.wifi_connectivity_verify()
        assert verify_connect == True, 'Connection establishment in WIFI'
