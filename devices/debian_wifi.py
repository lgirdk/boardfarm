import debian
import re
from devices import wlan

class DebianWifi(debian.DebianBox):
    '''Extension of Debian class with wifi functions'''

    model = ('debianwifi')
    log_to_file = ""
    iface_wlan = "wlan1"

    def scan(self):
        self.sendline('iw %s scan | grep SSID:' % self.iface_wlan)
        self.expect(self.prompt)

        return self.before

    def wpa_connect(self,ssid_name,pass_word):
         '''Generate WPA supplicant file and execute it'''
         self.sendline("rm /etc/"+ssid_name+".conf")
         self.expect(self.prompt)
         self.sendline("wpa_passphrase "+ssid_name+ " >> /etc/"+ssid_name+".conf")
         self.expect("")
         self.sendline(pass_word)
         self.expect(self.prompt)
         self.sendline("cat /etc/"+ssid_name+".conf")
         self.expect(self.prompt)
         self.sendline("wpa_supplicant  -B -Dnl80211 -iwlan1 -c/etc/"+ssid_name+".conf")
         self.expect(self.prompt)
         wpa_start = None
         wpa_start = self.before
         match = re.search('Successfully initialized wpa_supplicant',wpa_start)
         if match:
            return match.group(0)
         else:
            return None

    def wlan_connect(self,ssid_val):
        '''Connection state verify'''
        self.sendline("iw wlan1 link")
        self.expect(self.prompt)
        conn_state = self.before
        match = re.search('Connected',conn_state)
        if match:
            return match.group(0)
        else:
            return None

    def link_up(self):
        self.sendline("ip link show wlan1")
        self.expect(self.prompt)
        link_state = self.before
        match = re.search('NO-CARRIER,BROADCAST,MULTICAST,UP',link_state)
        if match:
            return match.group(0)
        else:
            return None

    def kill_supplicant(self):
        self.sendline("killall wpa_supplicant")
        self.expect(self.prompt)
