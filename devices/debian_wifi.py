
import debian


class DebianWifi(debian.DebianBox):
    '''Extension of Debian class with wifi functions'''

    model = ('debianwifi')

    iface_wlan = "wlan1"

    def scan(self):
        from tests.lib.installers import install_iw
        install_iw(self)

        self.sendline('iw %s scan | grep SSID:' % self.iface_wlan)
        self.expect(self.prompt)

        return self.before
