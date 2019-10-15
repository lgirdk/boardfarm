import pexpect, re
from wifi import wifi_stub

class wifi_acs(wifi_stub):
    #for acs connect func it is required
    log_to_file = ""

    def __init__(self, wan, board, acs_server):
        self.wan = wan
        self.board = board
        self.acs_server = acs_server
        self.serial_number = board.get_serial_number(wan)
        self.acs_data = self.board.wifi_acs_file

    def prepare(self):
        #Getting boot file name via ACS to ensure connectivity exist or not
        #If it returns none , ACS connectivity happens
        acs_value = self.acs_server.get(self.serial_number,'Device.DeviceInfo.SerialNumber')
        if acs_value == None:
            self.board.restart_tr069(self)

    def _check_acspath_spectrum(self, wifi_mode, ssid_flag=0):
        acs_path = "Device.WiFi."
        if ssid_flag == 0:
            if "2.4" in wifi_mode:
                table_path = acs_path+"Radio."+self.acs_data['wifi_path']['Radio_2.4']
            elif "5" in wifi_mode:
                table_path = acs_path+"Radio."+self.acs_data['wifi_path']['Radio_5']
        elif ssid_flag == 1:
            if "2.4" in wifi_mode:
                table_path = acs_path+"SSID."+self.acs_data['wifi_path']['SSID_2.4']
            elif "5" in wifi_mode:
                table_path = acs_path+"SSID."+self.acs_data['wifi_path']['SSID_5']
        elif ssid_flag == 2:
            if "2.4" in wifi_mode:
                table_path = acs_path+"AccessPoint."+self.acs_data['wifi_path']['Access_Point_2.4']
            elif "5" in wifi_mode:
                table_path = acs_path+"AccessPoint."+self.acs_data['wifi_path']['Access_Point_5']
        return table_path

    def enable_wifi(self, wifi_mode):
        #importing self.acs_server for each func, because global import not working
        table_path = self._check_acspath_spectrum(wifi_mode)
        acs_value = self.acs_server.set(self.serial_number,table_path+'.'+'Enable',1)
        #timeout requires for all func as it takes time to set in acs server
        self.board.expect(pexpect.TIMEOUT, timeout=20)
        return acs_value

    def disable_wifi(self, wifi_mode):
        table_path = self._check_acspath_spectrum(wifi_mode)
        acs_value = self.acs_server.set(self.serial_number,table_path+'.'+'Enable',0)
        self.board.expect(pexpect.TIMEOUT, timeout=20)
        return acs_value

    def set_channel_number(self, wifi_mode, channel_number):
        print("Setting the channel mode")
        table_path = self._check_acspath_spectrum(wifi_mode)
        if int(channel_number) > 0 :
            acs_value = self.acs_server.set(self.serial_number,table_path+'.'+'Channel', int(channel_number))
        else:
            acs_value = self.acs_server.set(self.serial_number,table_path+'.'+'AutoChannelEnable',1)
        self.board.expect(pexpect.TIMEOUT, timeout=30)
        return acs_value

    def set_bandwidth(self, wifi_mode, bandwidth, channel_number):
        print("setting bandwidth")
        bandwidth =  re.sub(' ', '', bandwidth)
        table_path = self._check_acspath_spectrum(wifi_mode)
        acs_value = self.acs_server.set(self.serial_number,table_path+'.'+'OperatingChannelBandwidth',bandwidth)
        self.board.expect(pexpect.TIMEOUT, timeout=20)
        return acs_value

    def set_operating_mode(self, wifi_mode, operating_mode):
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
        acs_value = self.acs_server.set(self.serial_number,table_path+'.'+'OperatingStandards',spectrummode)
        self.board.expect(pexpect.TIMEOUT, timeout=20)
        return acs_value

    def set_ssid(self, wifi_mode, ssid_name):
        print("Setting ssid name")
        table_path = self._check_acspath_spectrum(wifi_mode, ssid_flag=1)
        acs_value = self.acs_server.set(self.serial_number,table_path+'.'+'SSID',ssid_name)
        self.board.expect(pexpect.TIMEOUT, timeout=20)
        return acs_value

    def set_password(self, wifi_mode, password):
        print("setting the password")
        table_path = self._check_acspath_spectrum(wifi_mode, ssid_flag=2)
        acs_value = self.acs_server.set(self.serial_number,table_path+'.'+'Security'+'.'+'KeyPassphrase', password)
        self.board.expect(pexpect.TIMEOUT, timeout=20)
        return acs_value

    def set_broadcast(self, wifi_mode):
        print("setting the broadcast")
        table_path = self._check_acspath_spectrum(wifi_mode, ssid_flag=2)
        acs_value = self.acs_server.set(self.serial_number,table_path+'.'+'SSIDAdvertisementEnabled', 1)
        self.board.expect(pexpect.TIMEOUT, timeout=20)
        return acs_value

    def set_security(self, wifi_mode, security):
        print("setting security")
        table_path = self._check_acspath_spectrum(wifi_mode, ssid_flag=2)
        if security == "Disabled":
            security_value = self.acs_data['security_mode']['Disabled']
        elif security == "WPA2-PSK":
            security_value = self.acs_data['security_mode']['WPA2-PSK']
        elif security == "WPA-PSK/WPA2-PSK":
            security_value = self.acs_data['security_mode']['WPA-PSK/WPA2-PSK']
        acs_value = self.acs_server.set(self.serial_number,table_path+'.'+'Security'+'.'+'ModeEnabled', security_value)
        self.board.expect(pexpect.TIMEOUT, timeout=20)
        return acs_value

    def get_wifi_enabled(self, wifi_mode):
        table_path = self._check_acspath_spectrum(wifi_mode)
        acs_value = self.acs_server.get(self.serial_number,table_path+'.'+'Enable')
        return acs_value

    def get_channel_number(self, wifi_mode):
        print("Getting the channel number")
        table_path = self._check_acspath_spectrum(wifi_mode)
        acs_value = self.acs_server.get(self.serial_number,table_path+'.'+'Channel')
        return acs_value

    def get_bandwidth(self, wifi_mode):
        print("Getting bandwidth")
        table_path = self._check_acspath_spectrum(wifi_mode)
        acs_value = self.acs_server.get(self.serial_number,table_path+'.'+'OperatingChannelBandwidth')
        return acs_value

    def get_operating_mode(self, wifi_mode):
        print("Getting operating mode")
        table_path = self._check_acspath_spectrum(wifi_mode)
        acs_value = self.acs_server.get(self.serial_number,table_path+'.'+'OperatingStandards')
        return acs_value

    def get_ssid(self, wifi_mode):
        print("Getting ssid name")
        table_path = self._check_acspath_spectrum(wifi_mode, ssid_flag=1)
        acs_value = self.acs_server.get(self.serial_number,table_path+'.'+'SSID')
        return acs_value

    def get_password(self, wifi_mode):
        print("Getting password")
        table_path = self._check_acspath_spectrum(wifi_mode, ssid_flag=2)
        vendor_path = self.acs_data['password_object']['password_data']
        acs_value = self.acs_server.get(self.serial_number,table_path+'.'+'Security'+'.'+vendor_path)
        return acs_value

    def get_broadcast(self, wifi_mode):
        print("Getting the broadcast")
        table_path = self._check_acspath_spectrum(wifi_mode, ssid_flag=2)
        acs_value = self.acs_server.get(self.serial_number,table_path+'.'+'SSIDAdvertisementEnabled')
        return acs_value

    def get_security(self, wifi_mode):
        print("Getting security")
        table_path = self._check_acspath_spectrum(wifi_mode, ssid_flag=2)
        acs_value = self.acs_server.get(self.serial_number,table_path+'.'+'Security'+'.'+'ModeEnabled')
        return acs_value
