import re
import debian
import pexpect
from countrycode import countrycode
from boardfarm.lib.wifi import wifi_client_stub

class DebianWifi(debian.DebianBox, wifi_client_stub):
    '''Extension of Debian class with wifi functions'''

    model = ('debianwifi')
    def __init__(self, *args, **kwargs):
        super(DebianWifi,self).__init__( *args, **kwargs)
        self.iface_dut = self.iface_wifi = self.kwargs.get('dut_interface', 'wlan1')

    def disable_and_enable_wifi(self):
       self.disable_wifi()
       self.enable_wifi()

    def disable_wifi(self):
       self.set_link_state(self.iface_wifi, "down")

    def enable_wifi(self):
       self.set_link_state(self.iface_wifi, "up")

    def wifi_scan(self):
        from boardfarm.lib.installers import install_iw
        install_iw(self)

        self.sudo_sendline('iw %s scan | grep SSID:' % self.iface_wifi)
        self.expect(self.prompt)
        return self.before

    def wifi_check_ssid(self, ssid_name):
        from tests.lib.installers import install_iw
        install_iw(self)

        self.sudo_sendline('iw %s scan | grep "SSID: %s"' % (self.iface_wifi, ssid_name))
        self.expect(self.prompt)
        match = re.search("%s\"\s+.*(%s)"%(ssid_name, ssid_name), self.before)
        if match:
            return True
        else:
            return False

    def wifi_connect(self, ssid_name, password=None, security_mode=None):
        if password == None:
            self.sudo_sendline("iwconfig %s essid %s" % (self.iface_wifi,ssid_name))
        else:
            '''Generate WPA supplicant file and execute it'''
            self.sudo_sendline("rm "+ssid_name+".conf")
            self.expect(self.prompt)
            self.sudo_sendline("wpa_passphrase "+ssid_name+" "+password+" >> "+ssid_name+".conf")
            self.expect(self.prompt)
            self.sendline("cat "+ssid_name+".conf")
            self.expect(self.prompt)
            self.sudo_sendline("wpa_supplicant  -B -Dnl80211 -i"+self.iface_wifi+ " -c"+ssid_name+".conf")
            self.expect(self.prompt)
            match = re.search('Successfully initialized wpa_supplicant', self.before)
            if match:
                return True
            else:
                return False

    def wifi_connectivity_verify(self):
        '''Connection state verify'''
        self.sendline("iw %s link" % self.iface_wifi)
        self.expect(self.prompt)
        match = re.search('Connected', self.before)
        if match:
            return True
        else:
            return False

    def disconnect_wpa(self):
        self.sudo_sendline("killall wpa_supplicant")
        self.expect(self.prompt)

    def wlan_ssid_disconnect(self):
        output = self.sudo_sendline("iw dev %s disconnect" % self.iface_wifi)
        self.expect(self.prompt)

    def wifi_disconnect(self):
        self.disconnect_wpa()
        self.wlan_ssid_disconnect()

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

    def start_lan_client(self):
        self.iface_dut = self.iface_wifi
        super(DebianWifi, self).start_lan_client()

    def wifi_client_connect(self, ssid_name, password=None, security_mode=None):
        '''Scan for SSID and verify connectivity'''
        self.disable_and_enable_wifi()
        self.expect(pexpect.TIMEOUT, timeout=20)
        output = self.wifi_check_ssid(ssid_name)
        assert output==True,'SSID value check in WLAN container'

        conn_wifi = self.wifi_connect(ssid_name, password)
        self.expect(pexpect.TIMEOUT, timeout=20)
        verify_connect = self.wifi_connectivity_verify()
        assert verify_connect==True,'Connection establishment in WIFI'
