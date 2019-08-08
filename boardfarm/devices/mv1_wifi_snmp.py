import os, pexpect, re
from lib.wifi import wifi_stub
from lib.common import file_open_json, snmp_mib_get, snmp_mib_set

class wifi_snmp(wifi_stub):
    global mib_value
    mib_value = file_open_json(os.path.join(os.path.dirname(__file__), "wifi_mibs.json"))

    def __init__(self, device, board):
        self.device = device
        self.board = board
        self.iface_ip = board.get_iface_addr_with_retries(board.wan_iface)

    def enable_wifi(self, wifi_mode):
        index = mib_value["mib_index"][wifi_mode]
        mib_out=snmp_mib_set(self.device,self.board,self.iface_ip,mib_value["mib_name"]["Wifi_enable"],index,"i","1")
        if self.apply_changes_no_delay:
            self.apply_changes(wifi_mode)
            mib_out=snmp_mib_get(self.device,self.board,self.iface_ip,mib_value["mib_name"]["Wifi_enable"],index)
        assert mib_out=="1", "Mib query return value for enable wifi: %s" % mib_out

    def set_ssid(self, wifi_mode, ssid_name):
        index = mib_value["mib_index"][wifi_mode]
        mib_out=snmp_mib_set(self.device,self.board,self.iface_ip,mib_value["mib_name"]["SSID_set"],index,"s",ssid_name)
        if self.apply_changes_no_delay:
            self.apply_changes(wifi_mode)
            mib_out=snmp_mib_get(self.device,self.board,self.iface_ip,mib_value["mib_name"]["SSID_set"],index)
        assert mib_out==ssid_name, "Mib query return value for setting the SSID: %s" % mib_out

    def set_security(self, wifi_mode, security):
        index = mib_value["mib_index"][wifi_mode]
        security_mode = mib_value["security_mode"][security]
        mib_out=snmp_mib_set(self.device,self.board,self.iface_ip,mib_value["mib_name"]["Security_mode"],index,"i",security_mode)
        if self.apply_changes_no_delay:
            self.apply_changes(wifi_mode)
            mib_out=snmp_mib_get(self.device,self.board,self.iface_ip,mib_value["mib_name"]["Security_mode"],index)
        assert mib_out==security_mode, "Mib query return value for setting the security mode: %s" % mib_out

    def set_password(self, wifi_mode, password):
        index = mib_value["mib_index"][wifi_mode]
        mib_out=snmp_mib_set(self.device,self.board,self.iface_ip,mib_value["mib_name"]["Password_set"],index,"s",password)
        if self.apply_changes_no_delay:
            self.apply_changes(wifi_mode)
            mib_out=snmp_mib_get(self.device,self.board,self.iface_ip,mib_value["mib_name"]["Password_set"],index)
        assert mib_out==password, "Mib query return value for setting the password: %s" % mib_out

    def enable_channel_utilization(self):
        mib_out=snmp_mib_set(self.device,self.board,self.iface_ip,mib_value["mib_name"]["Channel_Util"],"0","i","2")
        if self.apply_changes_no_delay:
            self.apply_changes(wifi_mode)
            mib_out=snmp_mib_get(self.device,self.board,self.iface_ip,mib_value["mib_name"]["Channel_Util"],"0")
        assert mib_out=="2", "Mib query return value for setting the channel utilisation: %s" % mib_out

    def set_operating_mode(self, wifi_mode, operating_mode):
        index = mib_value["mib_index"][wifi_mode]
        operating_mode = mib_value["operating_mode"][operating_mode]
        mib_out=snmp_mib_set(self.device,self.board,self.iface_ip,mib_value["mib_name"]["Operating_mode"],index,"i",operating_mode)
        if self.apply_changes_no_delay:
            self.apply_changes(wifi_mode)
            mib_out=snmp_mib_get(self.device,self.board,self.iface_ip,mib_value["mib_name"]["Operating_mode"],index)
        assert mib_out==operating_mode, "Mib query return value for setting the operating mode: %s" % mib_out

    def set_bandwidth(self, wifi_mode, bandwidth, channel_number=0):
        index = mib_value["mib_index"][wifi_mode]
        bandwidth = mib_value["bandwidth"][bandwidth]
        mib_out=snmp_mib_set(self.device,self.board,self.iface_ip,mib_value["mib_name"]["Bandwidth"],index,"i",bandwidth)
        if self.apply_changes_no_delay:
            self.apply_changes(wifi_mode)
            mib_out=snmp_mib_get(self.device,self.board,self.iface_ip,mib_value["mib_name"]["Bandwidth"],index)
        assert mib_out==bandwidth, "Mib query return value for setting the bandwidth: %s" % mib_out

    def set_channel_number(self, wifi_mode, channel_number):
        index = mib_value["mib_index"][wifi_mode]
        mib_out=snmp_mib_set(self.device,self.board,self.iface_ip,mib_value["mib_name"]["Channel_mode"],index,"u",channel_number)
        if self.apply_changes_no_delay:
            self.apply_changes(wifi_mode)
            mib_out=snmp_mib_get(self.device,self.board,self.iface_ip,mib_value["mib_name"]["Channel_mode"],index)
        assert mib_out==channel_number, "Mib query return value for setting the channel number: %s" % mib_out

    def set_broadcast(self, wifi_mode, broadcast="enable"):
        if broadcast == "enable":
            broadcast_value = "2"
        elif broadcast == "disable":
            broadcast_value = "1"
        index = mib_value["mib_index"][wifi_mode]
        mib_out=snmp_mib_set(self.device,self.board,self.iface_ip,mib_value["mib_name"]["Broadcast"],index,"i",broadcast_value)
        if self.apply_changes_no_delay:
            self.apply_changes(wifi_mode)
            mib_out=snmp_mib_get(self.device,self.board,self.iface_ip,mib_value["mib_name"]["Broadcast"],index)
        assert mib_out==broadcast_value, "Mib query return value for setting the broadcast for SSID: %s" % mib_out

    def apply_changes(self, wifi_mode):
        """
        Name: apply_changes
        Purpose: Chekck DUT wireless is enable after wifiMgmtApplySettings setup
        Input: None
        Output: True or False
        """
        index = mib_value["mib_index"][wifi_mode]
        snmp_mib_set(self.device,self.board,self.iface_ip,mib_value["mib_name"]["Wifi_Apply_setting"],"0","i","1")
        for i in range(4):
            self.board.expect(pexpect.TIMEOUT, timeout=20)
            try:
                mib_out=snmp_mib_get(self.device,self.board,self.iface_ip,self.board.mib["wifiMgmtCurrentChannel"],index)
                if mib_out=='0':
                    return True
                    break
            except:
                pass
        return False

    def get_wifi_enabled(self, wifi_mode):
        index = mib_value["mib_index"][wifi_mode]
        mib_out = snmp_mib_get(self.device,self.board,self.iface_ip,mib_value["mib_name"]["Wifi_enable"],index)
        return mib_out

    def get_ssid(self, wifi_mode):
        index = mib_value["mib_index"][wifi_mode]
        mib_out = snmp_mib_get(self.device,self.board,self.iface_ip,mib_value["mib_name"]["SSID_set"],index)
        return mib_out

    def get_security(self, wifi_mode):
        index = mib_value["mib_index"][wifi_mode]
        mib_out = snmp_mib_get(self.device,self.board,self.iface_ip,mib_value["mib_name"]["Security_mode"],index)
        return mib_out

    def get_password(self, wifi_mode):
        index = mib_value["mib_index"][wifi_mode]
        mib_out = snmp_mib_get(self.device,self.board,self.iface_ip,mib_value["mib_name"]["Password_set"],index)
        return mib_out

    def get_channel_utilization(self):
        mib_out = snmp_mib_get(self.device,self.board,self.iface_ip,mib_value["mib_name"]["Channel_Util"],"0")
        return mib_out

    def get_operating_mode(self, wifi_mode):
        index = mib_value["mib_index"][wifi_mode]
        mib_out = snmp_mib_get(self.device,self.board,self.iface_ip,mib_value["mib_name"]["Operating_mode"],index)
        return mib_out

    def get_bandwidth(self, wifi_mode):
        index = mib_value["mib_index"][wifi_mode]
        mib_out = snmp_mib_get(self.device,self.board,self.iface_ip,mib_value["mib_name"]["Bandwidth"],index)
        return mib_out

    def get_broadcast(self, wifi_mode):
        index = mib_value["mib_index"][wifi_mode]
        mib_out = snmp_mib_get(self.device,self.board,self.iface_ip,mib_value["mib_name"]["Broadcast"],index)
        return mib_out

    def get_channel_number(self, wifi_mode):
        index = mib_value["mib_index"][wifi_mode]
        mib_out = snmp_mib_get(self.device,self.board,self.iface_ip,mib_value["mib_name"]["Current_channel"],index)
        return mib_out


