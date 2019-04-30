import re
import debian
import pexpect

class DebianWifi(debian.DebianBox):
    '''Extension of Debian class with wifi functions'''

    model = ('debianwifi')

    def wifi_scan(self, iface_wlan="wlan1", login_pwd=None):
        from tests.lib.installers import install_iw
        install_iw(self)

        self.sendline('iw %s scan | grep SSID:' % iface_wlan)
        self.expect(self.prompt)
        match = re.search("Operation not permitted", self.before)
        if match:
            self.sendline('sudo iw %s scan | grep SSID:' % iface_wlan)
            idx = self.expect(["password for .*:"] + self.prompt,timeout=20)
            if idx == 0:
                self.sendline(login_pwd)
                self.expect(self.prompt)
        return self.before

    def wpa_connect(self, ssid_name, password, iface_wlan="wlan1", login_pwd=None):
         '''Generate WPA supplicant file and execute it'''
         self.sendline("rm "+ssid_name+".conf")
         self.expect(self.prompt)
         self.sendline("wpa_passphrase "+ssid_name+" "+password+" >> "+ssid_name+".conf")
         self.expect(self.prompt)
         self.sendline("cat "+ssid_name+".conf")
         self.expect(self.prompt)
         self.sendline("wpa_supplicant  -B -Dnl80211 -i"+iface_wlan+ " -c"+ssid_name+".conf")
         self.expect(self.prompt)
         match = re.search("Failed to initialize driver interface",self.before)
         if match:
             self.sendline("sudo wpa_supplicant  -B -Dnl80211 -i"+iface_wlan+ " -c"+ssid_name+".conf")
             idx = self.expect(["password for .*:"] + self.prompt,timeout=20)
             if idx == 0:
                 self.sendline(login_pwd)
                 self.expect(self.prompt)
         wpa_start = None
         wpa_start = self.before
         match = re.search('Successfully initialized wpa_supplicant',wpa_start)
         if match:
            return match.group(0)
         else:
            return None

    def wlan_connectivity(self, iface_wlan="wlan1", login_pwd=None):
        '''Connection state verify'''
        self.sendline("iw %s link" % iface_wlan)
        try:
            wlan_connect = self.expect('Connected', timeout=5)
            self.expect(self.prompt)
        except:
            self.sendline("sudo iw %s link" % iface_wlan)
            idx = self.expect(["password for .*:"] + self.prompt,timeout=20)
            if idx == 0:
                self.sendline(login_pwd)
                wlan_connect = self.expect('Connected', timeout=5)
                self.expect(self.prompt)
        if wlan_connect == 0:
            return "Connected"
        else:
            return None

    def disconnect_wpa(self, login_pwd=None):
        self.sendline("killall wpa_supplicant")
        self.expect(self.prompt)
        match = re.search("Operation not permitted", self.before)
        if match:
            self.sendline("sudo killall wpa_supplicant")
            idx = self.expect(["password for .*:"] + self.prompt,timeout=20)
            if idx == 0:
                self.sendline(login_pwd)
                self.expect(self.prompt)

    def wlan_ssid_connect(self, ssid_name, iface_wlan="wlan1", login_pwd=None):
        self.sendline("iwconfig %s essid %s" % (iface_wlan,ssid_name))
        self.expect(self.prompt)
        match = re.search("Operation not permitted", self.before)
        if match:
            self.sendline("sudo iwconfig %s essid %s" % (iface_wlan,ssid_name))
            idx = self.expect(["password for .*:"] + self.prompt,timeout=20)
            if idx == 0:
                self.sendline(login_pwd)
                self.expect(self.prompt)

    def wlan_ssid_disconnect(self, iface_wlan="wlan1", login_pwd=None):
        self.sendline("iw dev %s disconnect" % iface_wlan)
        self.expect(self.prompt)
        match = re.search("Operation not permitted", self.before)
        if match:
            self.sendline("sudo iw dev %s disconnect" % iface_wlan)
            idx = self.expect(["password for .*:"] + self.prompt,timeout=20)
            if idx == 0:
                self.sendline(login_pwd)
                self.expect(self.prompt)

    def start_lan_client(self, iface_wlan, wan_gw=None):
        self.iface_dut = iface_wlan
        super(DebianWifi, self).start_lan_client()

    def linux_wifi_client(self, board, ssid_name, password=None, iface_wlan="wlan1", login_pwd=None):
        '''Scan for SSID and verify connectivity'''
        output = self.wifi_scan(iface_wlan, login_pwd)
        match = re.search("%s" % ssid_name,output)
        assert match!=None,'SSID value check in WLAN container'

        link = self.link_up(iface_wlan)
        if link==None:
            self.set_link_state(iface_wlan,"up",login_pwd)

        if password:
            conn_wpa = self.wpa_connect(ssid_name,password,iface_wlan,login_pwd)
            assert conn_wpa!=None,'WPA supplicant initiation'
        else:
            self.wlan_ssid_connect(ssid_name,iface_wlan,login_pwd)

        board.expect(pexpect.TIMEOUT, timeout=20)
        conn_wlan = self.wlan_connectivity(iface_wlan,login_pwd)
        assert conn_wlan!=None,'Connection establishment in WIFI'
