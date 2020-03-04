from boardfarm.lib.installers import install_pjsua


class SoftPhone(object):

    model = "pjsip"
    profile = {}

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.own_number = self.kwargs.get('number', '3000')
        self.port = self.kwargs.get('num_port', '5060')
        self.config_name = "pjsip.conf"
        self.pjsip_local_url = kwargs.get("local_site", None)
        self.pjsip_prompt = ">>>"
        self.profile[self.name] = self.profile.get(self.name, {})
        softphone_profile = self.profile[self.name] = {}
        softphone_profile["on_boot"] = self.install_softphone

    def __str__(self):
        return "softphone"

    def install_softphone(self):
        # to install softphone from local url or from internet
        self.prefer_ipv4()
        install_pjsua(self, getattr(self, "pjsip_local_url", None))

    def phone_config(self, sipserver_ip):
        '''
        To configure the soft phone
        Arguments:
        sipserver_ip(str): ip of sip server
        '''
        conf = '''(
        echo --local-port=''' + self.port + '''
        echo --id=sip:''' + self.own_number + '''@''' + sipserver_ip + '''
        echo --registrar=sip:''' + sipserver_ip + '''
        echo --realm=*
        echo --username=''' + self.own_number + '''
        echo --password=1234
        echo --null-audio
        )> ''' + self.config_name
        self.sendline(conf)
        self.expect(self.prompt)

    def phone_start(self):
        '''To start the soft phone
        Note: Start softphone only when asterisk server is running to avoid failure'''
        self.sendline('pjsua --config-file=' + self.config_name)
        self.expect(r'registration success, status=200 \(OK\)')
        self.sendline('/n')
        self.expect(self.pjsip_prompt)

    def dial(self, dial_number, receiver_ip):
        '''
        To dial to the other phone
        Arguments:
        dial_number(str): number to dial
        receiver_ip(str): ip of the reciever,it is mta ip the call is dialed to mta
        '''
        self.sendline('/n')
        self.expect(self.pjsip_prompt)
        self.sendline('m')
        self.expect(r'Make call\:')
        self.sendline('sip:' + dial_number + '@' + receiver_ip)
        self.expect('Call 0 state changed to CALLING')
        self.expect(self.pjsip_prompt)

    def answer(self):
        '''To answer the incoming call in soft phone'''
        self.sendline('/n')
        self.expect(self.pjsip_prompt)
        self.expect('Press a to answer or h to reject call')
        self.sendline('a')
        self.expect(r'Answer with code \(100\-699\) \(empty to cancel\)\:')
        self.sendline('200')
        self.expect('Call 0 state changed to CONFIRMED')
        self.sendline('/n')
        self.expect(self.pjsip_prompt)

    def hangup(self):
        '''To hangup the ongoing call'''
        self.sendline('/n')
        self.expect(self.pjsip_prompt)
        self.sendline('a')
        self.expect('DISCON')
        self.expect(self.pjsip_prompt)

    def phone_kill(self):
        '''To kill the pjsip session'''
        self.sendcontrol('c')
        self.expect(self.prompt)
