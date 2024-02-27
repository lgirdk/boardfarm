"""Kamailio SIP server module

This module consists of SIPcenterKamailio class.
"""

import pathlib
import re
from typing import List, Union

from boardfarm.dbclients.mysql import MySQL
from boardfarm.devices.base_devices import fxo_template
from boardfarm.devices.base_devices.sip_template import SIPPhoneTemplate, SIPTemplate
from boardfarm.devices.debian import DebianBox
from boardfarm.lib.installers import apt_install
from boardfarm.lib.voice import (
    rtpproxy_configuration,
    rtpproxy_install,
    rtpproxy_start,
    rtpproxy_stop,
)


class SIPcenterKamailio(DebianBox, SIPTemplate):
    """Kamailio server."""

    model = "kamailio"
    profile = {}

    def __init__(self, *args, **kwargs) -> None:
        """Instance initialization of kamailio class."""
        self.args = args
        self.kwargs = kwargs
        self.ast_prompt = ".*>"
        self.users = self.kwargs.get("users", ["1000", "2000", "3000", "4000"])
        self.user_password = "1234"
        self.db_name = "kamailio"
        self.kamailio_cfg = "/etc/kamailio/kamailio.cfg"
        self.mysql = MySQL(self)
        sipcenter_profile = self.profile[self.name] = {}
        sipcenter_profile["on_boot"] = self._kamailio_boot
        self.url = self.dns.url

    def __str__(self):
        return "kamailio"

    def sipserver_install(self) -> None:
        """Install kamailio from internet."""
        self.mysql.install()
        rtpproxy_install(self)
        apt_install(self, "kamailio", timeout=300)
        apt_install(self, "kamailio-mysql-modules", timeout=300)

    def sipserver_purge(self) -> None:
        """Uninstall and purge kamailio server."""
        self.sendline("rm " + self.kamailio_cfg)
        self.expect(self.prompt)
        self.sendline("apt-get purge kamailio -y")
        self.expect(self.prompt, timeout=80)

    def sipserver_configuration(self) -> None:
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

    def sipserver_start(self) -> None:
        """Start the kamailio server if executable is present."""
        self.sendline("service kamailio start")
        self.expect("Starting")
        self.expect(self.prompt)

    def sipserver_kill(self) -> None:
        """Kill the kamailio server."""
        self.sendline("killall  kamailio")
        self.expect(self.prompt)

    def sipserver_stop(self) -> None:
        """Stop the kamailio server"""
        self.sendline("service kamailio stop")
        self.expect("Stopping")
        self.expect(self.prompt)

    def sipserver_restart(self) -> None:
        """Restart the kamailio server"""
        self.sendline("service kamailio restart")
        self.expect(self.prompt)

    def sipserver_status(self) -> str:
        """Check the kamailio status"""
        self.sendline("kamailio status")
        index = self.expect(["Listening on", "command not found"] + self.prompt)
        if index == 0:
            self.expect(self.prompt)
            return "Running"
        elif index == 1:
            self.expect(self.prompt)
            return "Not installed"
        return "Not Running"

    def add_endpoint_to_sipserver(self, endpoint: str, password: str) -> None:
        """Add endpoint to the directory.

        param endpoint: the endpoint entry to be added
        type endpoint: string
        param password: the password of the endpoint
        type password: string"""
        password = self.user_password if not password else password
        if isinstance(endpoint, str):
            endpoint = [endpoint]
        for i in endpoint:
            self.sendline(f"kamctl add {i} {password}")
            index = self.expect(["MySQL password for user"] + self.prompt)
            if index == 0:
                self.sendline(self.mysql.password)
                self.expect(self.prompt)

    def remove_endpoint_from_sipserver(self, endpoint: str) -> None:
        """Remove endpoint from the directory.

        param endpoint: the endpoint entry to be added
        type endpoint: string"""
        self.sendline(f"kamctl rm {endpoint}")
        self.expect(self.prompt)

    def update_endpoint_in_sipserver(self, endpoint: str, password: str) -> None:
        """Update the endpoint password to the directory.

        param endpoint: the endpoint entry to be added
        type endpoint: string
        param password: the password of the endpoint
        type password: string"""
        self.sendline(f"kamctl passwd {endpoint} {password}")
        self.expect(self.prompt)

    def configure_tls_to_endpoint_in_sipserver(
        self,
        phone_list: List[Union[fxo_template.FXOTemplate, SIPPhoneTemplate]],
    ) -> None:
        """Add user to the directory.

        param endpoint: the endpoint entry to be added
        type endpoint: string"""
        raise NotImplementedError

    def endpoint_registration_status_in_sipserver(
        self, endpoint: str, ip_address: str
    ) -> str:
        """Return the registration status.

        param endpoint: the endpoint entry to be added
        type endpoint: string
        param ip_address: the ip address of the endpoint
        type ip_address: string"""
        self.sendline(f"kamctl ul show {endpoint}")
        self.expect(self.prompt)
        if f"sip:{endpoint}@{ip_address}" in self.before:
            return "Registered"
        elif "404 AOR not found" in self.before:
            return "Unregistered"
        return self.before

    def sipserver_get_online_users(self) -> str:
        """Get sipserver online users"""
        self.sendline("kamctl online")
        self.expect(self.prompt)
        return self.before

    def sipserver_set_expire_timer(self, from_timer=180, to_timer=60):
        """Modify the call expires timer in kamailio.cfg

        :param from_timer: Expire timer value change from
        :type from_timer: int 'default to 180'
        :param to_timer: Expire timer value change to
        :type to_timer: int 'default to 60'
        """
        self.sendline(
            f"""sed -i -e 's|"max_expires", {from_timer}|"max_expires", {to_timer}|' """
            + self.kamailio_cfg
        )
        self.expect(self.prompt)
        self.sipserver_restart()

    def _check_kamailio_db(self, user):
        """check if the subscriber entries are added"""
        self.sendline(f"kamctl db smatch subscriber username {user}")
        self.expect(self.prompt)
        out = self.before + self.after

        if "username: " + user in out:
            return True
        return False

    def _create_kamailiodb(self):
        """Create a kamailio db."""
        self.sendline("kamdbctl create")
        self.expect("MySQL password for root:")
        self.sendline(self.mysql.password)
        self.expect("Enter character set name:")
        self.sendline(self.mysql.default_charset)
        for _i in range(3):
            self.expect(r"\(y\/n\)\:", timeout=60)
            self.sendline("y")

    def _does_kamailio_exist(self) -> bool:
        self.sendline("kamailio -v")
        res = self.expect(
            [
                "kamailio: (command not found|No such file or directory)",
                "version: kamailio",
            ]
        )
        self.expect(self.prompt)
        return res != 0

    def _kamailio_boot(self):
        """Method to accumulate all the boot functionalities."""
        try:
            if not self._does_kamailio_exist():
                self.sipserver_install()
            rtpproxy_stop(self)
            self.sipserver_configuration()
            self.generate_kamailio_cfg()
            self.sipserver_kill()
            self.sipserver_start()
            for i in self.users:
                if not self._check_kamailio_db(i):
                    self.sipserver_user_add(i, self.user_password)
        except Exception as error:
            raise error

    def generate_kamailio_cfg(self, update_cfg_dict=None):
        if update_cfg_dict is None:
            update_cfg_dict = {}
        self.txt = []
        dir = pathlib.Path(__file__).parent
        with open(dir.joinpath("../resources/configs/kamailio.cfg")) as cf:
            config = cf.read()
        kamailio_conf_dict = {
            "startup": None,
            "local_config": None,
            "defined_values": None,
            "global_parameters": None,
            "custom_parameters": None,
            "module_section": None,
            "routing logic": None,
        }
        for k, v in zip(
            kamailio_conf_dict.keys(), re.split(r"#######.*#######", config)
        ):
            kamailio_conf_dict[k] = v
        if update_cfg_dict:
            kamailio_conf_dict.update(update_cfg_dict)
        for k, v in kamailio_conf_dict.items():
            self.txt.append(f"####### {k} #######")
            for lines in v.splitlines():
                self.txt.append(lines)
        self.txt.append("EOF")
        self.sendline(f"cat > {self.kamailio_cfg} << EOF")
        for data in self.txt:
            self.sendline(data)
        self.expect(self.prompt, timeout=50)

    def get_sipserver_expire_timer(self) -> int:
        """Get the call expire timer in kamailio.cfg.

        :return: expiry timer saved in the config or None if it is not found
        :rtype: int
        """
        self.sendline("grep --colour=never 'max_expires' " + self.kamailio_cfg)
        self.expect(self.prompt)
        return int(self.before.split(sep=",")[-1].replace(")", "").strip())
