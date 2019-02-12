import re
import debian
import pexpect
from devices import wlan, board, prompt
from lib.regexlib import ValidIpv4AddressRegex

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

    def wlan_ssid_connect(self, ssid_name):
        self.sendline("iwconfig %s essid %s" % (self.iface_wlan,ssid_name))
        self.expect(self.prompt)

    def wlan_ssid_disconnect(self):
        self.sendline("iw dev %s disconnect" % self.iface_wlan)
        self.expect(self.prompt)

    def start_lan_client(self, wan_gw=None):
        self.iface_dut = self.iface_wlan
        super(DebianWifi, self).start_lan_client()

    def linux_wifi_client(self, board, ssid_name, password=None):
        '''Scan for SSID and verify connectivity'''
        output = self.scan()
        match = re.search("%s" % ssid_name,output)
        assert match!=None,'SSID value check in WLAN container'

        link = self.link_up(self.iface_wlan)
        if link==None:
            wlan.set_link_state(self.iface_wlan)

        if password:
            conn_wpa = self.wpa_connect(ssid_name,password)
            assert conn_wpa!=None,'WPA supplicant initiation'
        else:
            self.wlan_ssid_connect(ssid_name)

        board.expect(pexpect.TIMEOUT, timeout=20)
        conn_wlan = self.wlan_connectivity()
        assert conn_wlan!=None,'Connection establishment in WIFI'

        self.start_lan_client()

