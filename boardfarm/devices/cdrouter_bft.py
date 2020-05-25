class CDrouterDevice(object):
    """CDRouter is an industry standard server.
    Used for feature, security, and performance testing of
    broadband and enterprise edge gateways, Wi-Fi APs and mesh systems, VoIP gateways, set-top-boxes,
    and smart hubs enabling the Internet of Things.

    Since CD-Router has its own test-suite, this device class is used to execute test cases on
    the server based on test and board detail provided by boardfarm.
    """

    model = "cdrouter"
    name = "cdrouter"

    def __init__(self, *args, **kwargs):
        """Instance initalization.
        This method is to initialize the variables required from board-farm perspective
        to execute the tests and fetch results from CD-router.

        These variables include ipaddress, wan_iface, lan_iface etc.,

        :param ``*args``: set of arguements to be passed if any.
        :type ``*args``: tuple
        :param ``**kwargs``: extra args to be used if any.
        :type ``**kwargs``: dict
        """
        self.ipaddr = kwargs.pop("ipaddr")
        self.wan_iface = kwargs.pop("wan_iface")
        self.lan_iface = kwargs.pop("lan_iface")
        self.wanispip = kwargs.pop("wanispip")
        self.wanispip_v6 = kwargs.pop("wanispip_v6")
        self.wanispgateway = kwargs.pop("wanispgateway")
        self.wanispgateway_v6 = kwargs.pop("wanispgateway_v6")
        self.ipv4hopcount = kwargs.pop("ipv4hopcount")

    def close(self):
        """Close method is supposed to close the connection to the device.
        (To be Enhanced).
        """
        pass
