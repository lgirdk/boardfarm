from boardfarm.lib.installers import apt_install
class SipCenter(object):
    '''
    asterisk  server
    '''

    model = ('asterisk')
    profile = {}

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

        self.numbers = self.kwargs.get('numbers', ["1000", "2000", "3000"])
        #local installation without internet will be added soon
        self.ast_local_url = kwargs.get("local_site", None)
        self.profile["on_boot"] = self.start_asterisk

    def __str__(self):
        return "asterisk"

    def install_essentials(self):
        '''
        install asterisk essentials
        '''
        apt_install(self, 'build-essential')
        apt_install(self, 'libncurses5-dev')
        apt_install(self, 'libjansson-dev')
        apt_install(self, 'uuid-dev')
        apt_install(self, 'libxml2-dev')
        apt_install(self, 'libsqlite3-dev')

    def install_asterisk(self):
        '''
        install asterisk from internet
        '''
        self.install_essentials()
        apt_install(self, 'asterisk', timeout= 300)

    def setup_asterisk_config(self):
        '''
        Generates sip.conf and extensions.conf file.

        '''
        gen_conf = '''cat > /etc/asterisk/sip.conf << EOF
[general]
context=default
bindport=5060
allowguest=yes
qualify=yes
registertimeout=900
allow=all
allow=alaw
allow=gsm
allow=g723
allow=g729
EOF'''
        gen_mod = '''cat > /etc/asterisk/extensions.conf << EOF
[default]
EOF'''
        self.sendline(gen_conf)
        self.expect(self.prompt)
        self.sendline(gen_mod)
        self.expect(self.prompt)
        for i in self.numbers:
            num_conf = '''(
echo [''' + i + ''']
echo type=friend
echo regexten=''' + i + '''
echo secret=1234
echo qualify=no
echo nat=force_rport
echo host=dynamic
echo canreinvite=no
echo context=default
echo dial=SIP/''' + i + '''
)>>  /etc/asterisk/sip.conf'''
            self.sendline(num_conf)
            self.expect(self.prompt)
            num_mod = '''(
echo exten \=\> ''' + i + ''',1,Dial\(SIP\/''' + i + ''',10,r\)
echo same \=\>n,Wait\(20\)
)>> /etc/asterisk/extensions.conf'''
            self.sendline(num_mod)
            self.expect(self.prompt)

    def start_asterisk(self):
        '''
        Start the asterisk server if executable is present
        '''
        self.install_asterisk()
        self.sendline('nohup asterisk -vvvvvvvd &> ./log.ast &')
        self.expect(self.prompt)

    def kill_asterisk(self):
        '''
        Kill  the asterisk server
        '''
        self.sendline('killall -9 asterisk')
        self.expect(self.prompt)
