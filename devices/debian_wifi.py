
import re
import debian


class DebianWifi(debian.DebianBox):
    '''Extension of Debian class with wifi functions'''

    model = ('debianwifi')

    iface_wlan = "wlan1"

    def scan(self):
        from tests.lib.installers import install_iw
        install_iw(self)

        self.sendline('iw %s scan | grep SSID:' % self.iface_wlan)
        self.expect(self.prompt)

        return self.before

    def wpa_connect(self, ssid_name, password):
         '''Generate WPA supplicant file and execute it'''
         self.sendline("rm /etc/"+ssid_name+".conf")
         self.expect(self.prompt)
         self.sendline("wpa_passphrase "+ssid_name+ " >> /etc/"+ssid_name+".conf")
         self.expect("")
         self.sendline(password)
         self.expect(self.prompt,timeout=20)
         self.sendline("cat /etc/"+ssid_name+".conf")
         self.expect(self.prompt)
         self.sendline("wpa_supplicant  -B -Dnl80211 -i"+self.iface_wlan+ " -c/etc/"+ssid_name+".conf")
         self.expect(self.prompt)
         wpa_start = None
         wpa_start = self.before
         match = re.search('Successfully initialized wpa_supplicant',wpa_start)
         if match:
            return match.group(0)
         else:
            return None

    def wlan_connectivity(self):
        '''Connection state verify'''
        self.sendline("iw %s link" % self.iface_wlan)
        self.expect(self.prompt)
        conn_state = self.before
        match = re.search('Connected',conn_state)
        if match:
            return match.group(0)
        else:
            return None

    def disconnect_wpa(self):
        self.sendline("killall wpa_supplicant")
        self.expect(self.prompt)
