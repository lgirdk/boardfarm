class CDrouterDevice(object):
    model = ('cdrouter')

    def __init__(self, *args, **kwargs):
        self.ipaddr = kwargs.pop('ipaddr')
        self.wan_iface = kwargs.pop('wan_iface')
        self.lan_iface = kwargs.pop('lan_iface')
        self.wanispip = kwargs.pop('wanispip')
        self.wanispip_v6 = kwargs.pop('wanispip_v6')
        self.wanispgateway = kwargs.pop('wanispgateway')
        self.wanispgateway_v6 = kwargs.pop('wanispgateway_v6')
        self.ipv4hopcount = kwargs.pop('ipv4hopcount')
