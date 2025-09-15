"""Device class for Kamailio version 5."""

from __future__ import annotations

import logging
import re
from typing import Any

from boardfarm3 import hookimpl
from boardfarm3.devices.base_devices import LinuxDevice
from boardfarm3.exceptions import VoiceError
from boardfarm3.lib.utils import get_static_ipaddress
from boardfarm3.templates.sip_server import SIPServer as SIPServerTemplate
from boardfarm3.templates.sip_server import VscScopeType

_LOGGER = logging.getLogger(__name__)

# pylint: disable=R0801
# pylint: disable=too-many-public-methods,too-many-instance-attributes
# R0801 tracks duplication in code that raises NotImplemented Error
# Work in progress - implementation will be done at a later point in time


class SIPcenterKamailio5(LinuxDevice, SIPServerTemplate):
    """Kamailio version 5 server."""

    def __init__(
        self,
        config: dict[str, Any],
        cmdline_args: Namespace,
    ) -> None:
        """Instance initialization of kamailio class.

        :param config: configuration dictionary
        :type config: dict[str, Any]
        :param cmdline_args: command line args
        :type cmdline_args: Namespace
        :raises VoiceError: if numbers not present in config
        """
        super().__init__(config=config, cmdline_args=cmdline_args)
        self._vsc_dict = {
            "set_cf_busy": "CFB_SET",
            "unset_cf_busy": "CFB_UNSET",
            "set_cf_no_answer": "CFNA_SET",
            "unset_cf_no_answer": "CFNA_UNSET",
            "set_cf_unconditional": "CFU_SET",
            "unset_cf_unconditional": "CFU_UNSET",
        }
        try:
            self._users = self._config.get("numbers")
        except KeyError as exc:
            msg = "Numbers not present in the config."
            raise VoiceError(msg) from exc
        self._user_pass = self._config.get("user_pass", "1234")
        self._cfg_path = self._config.get("cfg_path", "/etc/kamailio/kamailio.cfg")
        self._iface_dut = "eth1"
        self._ipv4_address = get_static_ipaddress(self._config, "ipv4")
        self._ipv6_address = get_static_ipaddress(self._config, "ipv6")
        self._fqdn = "sipcenter.boardfarm.com"
        self._db_user = self._config.get("db_user", "root")
        self._db_pass = self._config.get("db_pass", "test")
        self._db_name = self._config.get("db_name", "kamailio")
        # FQDN is a temporary fix, the value will be fetched from kamailio running conf

    @hookimpl
    def boardfarm_server_boot(self) -> None:
        """Boardfarm hook implementation to boot the sipcenter."""
        _LOGGER.info("Booting %s(%s) device", self.device_name, self.device_type)
        self._connect()

    @hookimpl
    def boardfarm_skip_boot(self) -> None:
        """Boardfarm hook implementation to initialize the sipcenter."""
        self._connect()

    @hookimpl
    async def boardfarm_skip_boot_async(self) -> None:
        """Boardfarm hook implementation to initialize the sipcenter asynchronously."""
        _LOGGER.info(
            "Initializing %s(%s) device with skip-boot option",
            self.device_name,
            self.device_type,
        )
        await self._connect_async()

    # TODO: This is in progress and will be modified in further commits
    @hookimpl
    def boardfarm_server_configure(self) -> None:
        """Boardfarm server configuration to initiliase env.json variables.

        This method expects that the listening IPs and aliases are defined
        correctly during docker server boot. Other user/tester control parameters
        have been managed here to ensure clean working setup for the user.
        """
        self._setup_static_routes()
        existing_users = self.get_all_users()
        # remove all existing users
        for number in existing_users:
            self.remove_endpoint(number)

        # add the users as defined in the inventory.json
        for number in self._users:
            self.add_user(number, self._user_pass)

        self._configure_rtpengine()

        # set expire timer to 180 and restart kamailio
        self.set_expire_timer(180)

    @hookimpl
    def boardfarm_shutdown_device(self) -> None:
        """Boardfarm hook implementation to shutdown the sipcenter device."""
        _LOGGER.info("Shutdown %s(%s) device", self.device_name, self.device_type)
        self._disconnect()

    @property
    def name(self) -> str:
        """Return the SIP server name.

        :return: server name
        :rtype: str
        """
        return str(self._config["name"])

    @property
    def iface_dut(self) -> str:
        """Return the DUT connected interface.

        :return: the DUT connected interface
        :rtype: str
        """
        return self._iface_dut

    # TODO: Review BOARDFARM-5108 for this method
    @property
    def ipv4_addr(self) -> str | None:
        """Return the server IP v4 address.

        :return: IP v4 address
        :rtype: str | None
        """
        return self._ipv4_address

    # TODO: Review BOARDFARM-5108 for this method
    @property
    def ipv6_addr(self) -> str | None:
        """Return the server IP v6 address.

        :return: IP v6 address
        :rtype: str | None
        """
        return self._ipv6_address

    # TODO: Review BOARDFARM-5108 for this method
    @property
    def fqdn(self) -> str | None:
        """FQDN of Kamailio.

        :return: FQDN of Kamailio.
        :rtype: str
        """
        return self._fqdn

    def _configure_rtpengine(self) -> None:
        """Configure RTPengine on kamailio based on the SKU of the board."""
        self._console.execute_command("killall -9 rtpengine")
        self._console.execute_command(
            f" rtpengine --listen-ng=localhost:2223 --interface={self.ipv4_addr}"
        )

    def get_online_users(self) -> str:
        """Get SipServer online users.

        :return: the online users
        :rtype: str
        """
        return self._console.execute_command("kamctl online")

    def get_status(self) -> str:
        """Check the kamailio status.

        :return: the status of the sipserver(Running/Not installed/Not Running)
        :rtype: str
        """
        output = self._console.execute_command("service kamailio status")
        if "kamailio is running" in output:
            return "Running"
        if "command not found" in output:
            return "Not installed"
        return "Not Running"

    def remove_endpoint(self, endpoint: str) -> None:
        """Remove endpoint from the directory.

        :param endpoint: the endpoint entry to be added
        :type endpoint: str
        :raises ValueError: when subscriber doesn't exist in the database
        """
        output = self._console.execute_command(f"kamctl rm {endpoint}")
        if output:
            msg = "Provided subscriber doesn't exist"
            raise ValueError(msg)

    def restart(self) -> None:
        """Restart the kamailio server."""
        self._console.execute_command("service kamailio restart")

    def start(self) -> None:
        """Start the kamailio server."""
        self._console.execute_command("service kamailio start")

    def stop(self) -> None:
        """Stop the kamailio server."""
        self._console.execute_command("service kamailio stop")

    def get_expire_timer(self) -> int:
        """Get the call expire timer in kamailio.cfg.

        :return: expiry timer saved in the config
        :rtype: int
        """
        max_expires: str = self._console.execute_command(
            f"grep --colour=never 'max_expires' {self._cfg_path}"
        )
        # In the kamailio.cfg, expire timer is defined as below
        # modparam("registrar", "max_expires", 180)'
        return int(max_expires.split(sep=",")[-1].replace(")", "").strip())

    def set_expire_timer(self, to_timer: int = 60) -> None:
        """Modify call expire timer in kamailio.cfg and restart the server.

        :param to_timer: Expire timer value change to, default to 60
        :type to_timer: int
        """
        cmd_str = """sed -i -e 's|"max_expires","""
        self._console.execute_command(
            rf"""{cmd_str} [[:digit:]]\+|"max_expires", {to_timer}|' {self._cfg_path}"""
        )
        self.restart()

    def add_user(
        self,
        user: str,
        password: str | None = None,
    ) -> None:
        """Add user to the directory.

        :param user: the endpoint entry to be added
        :type user: str
        :param password: the password of the endpoint
        :type password: str
        :raises ValueError: input is empty or subscriber already exists
        """
        if not password:
            msg = "Password is mandatory"
            raise ValueError(msg)
        if not user:
            msg = "User is mandatory"
            raise ValueError(msg)

        output = self._console.execute_command(f"kamctl add {user} {password}")
        if f"new user '{user}' added" not in output:
            msg = f"{user} exists already"
            raise ValueError(msg)

    def get_all_users(self) -> list:
        """Get all existing users in the kamailio database.

        :raises VoiceError: If database doesn't exist or some other error
        :returns: existing users in the database
        :rtype: list
        """
        db_login_cmd = f"mysql -u {self._db_user} -p{self._db_pass}"
        db_select_cmd = f"USE {self._db_name}"
        db_find_user_cmd = "SELECT username FROM subscriber"
        user_data = (
            self._console.execute_command(
                f'{db_login_cmd} -e "{db_select_cmd};{db_find_user_cmd};"',
            )
            .strip()
            .split("\n")
        )
        if self._console.execute_command("echo $?") != "0":
            raise VoiceError(self._console.get_last_output())
        return [user.strip().split("|")[1].strip() for user in user_data[3:-1]]

    def get_vsc_prefix(self, scope: VscScopeType) -> str:
        """Get prefix to build a VSC.

        It is expected that, to enable call forwarding, the phone dials a pattern as:
        "{prefix}{phone_number}#".

        It is is expected that all prefixes to disable call forwarding terminate with
        `#` to execute the VSC.

        .. code-block:: python

            # example output
            "*63*"  # to activate call forwarding busy

            "#63#"  # to disable call forwarding busy

        :param scope: Set/Unset call forwarding in case of busy/no answer/unconditional
        :type scope: VscScopeType
        :raises ValueError: CF scope doesn't match
        :raises FileNotFoundError: kamailio.cfg doesn't exist
        :return: the prefix to be dialled
        :rtype: str
        """
        if scope not in self._vsc_dict:
            msg = f"Invalid scope: {scope}"
            raise ValueError(msg)

        cf_variable = f"#!define {self._vsc_dict[scope]}"
        command = f"cat {self._cfg_path} | grep '{cf_variable}'"
        code = self._console.execute_command(command)

        if not code:
            msg = f"{cf_variable} not found in the config"
            raise ValueError(msg)

        file_error = "No such file or directory"
        if file_error in code:
            raise FileNotFoundError(file_error)

        # Apply transformations
        code = re.sub(r"\.\*", "", code)  # Remove .* occurences
        code = re.sub(
            r"[^\*\d%23]", "", code
        )  # Remove all characters except *, digits, and %23

        # Format the code based on cf set or unset

        if scope.startswith("set_"):
            code = re.sub(r"%23", "", code)
            code = re.sub(r"\*\*", "*", code)  # ensuring no ** is returned
        elif scope.startswith("unset_"):
            code = re.sub(r"%23", "#", code)
        return f"{code}"

    def _set_cf_vsc(self) -> None:
        """Set the call forwarding VSC in kamailio.cfg based on the env.json.

        Default kamailio config contains the pre-defined codes for all types of CF.
        Only the applicable codes defined in the env.json as per the SKU
        will overwrite the exisiting codes in the kamailio.cfg.
        CF is a SIP server feature, hence no impact is expected even
        if unsed VSC exists in the config.

        :raises FileNotFoundError: kamailio.cfg doesn't exist
        :raises ValueError: CF scope not found in the kamailio config
        """
        # Read the "cf_vsc" values from the env.json
        for scope, code in self._config["cf_vsc"].items():
            command = f"grep '#!define {scope}' {self._cfg_path}"
            current_vsc_str = self._console.execute_command(command).strip()

            error_msg = "No such file or directory"
            if error_msg in current_vsc_str:
                msg = f"Kamailio config not found in defined path: {self._cfg_path}"
                raise FileNotFoundError(msg)

            if not current_vsc_str:
                msg = f"{scope} not found in the config. Check kamailio running config."
                raise ValueError(msg)

            # Create the new VSC string with the code from env.json
            new_vsc_str = f'#!define {scope} "{code}"'

            # Escape strings for sed
            current_vsc_str = re.escape(current_vsc_str)
            new_vsc_str = re.escape(new_vsc_str)

            # Replace the line in the running config with the new values from env.json
            command = f"sed -i 's|{current_vsc_str}|{new_vsc_str}|' {self._cfg_path}"
            self._console.execute_command(command)

    # this is a temporary fix to test use cases and will be revisited
    def allocate_number(self, number: str | None = None) -> str:
        """Allocate a number from the sipserver number list.

        :param number: allocate a number (or select a random one), defaults to None
        :type number: str | None
        :return: the allocated number
        :rtype: str
        :raises VoiceError: number doesn't exist in the user list
        """
        if number and number in self._users:
            return number
        msg = f"provided number:- {number},not present in the user list {self._users}"
        raise VoiceError(msg)


if __name__ == "__main__":
    # stubbed instantation of the device
    # this would throw a linting issue in case the device does not follow the template
    from argparse import Namespace

    SIPcenterKamailio5(config={}, cmdline_args=Namespace())
