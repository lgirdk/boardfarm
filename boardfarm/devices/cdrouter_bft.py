class CDrouterDevice(object):
    model = ('cdrouter')

    def __init__(self, *args, **kwargs):
        self.ipaddr = kwargs.pop('ipaddr')
        self.wan_iface = kwargs.pop('wan_iface')
        self.lan_iface = kwargs.pop('lan_iface')
        self.wanispip = kwargs.pop('wanispip')
        self.wanispgateway = kwargs.pop('wanispgateway')
        self.ipv4hopcount = kwargs.pop('ipv4hopcount')
