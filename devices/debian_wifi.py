import re
import debian
import pexpect
from countrycode import countrycode
from lib.wifi import wifi_client_stub

class DebianWifi(debian.DebianBox, wifi_client_stub):
    '''Extension of Debian class with wifi functions'''

    model = ('debianwifi')
    iface_wlan = "wlan0"
    iface_wlan1 = "wlan1"

    def disable_and_enable_wifi(self, iface):
       self.set_link_state(iface, "down")
       self.set_link_state(iface, "up")

    def disable_wifi(self, iface):
       self.set_link_state(iface, "down")

    def enable_wifi(self, iface):
       self.set_link_state(iface, "up")

    def wifi_scan(self, iface):
        from tests.lib.installers import install_iw
        install_iw(self)

        self.sudo_sendline('iw %s scan | grep SSID:' % iface)
        self.expect(self.prompt)
        return self.before

    def wifi_check_ssid(self, iface, ssid_name):
        from tests.lib.installers import install_iw
        install_iw(self)

        self.sudo_sendline('iw %s scan | grep "SSID: %s"' % (iface, ssid_name))
        self.expect(self.prompt)
        match = re.search("%s\"\s+.*(%s)"%(ssid_name, ssid_name), self.before)
        if match:
            return True
        else:
            return False

    def wifi_connect(self, iface, ssid_name, password=None, security_mode=None):
        if password == None:
            self.sudo_sendline("iwconfig %s essid %s" % (iface,ssid_name))
        else:
            '''Generate WPA supplicant file and execute it'''
            self.sudo_sendline("rm "+ssid_name+".conf")
            self.expect(self.prompt)
            self.sudo_sendline("wpa_passphrase "+ssid_name+" "+password+" >> "+ssid_name+".conf")
            self.expect(self.prompt)
            self.sendline("cat "+ssid_name+".conf")
            self.expect(self.prompt)
            self.sudo_sendline("wpa_supplicant  -B -Dnl80211 -i"+iface+ " -c"+ssid_name+".conf")
            self.expect(self.prompt)
            match = re.search('Successfully initialized wpa_supplicant', self.before)
            if match:
                return True
            else:
                return False

    def wifi_connectivity_verify(self, iface):
        '''Connection state verify'''
        self.sendline("iw %s link" % iface)
        self.expect(self.prompt)
        match = re.search('Connected', self.before)
        if match:
            return True
        else:
            return False

    def disconnect_wpa(self):
        self.sudo_sendline("killall wpa_supplicant")
        self.expect(self.prompt)

    def wlan_ssid_disconnect(self, iface):
        output = self.sudo_sendline("iw dev %s disconnect" % iface)
        self.expect(self.prompt)

    def wifi_disconnect(self, iface):
        self.disconnect_wpa()
        self.wlan_ssid_disconnect(iface)

    def wifi_change_region(self, country):
        country = countrycode(country, origin='country_name', target='iso2c')
        self.sudo_sendline("iw reg set %s"%(country))
        self.expect(self.prompt)
        self.sendline("iw reg get")
        self.expect(self.prompt)
        match = re.search(country, self.before)
        if match:
            return match.group(0)
        else:
            return None

    def start_lan_client(self, iface):
        self.iface_dut = iface
        super(DebianWifi, self).start_lan_client()

    def wifi_client_connect(self, iface, ssid_name, password=None):
        '''Scan for SSID and verify connectivity'''
        self.disable_and_enable_wifi(iface)
        self.expect(pexpect.TIMEOUT, timeout=20)
        output = self.wifi_check_ssid(iface, ssid_name)
        assert output==True,'SSID value check in WLAN container'

        conn_wifi = self.wifi_connect(iface, ssid_name, password)
        self.expect(pexpect.TIMEOUT, timeout=20)
        verify_connect = self.wifi_connectivity_verify(iface)
        assert verify_connect==True,'Connection establishment in WIFI'
