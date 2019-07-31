import base


class BaseCmts(base.BaseDevice):
    '''
    Common API for the CMTS type devices
    '''
    model = "undefined"

    def connect(self):
        raise Exception("Not implemented!")

    def logout(self):
        raise Exception("Not implemented!")

    def check_online(self, cmmac):
        raise Exception("Not implemented!")

    def get_cmip(self, cmmac):
        raise Exception("Not implemented!")

    def get_cmipv6(self, cmmac):
        raise Exception("Not implemented!")

    def get_mtaip(self, cmmac, mtamac):
        raise Exception("Not implemented!")

    # this should be get_md_bundle
    def get_cm_bundle(self, mac_domain):
        raise Exception("Not implemented!")

    def get_cm_mac_domain(self, cm_mac):
        raise Exception("Not implemented!")

    def get_cmts_ip_bundle(self, bundle):
        raise Exception("Not implemented!")

    def get_cmts_model(self):
        return self.model

    def clear_offline(self, cmmac):
        raise Exception("Not implemented!")

    def clear_cm_reset(self, cmmac):
        raise Exception("Not implemented!")

    def get_cm_mac_cmts_format(self, mac):
        """
        Function:   get_cm_mac_cmts_format(mac)
        Parameters: mac        (mac address XX:XX:XX:XX:XX:XX)
        returns:    the cm_mac in cmts format xxxx.xxxx.xxxx (lowercase)
        """
        if mac == None:
            return None
        # the mac cmts syntax format example is 3843.7d80.0ac0
        tmp = mac.replace(':', '')
        mac_cmts_format = tmp[:4]+"."+tmp[4:8]+"."+tmp[8:]
        return mac_cmts_format.lower()
