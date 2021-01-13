"""Kamailio SIP server module

This module consists of SIPcenterKamailio class.
"""
from boardfarm.dbclients.mysql import MySQL
from boardfarm.lib.installers import apt_install
from boardfarm.lib.voice import (
    rtpproxy_configuration,
    rtpproxy_install,
    rtpproxy_start,
    rtpproxy_stop,
)

from .base_devices.sipcenter_interface import ISIPCenter
from .debian import DebianBox


class SIPcenterKamailio(DebianBox, ISIPCenter):
    """Kamailio server."""

    model = "kamailio"
    profile = {}

    def __init__(self, *args, **kwargs):
        """Instance initialization of kamailio class."""
        self.args = args
        self.kwargs = kwargs
        self.ast_prompt = ".*>"
        self.users = self.kwargs.get("users", ["1000", "2000", "3000"])
        self.password = "1234"
        self.db_name = "kamailio"
        self.kamailio_cfg = "/etc/kamailio/kamailio.cfg"
        self.mysql = MySQL(self)
        sipcenter_profile = self.profile[self.name] = {}
        sipcenter_profile["on_boot"] = self._kamailio_boot

    def __str__(self):
        return "kamailio"

    def sipserver_install(self):
        """Install kamailio from internet."""
        self.mysql.install()
        rtpproxy_install(self)
        apt_install(self, "kamailio", timeout=300)
        apt_install(self, "kamailio-mysql-modules", timeout=300)

    def sipserver_purge(self):
        """Uninstall and purge kamailio server."""
        self.sendline("rm " + self.kamailio_cfg)
        self.expect(self.prompt)
        self.sendline("apt-get purge kamailio -y")
        self.expect(self.prompt, timeout=80)

    def sipserver_configuration(self):
        """Generate kamailio basic db and configuration file."""
        # basic configurations
        self.mysql.start()
        self.mysql.setup_root_user()
        rtpproxy_configuration(self)
        rtpproxy_start(self)
        gen_db_conf = """cat > /etc/kamailio/kamctlrc << EOF
SIP_DOMAIN=sipcenter.boardfarm.com
DBENGINE=MYSQL
DBRWUSER="kamailio"
DBRWPW="test"
EOF"""
        self.sendline(gen_db_conf)
        self.expect(self.prompt)
        gen_sed = """sed -i '1d' """ + self.kamailio_cfg
        gen_kamailio_cfg = (
            """echo '#!KAMAILIO
#!define WITH_MYSQL
#!define WITH_AUTH
#!define WITH_NAT
#!define WITH_USRLOCDB
#!define DBURL "mysql://kamailio:test@localhost/kamailio"' | cat - """
            + self.kamailio_cfg
            + """ > temp && mv temp """
            + self.kamailio_cfg
        )
        self.sendline(gen_sed)
        self.expect(self.prompt)
        self.sendline(gen_kamailio_cfg)
        self.expect(self.prompt)
        db_exists = self.mysql.check_db_exists(self.db_name)
        if not db_exists:
            self._create_kamailiodb()
            self.mysql.update_user_password(self.db_name)

        startup_conf = """ cat > /etc/default/kamailio << EOF
RUN_KAMAILIO=yes
USER=kamailio
CFGFILE=/etc/kamailio/kamailio.cfg
EOF"""
        self.sendline(startup_conf)

    def sipserver_start(self):
        """Start the kamailio server if executable is present."""
        self.sendline("service kamailio start")
        self.expect("Starting")
        self.expect(self.prompt)

    def sipserver_kill(self):
        """Kill the kamailio server."""
        self.sendline("killall  kamailio")
        self.expect(self.prompt)

    def sipserver_stop(self):
        """Stop the kamailio server"""
        self.sendline("service kamailio stop")
        self.expect("Stopping")
        self.expect(self.prompt)

    def sipserver_restart(self):
        """Restart the kamailio server"""
        self.sendline("service kamailio restart")
        self.expect(self.prompt)

    def sipserver_status(self):
        """Check the kamailio status"""
        self.sendline("kamailio status")
        index = self.expect(["Listening on", "command not found"] + self.prompt)
        if index == 0:
            return "Running"
        elif index == 1:
            return "Not installed"
        return "Not Running"

    def sipserver_user_add(self, user, password):
        """Add user and password to the sipserver.

        param user: the user entry to be added
        type user: list/string
        param password: the password of the user
        type password: string
        """
        if isinstance(user, str):
            user = [user]
        for i in user:
            self.sendline("kamctl add %s %s" % (i, password))
            index = self.expect(["MySQL password for user"] + self.prompt)
            if index == 0:
                self.sendline(self.mysql.password)
                self.expect(self.prompt)

    def sipserver_user_remove(self, user):
        """Remove the the user added.

        param user: the user entry to be added
        type user: string
        """
        self.sendline("kamctl rm %s" % user)
        self.expect(self.prompt)

    def sipserver_user_update(self, user, password):
        """Update the user details.

        param user: the user entry to be added
        type user: string
        param password: the password of the user
        type password: string
        """
        self.sendline("kamctl passwd %s %s" % (user, password))
        self.expect(self.prompt)

    def sipserver_user_registration_status(self, user, ip_address):
        """Returns user registration status.

        param user: the user entry to be added
        type user: string
        param password: the password of the user
        type password: string
        """
        self.sendline("kamctl ul show %s" % user)
        self.expect(self.prompt)
        if "sip:%s@%s:5060" % (user, ip_address) in self.before:
            return "Registered"
        elif "404 AOR not found" in self.before:
            return "Unregistered"
        return self.before

    def sipserver_get_online_users(self):
        """Get sipserver online users"""
        self.sendline("kamctl online")
        self.expect(self.prompt)
        return self.before

    def _check_kamailio_db(self, user):
        """check if the subscriber entries are added"""
        self.sendline("kamctl db smatch subscriber username %s" % user)
        self.expect(self.prompt)
        out = self.before + self.after

        if "username: " + user in out:
            return True
        return False

    def _create_kamailiodb(self):
        """Create a kamailio db. """
        self.sendline("kamdbctl create")
        self.expect("MySQL password for root:")
        self.sendline(self.mysql.password)
        self.expect("Enter character set name:")
        self.sendline(self.mysql.default_charset)
        for _i in range(3):
            self.expect(r"\(y\/n\)\:", timeout=60)
            self.sendline("y")

    def _kamailio_boot(self):
        """ Method to accumulate all the boot functionalities."""
        try:
            self.sipserver_kill()
            self.sipserver_purge()
            rtpproxy_stop(self)
            self.sipserver_install()
            self.sipserver_configuration()
            self.sipserver_kill()
            self.sipserver_start()
            for i in self.users:
                if not self._check_kamailio_db(i):
                    self.sipserver_user_add(i, self.password)
        except Exception as error:
            raise error
