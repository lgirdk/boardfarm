from functools import wraps

from boardfarm.devices import base


def deco_get_mac(function):
    """Fetch MAC address for board under use.

    Use this decorator on functions where MAC
    address of board under test is required as initial arg.

    Implemented considering MAC address of board does not need
    to be passed as an arg when know via JSON config.

    """

    @wraps(function)
    def wrapper(*args, **kwargs):
        args = list(args)
        if args[1] is None:
            args[1] = args[0].board_wan_mac
        return function(*args)

    return wrapper


class BaseCmts(base.BaseDevice):
    """Connects to and configures  CMTS common methods API

    BaseCmts device class can be used to derive any boardband router API.
    """

    model = "base_cmts"
    name = "cmts"
    board_wan_mac = None
    board_mta_mac = None

    def __init__(self, *args, **kwargs):
        self.board_wan_mac = kwargs.get("wan_mac", None)
        self.board_mta_mac = kwargs.get("mta_mac", None)

    def connect(self):
        """This method is used to connect CMTS, login to the CMTS based on the connection type available

        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def logout(self):
        """Logout of the CMTS device

        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def check_online(self, cmmac=None):
        """Check the board status from CMTS

        Function checks the encrytion mode and returns True if online

        :param cmmac: mac address of the board
        :type cmmac: string
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def is_online(self, cmmac=None, encrypted=True):
        """Check if board is online on CMTS.

        If the encrypted flag is True, verify that traffic between
        CMTS and CM is encrypted.

        :param cmmac: mac address of the board
        :type cmmac: string
        :param encrypted: BPI encryption flag
        :type encrypted: bool
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def get_cmip(self, cmmac):
        """Get the IP of the board from CMTS

        :param cmmac: mac address of the board
        :type cmmac: string
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def get_cmipv6(self, cmmac):
        """Get IPv6 address of the board from CMTS

        :param cmmac: mac address of the board
        :type cmmac: string
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def get_mtaip(self, cmmac, mtamac):
        """Get the MTA IP from CMTS

        :param cmmac: mac address of the board
        :type cmmac: string
        :param mtamac: mta mac address
        :type mtamac: string
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def get_cm_bundle(self, mac_domain):
        """Get IP-bundle interface configured for a board in particular mac domain.

        Depends on output ``cmts.get_cm_mac_domain(board_mac)

        :param mac_domain: Mac_domain of the board connected
        :type mac_domain: string
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def get_cm_mac_domain(self, cm_mac):
        """Get the Mac-domain ID of board

        :param cm_mac: mac address of the board
        :type cm_mac: string
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def get_cmts_ip_bundle(self, cm_mac, gw_ip=None):
        """Get subnet details of IP bundle of a MAC domain.

        Optional host ip of board can be provided to obtain host/secondary subnet details

        :param cm_mac: mac address of the board
        :type cm_mac: string
        :param gw_ip: gateway ip address
        :type gw_ip: string
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def get_cmts_model(self):
        """Get CMTS model

        :return: returns CMTS model
        :rtype: string
        :raises Exception: Not implemented
        """
        return self.model

    def clear_offline(self, cmmac):
        """Clear board entry from CMTS which is offline

        :param cmmac: mac address of the board
        :type cmmac: string
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def clear_cm_reset(self, cmmac):
        """Reset the board from CMTS using cli

        :param cmmac: mac address of the board
        :type cmmac: string
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def save_running_to_startup_config(self):
        """save the running config to startup

        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def save_running_config_to_local(self, filename):
        """Copy running config to local machine

        :param filename: filename to save the config
        :type filename: string
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def get_qam_module(self):
        """Get the module of the qam

        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def get_ups_module(self):
        """Get the upstream module of the qam

        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def set_iface_ipaddr(self, iface, ipaddr):
        """This function is used to set an IPv4 address on a CMTS interface

        :param iface: interface name ,
        :type iface: string
        :param ipaddr: <ip></><subnet> using 24 as default if subnet is not provided.
        :type ipaddr: string
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def set_iface_ipv6addr(self, iface, ipaddr):
        """This function is used to set an IPv6 address on a CMTS interface

        :param iface: interface name
        :type iface: string
        :param ipaddr: ipaddress to configure
        :type ipaddr: string
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def unset_iface_ipaddr(self, iface):
        """This function is to unset an IPv4 address of an interface on CMTS

        :param iface: interface name
        :type iface: string
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def unset_iface_ipv6addr(self, iface):
        """This function is to unset an IPv6 address of an interface on CMTS

        :param iface: interface name.
        :type iface: string
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def del_file(self, f):
        """delete file on CMTS

        :param f: filename to delete from CMTS
        :type f: string
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def check_docsis_mac_ip_provisioning_mode(self, index):
        """Get the provisioning mode of the board from CMTS

        :param index: mac domain of the board
        :type index: string
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def wait_for_ready(self):
        """Check the CMTS status

        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def modify_docsis_mac_ip_provisioning_mode(self, index, ip_pvmode="dual-stack"):
        """Change the ip provsioning mode

        :param index: mac domain of the board configured
        :type index: string
        :param ip_pvmode: provisioning mode can ipv4, ipv6 or 'dual-stack', defaults to 'dual-stack'
        :type ip_pvmode: string
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def get_ertr_ipv4(self, mac, offset=2):
        """Getting erouter ipv4 from CMTS

        :param mac: mac address of the board
        :type mac: string
        :param offset: ignored based on model
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def get_ertr_ipv6(self, mac, offset=2):
        """Getting erouter ipv6 from CMTS

        :param mac: mac address of the board
        :type mac: string
        :param offset: ignored based on model
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def get_center_freq(self, mac_domain=None):
        """This function is to return the center frequency of CMTS

        :param mac_domain: Mac Domain of the board defaults to None
        :type mac_domain: string
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def check_PartialService(self, cmmac):
        """Check the board is in partial service

        :param cmmac: mac address of the board
        :type cmmac: string
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def DUT_chnl_lock(self, cm_mac):
        """Check the board channel locks based on CMTS type

        :param cm_mac: mac address of the board
        :type cm_mac: string
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def add_route(self, ipaddr, gw):
        """This function is to add route

        :param ipaddr: <network ip></><subnet ip> take subnet 24 if not provided,
        :param ipaddr: string
        :param gw: gateway ip.
        :type gw: string
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def add_route6(self, net, gw):
        """This function is to add route6

        :param net: <network ip></><subnet ip> take subnet 24 if not provided,
        :param net: string
        :param gw: gateway ip.
        :type gw: string
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def del_route(self, ipaddr, gw):
        """This function is to delete route

        :param ipaddr: <network ip></><subnet ip> take subnet 24 if not provided
        :type ipaddr: string
        :param gw: gateway ip
        :type gw: string
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def del_route6(self, net, gw):
        """This function is to delete ipv6 route

        :param net: <network ip></><subnet ip> take subnet 24 if not provided,
        :type net: string
        :param gw: gateway ip
        :type gw: string
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def add_ip_bundle(self, index, helper_ip, ipaddr, secondary_ips=[]):
        """This function is to add ip bundle to a cable mac

        :param index: cable mac index,
        :type index: string
        :param helper_ip: helper ip to be used,
        :type helper_ip: string
        :param ipaddr: actual ip to be assiged to cable mac in the format  <ip></><subnet> subnet defaut taken as 24 if not provided,
        :type ipaddr: string
        :param secondary_ips: list of seconday ips  in the format  <ip></><subnet> subnet defaut taken as 24 if not provided, defaults to empty list []
        :type secondary_ips: list
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def add_ipv6_bundle_addrs(self, index, helper_ip, ip, secondary_ips=[]):
        """This function is to add ipv6 bundle to a cable mac

        :param index: cable mac index
        :type index: string
        :param helper_ip: helper ip to be used
        :type helper_ip: string
        :param ip: actual ip to be assiged to cable mac in the format  <ip></><subnet> subnet defaut taken as 24 if not provided
        :type ip: string
        :param secondary_ips: list of seconday ips  in the format  <ip></><subnet> subnet defaut taken as 24 if not provided defaults to empty list []
        :type secondary_ips: list
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def set_iface_qam(self, index, sub, annex, interleave, power):
        """Configure the qam interface with annex, interleave and power

        :param index: index number of the qam
        :type index: string
        :param sub: qam slot number
        :type sub: string
        :param annex: annex a or b or c to configure
        :type annex: string
        :param interleave: interleave depth to configure
        :type interleave: string
        :param power: power level
        :type power: string
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def set_iface_qam_freq(self, index, sub, channel, freq):
        """Configure the qam interface with channel and frequency

        :param index: index number of the qam
        :type index: string
        :param sub: qam slot number
        :type sub: string
        :param channel: channel number
        :type channel: string
        :param freq: frequency for the channel
        :type freq: string
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def get_iface_qam_freq(self, cm_mac):
        """Get the qam interface with channel and frequency

        :param cm_mac: mac address of the board
        :type cm_mac: string
        :return: Downstream index, sub, channel and frequency values.
        ex.OrderedDict([('8/4/0', '512000000'), ('8/4/1', '520000000'), ('8/4/2', '528000000'), ('8/4/3', '536000000'),
                        ('8/4/4', '544000000'), ('8/4/5', '552000000'), ('8/4/6', '560000000'), ('8/4/7', '568000000'),
                        ('8/5/0', '576000000'), ('8/5/1', '584000000'), ('8/5/2', '592000000'), ('8/5/3', '600000000'),
                        ('8/5/4', '608000000'), ('8/5/5', '616000000'), ('8/5/6', '624000000'), ('8/5/7', '632000000'),
                        ('8/6/0', '640000000'), ('8/6/1', '648000000'), ('8/6/2', '656000000'), ('8/6/3', '664000000'),
                        ('8/6/4', '672000000'), ('8/6/5', '680000000'), ('8/6/6', '688000000'), ('8/6/7', '696000000')])
        :rtype: dict
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def set_iface_upstream(self, ups_idx, ups_ch, freq, width, power):
        """Configure the interface for upstream

        :param ups_idx: upstream index number of the interface
        :type ups_idx: string
        :param ups_ch: upstream channel number for the interface
        :type ups_ch: string
        :param freq: frequency to configure the upstream
        :type freq: string
        :param width: width of the qam
        :type width: string
        :param power: power of the qam
        :type power: string
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def reset(self):
        """Delete the startup config and Reboot the CMTS

        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def is_cm_bridged(self, mac, offset=2):
        """This function is to check if the modem is in bridge mode

        :param mac: Mac address of the modem,
        :param offset: ignored based on model
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def get_ip_from_regexp(self, cmmac, ip_regexpr):
        """Gets an ip address according to a regexpr (helper function)

        :param cmmac: board mac address
        :type cmmac: string
        :param ip_regexpr: regular expression for ip
        :type ip_regexpr: string
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def add_service_class(
        self, index, name, max_rate, max_burst, max_tr_burst=None, downstream=False
    ):
        """Add a service class

        :param index: service class number
        :type index: string
        :param name: service name
        :type name: string
        :param max_rate: maximum traffic rate
        :type max_rate: string
        :param max_burst: maximum traffic burst
        :type max_burst: string
        :param max_tr_burst: If anything, defaults to None
        :type max_tr_burst: optional
        :param downstream: True or False, defaults to False
        :type downstream: boolean
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def add_iface_docsis_mac(
        self,
        index,
        ip_bundle,
        qam_idx,
        qam_ch,
        ups_idx,
        ups_ch,
        qam_sub=None,
        prov_mode=None,
    ):
        """configure docsis-mac domain

        :param index: docsis mac index
        :type index: string
        :param ip_bundle: bundle id of the board
        :type ip_bundle: string
        :param qam_idx: slot number of the qam to configure
        :type qam_idx: string
        :param qam_ch: qam channel number
        :type qam_ch: string
        :param ups_idx: upstream slot number
        :type ups_idx: string
        :param ups_ch: upstream channel number
        :type ups_ch: string
        :param qam_sub: port number of the qam, defaults to None
        :type qam_sub: string , optional
        :param prov_mode: provisioning mode if any, defaults to None
        :type prov_mode: string, optional
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def get_cmts_type(self):
        """This function is to get the product type on CMTS

        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def add_service_group(
        self, index, qam_idx, qam_sub, qam_channels, ups_idx, ups_channels
    ):
        """Add a service group

        :param index: service group number
        :type index: string
        :param qam_idx: slot number of the qam
        :type qam_idx: string
        :param qam_sub: port number of the qam
        :type qam_sub: string
        :param qam_channels: channel number of the qam
        :type qam_channels: string
        :param ups_idx: upstream slot number
        :type ups_idx: string
        :param ups_channels: channel number of the upstream
        :type ups_channels: string
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def mirror_traffic(self, macaddr=""):
        """Send the mirror traffic

        :param macaddr: mac address of the device if avaliable, defaults to empty string ""
        :type macaddr: string
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def unmirror_traffic(self):
        """stop mirroring the traffic

        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def run_tcpdump(self, time, iface="any", opts=""):
        """tcpdump capture on the cmts interface

        :param time: timeout to wait till gets prompt
        :type time: integer
        :param iface: any specific interface, defaults to 'any'
        :type iface: string, optional
        :param opts: any other options to filter, defaults to ""
        :type opts: string
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def get_qos_parameter(self, cm_mac):
        """To get the qos related parameters of board, to get the qos related parameters ["Maximum Concatenated Burst", "Maximum Burst", "Maximum Sustained rate", "Mimimum Reserved rate", "Scheduling Type"] of board

        :param cm_mac: mac address of the board
        :type cm_mac: string
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def get_cm_mac_cmts_format(self, mac):
        """to convert mac adress to the format that to be used on CMTS

        :param mac: mac address of board in foramt XX:XX:XX:XX:XX:XX
        :type mac: string
        :return:  the cm_mac in CMTS format xxxx.xxxx.xxxx (lowercase)
        :rtype: string
        """
        if mac == None:
            return None
        # the mac CMTS syntax format example is 3843.7d80.0ac0
        tmp = mac.replace(":", "")
        mac_cmts_format = tmp[:4] + "." + tmp[4:8] + "." + tmp[8:]
        return mac_cmts_format.lower()

    def get_downstream_qam(self, cm_mac):
        """This function is to get downstream modulation type(64qam, 256qam...)

        :param cm_mac: mac address of the board
        :type cm_mac: string
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def set_downstream_qam(self, get_downstream_qam):
        """This function is to set downstream modulation type(64qam, 256qam...)

        :param get_downstream_qam: ex.{'8/6': '256qam', '8/4': '256qam', '8/5': '256qam'}
        :type get_downstream_qam: dict
        :raises Exception: Not implemented
        """
        raise Exception("Not implemented!")

    def ping(self, ping_ip, ping_count=3, timeout=10):
        """This function to ping the device from CMTS
        :param ping_ip: device ip which needs to be verified
        :ping_ip type: string
        :param ping_count: Repeating ping packets, defaults to 3
        :ping_count type: integer
        :param timeout: timeout for the packets, defaults to 10 sec
        :type timeout: integer
        :return: True if ping passed else False
        """
        raise Exception("Not implemented!")
