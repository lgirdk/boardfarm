import re
from lib.logging import logfile_assert_message
import debian
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

    def wlan_connect(self,ssid_val):
        board.expect(pexpect.TIMEOUT, timeout=25)
        '''Connection state verify'''
        self.sendline("iw %s link"  % self.iface_wlan)
        self.expect(self.prompt)
        conn_state = self.before
        match = re.search('Connected',conn_state)
        logfile_assert_message(self, match!=None,'Connection establishment in WIFI')
        match = re.search(ssid_val,conn_state)
        logfile_assert_message(self, match!=None,'Connection establishment - SSID verify')
        self.sendline("dhclient -v %s"  % self.iface_wlan)
        self.expect(self.prompt,timeout=40)

    def ping_hostname(self):
        '''Ping test'''
        hostname = "google.com"
        self.sendline("ping -c 1 " + hostname)
        self.expect(self.prompt)
        ping_result = self.before
        match = re.search("1 packets transmitted, 1 received, 0% packet loss",ping_result)
        logfile_assert_message(self, match!=None,'Host Ping status')

    def ping_gateway(self):
        self.sendline("ifconfig %s"  % self.iface_wlan)
        self.expect(self.prompt)
        ifconfig_res = self.before
        match = re.search(r'inet ([0-9]+\.[0-9]+\.[0-9]+)\.([0-9]+).*',ifconfig_res)
        logfile_assert_message(self, match!=None,'Ifconfig wlan IP fetch')
        gateway_ip = match.group(1) + ".1"
        ip = match.group(2)
        value = range(2,255)
        match = re.search(ip,str(value))
        logfile_assert_message(self, match!=None,'Ifconfig wlan IP verify')
        self.sendline("ping -c 1 " + gateway_ip)
        self.expect(self.prompt)
        ping_res = self.before
        match = re.search("1 packets transmitted, 1 received, 0% packet loss",ping_res)
        logfile_assert_message(self, match!=None,'Gateway Ping status')

    def link_up(self):
        self.sendline("ip link show %s"  % self.iface_wlan)
        self.expect(self.prompt)
        link_state = self.before
        match = re.search('NO-CARRIER,BROADCAST,MULTICAST,UP',link_state)
        if match==None:
            self.sendline("ip link set %s up"  % self.iface_wlan)
            self.expect(self.prompt)
            logfile_assert_message(self, True,'Setting Link up')
        else:
            logfile_assert_message(self, True,'Link is up')

    def kill_suplicant(self):
        self.sendline("killall wpa_supplicant")
        self.expect(self.prompt)
