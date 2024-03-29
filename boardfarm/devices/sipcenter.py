import logging
import re

from debtcollector import deprecate

from boardfarm.exceptions import PexpectErrorTimeout
from boardfarm.lib.installers import apt_install

logger = logging.getLogger("bft")


class SipCenter:
    """Asterisk  server."""

    model = "asterisk"
    profile = {}

    def __init__(self, *args, **kwargs):
        """Instance initialization."""
        self.args = args
        self.kwargs = kwargs
        self.ast_prompt = ".*>"
        self.numbers = self.kwargs.get("numbers", ["1000", "2000", "3000"])
        # local installation without internet will be added soon
        self.ast_local_url = kwargs.get("local_site", None)
        self.profile[self.name] = self.profile.get(self.name, {})
        sipcenter_profile = self.profile[self.name] = {}
        sipcenter_profile["on_boot"] = self.start_asterisk

    def __str__(self):
        return "asterisk"

    def install_essentials(self):
        """Install asterisk essentials."""
        apt_install(self, "build-essential")
        apt_install(self, "libncurses5-dev")
        apt_install(self, "libjansson-dev")
        apt_install(self, "uuid-dev")
        apt_install(self, "libxml2-dev")
        apt_install(self, "libsqlite3-dev")
        apt_install(self, "tshark")

    def install_asterisk(self):
        """Install asterisk from internet."""
        deprecate(
            "Warning!",
            message="install_asterisk() is deprecated",
            category=UserWarning,
        )
        self.install_essentials()
        apt_install(self, "asterisk", timeout=300)

    def setup_asterisk_config(self):
        """Generate sip.conf and extensions.conf file."""
        deprecate(
            "Warning!",
            message="setup_asterisk_config() is deprecated",
            category=UserWarning,
        )
        gen_conf = """cat > /etc/asterisk/sip.conf << EOF
[general]
context=default
bindport=5060
allowguest=yes
qualify=yes
registertimeout=900
allow=all
EOF"""
        gen_mod = """cat > /etc/asterisk/extensions.conf << EOF
[default]
EOF"""
        self.sendline(gen_conf)
        self.expect(self.prompt)
        self.sendline(gen_mod)
        self.expect(self.prompt)
        for i in self.numbers:
            num_conf = (
                """cat >> /etc/asterisk/sip.conf << EOF
["""
                + i
                + """]
type=friend
regexten="""
                + i
                + """
secret=1234
qualify=no
nat=force_rport
host=dynamic
canreinvite=no
context=default
dial=SIP/"""
                + i
                + """
EOF"""
            )
            self.sendline(num_conf)
            self.expect(self.prompt)
            num_mod = (
                """cat >> /etc/asterisk/extensions.conf << EOF
exten => """
                + i
                + """,1,Dial(SIP/"""
                + i
                + """,180,r)
EOF"""
            )
            self.sendline(num_mod)
            self.expect(self.prompt)

    def start_asterisk(self):
        """Start the asterisk server if executable is present."""
        deprecate(
            "Warning!",
            message="start_asterisk() is deprecated",
            category=UserWarning,
        )
        self.install_asterisk()
        self.setup_asterisk_config()
        self.sendline("nohup asterisk -vvvvvvvd &> ./log.ast &")
        self.expect(self.prompt)

    def kill_asterisk(self):
        """Kill  the asterisk server."""
        deprecate(
            "Warning!",
            message="kill_asterisk() is deprecated",
            category=UserWarning,
        )
        self.sendline("killall -9 asterisk")
        self.expect(self.prompt)

    def stop(self):
        """This function kills all the asterisk instances.

        The description of the function is subjected to change during Sipcenter Interface addition.
        """
        deprecate(
            "Warning!",
            message="stop() is deprecated",
            category=UserWarning,
        )
        self.kill_asterisk()

    def enter_asterisk_console(self):
        """Enter the asterisk console."""
        self.sendline("asterisk -rv")
        self.expect(self.ast_prompt)

    def exit_asterisk_console(self):
        """Exit the asterisk console."""
        self.sendline("exit")
        self.expect(self.prompt)

    def sip_reload(self):
        """Reload the SIP server from asterisk.
        :return: Status of reload output in boolean
        :rtype: Boolean
        """
        try:
            self.enter_asterisk_console()
            self.sendline("sip reload")
            self.expect("Reloading SIP")
            self.expect(self.ast_prompt)
            return True
        except PexpectErrorTimeout:
            return False
        finally:
            self.exit_asterisk_console()

    def sipserver_user_registration_status(self, user, mta_ip):
        """To check the status of a user in sip server.
        which can be either 'Registered' or 'Unregistered'
        or 'Not Present'
        :param user: the username of the user
        :type user: string
        :param mta_ip: IPv4 address of the MTA
        :type mta_ip: string
        :return: Registration Status for the user and will
        be in 'Registered'/'Unregistered'/'User Unavailable'
        :rtype: string
        """
        self.enter_asterisk_console()
        self.sendline("sip show peers")
        self.expect(r"]")
        output = self.before
        self.exit_asterisk_console()
        if re.search(".*" + user + ".+" + mta_ip, output):
            logger.debug(f"User {user} is registered")
            return "Registered"
        elif re.search(".*" + user + r".+\(Unspecified\)", output):
            logger.debug(f"User {user} is unregistered")
            return "Unregistered"
        else:
            logger.debug(f"User {user} unavailable")
            return "User Unavailable"

    def modify_sip_config(self, oper="", user=""):
        """
        Add or Delete users in sip.conf.
        :param oper: add or delete operation
        :type  oper: string
        :param user: enter the user number to add/delete
        :type user: string
        :return: output: return a tuple with bool and defined message
        :rtype output: tuple
        """
        deprecate(
            "Warning!",
            message="modify_sip_config() is deprecated",
            category=UserWarning,
        )
        apt_install(self, "python3")
        py_steps = [
            "import configparser",
            "def modify():",
            "   config = configparser.ConfigParser(strict=False)",
            '   config.read("/etc/asterisk/sip.conf")',
            '   sip_conf = {"type": "friend", "regexten": "'
            + user
            + '", "secret": "1234", "qualify": "no", "nat": '
            '"force_rport", "host": "dynamic", "canreinvite": '
            '"no", "context": "default", "dial": "SIP/' + user + '"}',
            '   if "' + oper + '" == "add":',
            '       config.add_section("' + user + '")',
            "       for keys, values in sip_conf.items():",
            '           out = config.set("' + user + '", keys, values)',
            '   elif "' + oper + '" == "delete":',
            '       out = config.remove_section("' + user + '")',
            '   with open("/etc/asterisk/sip.conf", "w") as configfile:',
            "       config.write(configfile)",
            "   return out",
            "print(modify())",
        ]

        self.sendline("cat > sip_config.py << EOF\n%s\nEOF" % "\n".join(py_steps))
        self.expect("EOF")
        self.expect_prompt()
        self.sendline("python3 sip_config.py")
        self.expect_prompt(timeout=10)
        if "Traceback" in self.before:
            output = False, f"File error :\n{self.before}"
        elif "True" in self.before or "None" in self.before:
            output = True, "Operation " + oper + " is successful"
        else:
            output = False, "Operation " + oper + " is failed"
        self.sendline("cat /etc/asterisk/sip.conf")
        self.expect_prompt()
        self.sendline("rm sip_config.py")
        self.expect_prompt()
        return output

    def update_dial_timeout(self, user, dial_timeout=180):
        """Update the dial timeout parameter in extensions.conf
        :param user: user for which the dial_timeout needs to be updated
        :type  oper: int/string
        :param user: The dial timeout that needs to be set
        :type user: int/string
        :return: True on successful update
        :rtpe: Boolean
        """
        user = str(user)
        dial_timeout = str(dial_timeout)
        file = "/etc/asterisk/extensions.conf"
        self.sendline(
            r'sed -i "s/'
            + user
            + ".*"
            + user
            + ",[0-9]*,/"
            + user
            + r",1,Dial(SIP\/"
            + user
            + ","
            + dial_timeout
            + ',/" '
            + file
        )
        self.expect(self.prompt)
        self.sendline(r'sed -n "s/[^/]*\/' + user + r',\([0-9]*\).*/\\1/p" ' + file)
        self.expect(dial_timeout)
        self.expect(self.prompt)
        return True

    def core_restart(self):
        """Restart the asterisk service.
        :return: Status of reload output in boolean
        :rtype: Boolean
        """
        try:
            self.enter_asterisk_console()
            self.sendline("core restart now")
            self.expect("Asterisk cleanly ending")
            self.expect(self.prompt)
            return True
        except PexpectErrorTimeout:
            return False
