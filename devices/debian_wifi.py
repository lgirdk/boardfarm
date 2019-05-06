import re, time
import debian
import pexpect
from countrycode import countrycode
from lib.wifi import wifi_client_stub
import pdb

class DebianWifi(debian.DebianBox, wifi_client_stub):
    '''Extension of Debian class with wifi functions'''

    model = ('debianwifi')
    wifi_interface = "wlan0"
    wifi_interface1 = "wlan1"

    wifi_client_control = None

    def disable_and_enable_wifi(self, iface):
       self.set_link_state(iface,"down")
       self.set_link_state(iface,"up")

    def wifi_scan(self, iface, ssid_name=None):
        from tests.lib.installers import install_iw
        install_iw(self)

        self.sudo_sendline('iw %s scan | grep SSID:' % iface)
        idx = self.expect(["password for .*:"] + self.prompt,timeout=20)
        if idx == 0:
            self.sendline(self.password)
            self.expect(self.prompt)
        return self.before

    def wifi_connect(self, iface, ssid_name, password=None, security_mode=8):
        if password == None:
            self.sudo_sendline("iwconfig %s essid %s" % (iface,ssid_name))
            idx = self.expect(["password for .*:"] + self.prompt,timeout=20)
            if idx == 0:
                self.sendline(self.password)
                self.expect(self.prompt)
        else:
            '''Generate WPA supplicant file and execute it'''
            self.sudo_sendline("rm "+ssid_name+".conf")
            idx = self.expect(["password for .*:"] + self.prompt,timeout=20)
            if idx == 0:
                self.sendline(self.password)
                self.expect(self.prompt)
            self.sudo_sendline("wpa_passphrase "+ssid_name+" "+password+" >> "+ssid_name+".conf")
            idx = self.expect(["password for .*:"] + self.prompt,timeout=20)
            if idx == 0:
                self.sendline(self.password)
                self.expect(self.prompt)
            self.sendline("cat "+ssid_name+".conf")
            self.expect(self.prompt)
            self.sudo_sendline("wpa_supplicant  -B -Dnl80211 -i"+iface+ " -c"+ssid_name+".conf")
            idx = self.expect(["password for .*:"] + self.prompt,timeout=20)
            if idx == 0:
                self.sendline(self.password)
                self.expect(self.prompt)
            wpa_start = None
            wpa_start = self.before
            match = re.search('Successfully initialized wpa_supplicant',wpa_start)
            if match:
                return match.group(0)
            else:
                return None

    def wifi_connectivity_verify(self, iface):
        '''Connection state verify'''
        self.sendline("iw %s link" % iface)
        self.expect(self.prompt)
        match = re.search('Connected', self.before)
        if match:
            return match.group(0)
        else:
            return None

    def disconnect_wpa(self):
        self.sudo_sendline("killall wpa_supplicant")
        idx = self.expect(["password for .*:"] + self.prompt,timeout=20)
        if idx == 0:
            self.sendline(self.password)
            self.expect(self.prompt)

    def wifi_ssid_disconnect(self, iface):
        self.sudo_sendline("iw dev %s disconnect" % iface)
        idx = self.expect(["password for .*:"] + self.prompt,timeout=20)
        if idx == 0:
            self.sendline(self.password)
            self.expect(self.prompt)

    def wifi_disconnect(self, iface):
        self.disconnect_wpa()
        self.wifi_ssid_disconnect(iface)

    def wifi_change_region(self, country):
        country = countrycode(country, origin='country_name', target='iso2c')
        self.sudo_sendline("iw reg set %s"%(country))
        idx = self.expect(["password for .*:"] + self.prompt,timeout=20)
        if idx == 0:
            self.sendline(self.password)
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

    def linux_client_connect(self, iface, ssid_name, password=None):
        '''Scan for SSID and verify connectivity'''
        self.disable_and_enable_wifi(iface)
        time.sleep(10)
        output = self.wifi_scan(iface)
        match = re.search("%s" % ssid_name,output)
        assert match!=None,'SSID value check in WLAN container'

        conn_wifi = self.wifi_connect(iface,ssid_name,password)
        assert conn_wifi!=None,'WIFI connect'

        time.sleep(20)
        verify_connect = self.wifi_connectivity_verify(iface)
        assert verify_connect!=None,'Connection establishment in WIFI'
