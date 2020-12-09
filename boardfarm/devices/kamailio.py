from boardfarm.dbclients.mysql import MySQL
from boardfarm.lib.installers import apt_install

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
        self.ast_local_url = kwargs.get("local_site", None)
        self.db = "kamailio"
        self.mysql = MySQL(self)
        sipcenter_profile = self.profile[self.name] = {}
        sipcenter_profile["on_boot"] = self._kamailio_boot

    def __str__(self):
        return "kamailio"

    def sipserver_install(self):
        """Install kamailio from internet."""
        self.mysql.install()
        apt_install(self, "kamailio", timeout=300)
        apt_install(self, "kamailio-mysql-modules", timeout=300)

    def sipserver_configuration(self):
        """Generate kamailio basic db and configuration file."""
        # basic configurations
        self.mysql.start()
        self.mysql.setup_root_user()
        gen_conf = """cat > /etc/kamailio/kamctlrc << EOF
SIP_DOMAIN=sipcenter.boardfarm.com
DBENGINE=MYSQL
EOF"""
        self.sendline(gen_conf)
        db_exists = self.mysql.check_db_exists(self.db)
        if not db_exists:
            self._create_kamailiodb()
            self.mysql.update_user_password(self.db)

        startup_conf = """ cat > /etc/default/kamailio << EOF
RUN_KAMAILIO=yes
EOF"""
        self.sendline(startup_conf)

    def sipserver_start(self):
        """Start the kamailio server if executable is present."""
        self.sendline("service kamailio start")
        self.expect("Starting")
        self.expect(self.prompt)

    def sipserver_kill(self):
        """Kill the kamailio server."""
        self.sendline("killall -9 kamailio")
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
        index = self.expect(["Listening on"] + self.prompt)
        if index == 0:
            return "Running"
        else:
            return "Stopped"

    def sipserver_user_add(self, user, password):
        """Add user and password to the sipserver.

        param user: the user entry to be added
        type user: list/string
        param password: the password of the user
        type password: string
        """
        if isinstance(user, str):
            user = list(user)
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

    def sipserver_user_registration_status(self, user):
        """Returns user registration status.

        param user: the user entry to be added
        type user: string
        param password: the password of the user
        type password: string
        """
        self.sendline("kamctl db smatch subscriber username %s" % user)
        self.expect(self.prompt)
        return self.before

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
        self.sipserver_install()
        self.configuration()
        self.start()
        self.user_add(self.users, self.password)
