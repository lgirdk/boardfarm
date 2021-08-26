from abc import ABC, abstractmethod

from boardfarm.devices.linux import LinuxInterface
from boardfarm.lib.signature_checker import __MetaSignatureChecker


class SIPTemplate(LinuxInterface, metaclass=__MetaSignatureChecker):
    """SIP server template class.
    Contains basic list of APIs to be able to use TR069 intercation with CPE
    All methods, marked with @abstractmethod annotation have to be implemented in derived
    class with the same signatures as in template. You can use 'pass' keyword if you don't
    need some methods in derived class.
    """

    @property
    @abstractmethod
    def model(self):
        """This attribute is used by boardfarm to match parameters entry from config
        and initialise correct object.
        This property shall be any string value that matches the "type"
        attribute of SIP entry in the inventory config file.
        See devices/kamailio.py as a reference
        """

    @abstractmethod
    def __init__(self, *args, **kwargs) -> None:
        """Initialize SIP parameters.
        Config data dictionary will be unpacked and passed to init as kwargs.
        You can use kwargs in a following way:
            self.username = kwargs.get("username", "DEFAULT_USERNAME")
            self.password = kwargs.get("password", "DEFAULT_PASSWORD")
        """
        super().__init__(*args, **kwargs)

    @abstractmethod
    def sipserver_install(self) -> None:
        """Install sipserver."""

    @abstractmethod
    def sipserver_purge(self) -> None:
        """To purge the sipserver installation."""

    @abstractmethod
    def sipserver_configuration(self) -> None:
        """Configure sipserver."""

    @abstractmethod
    def sipserver_start(self) -> None:
        """Start the server"""

    @abstractmethod
    def sipserver_stop(self) -> None:
        """Stop the server."""

    @abstractmethod
    def sipserver_restart(self) -> None:
        """Restart the server."""

    @abstractmethod
    def sipserver_status(self) -> str:
        """Return the status of the server."""

    @abstractmethod
    def sipserver_kill(self) -> None:
        """Kill the server."""

    @abstractmethod
    def sipserver_user_add(self, user: str, password: str) -> None:
        """Add user to the directory."""

    @abstractmethod
    def sipserver_user_remove(self, user: str) -> None:
        """Remove a user from the directory."""

    @abstractmethod
    def sipserver_user_update(self, user: str, password: str) -> None:
        """Update user in the directory."""

    @abstractmethod
    def sipserver_user_registration_status(self, user: str, ip_address: str) -> str:
        """Return the registration status."""


class SIPPhoneTemplate(LinuxInterface, ABC):
    @property
    @abstractmethod
    def model(self):
        """This attribute is used by boardfarm device manager.

        This is used to match parameters entry from config
        and initialise correct object.

        This property shall be any string value that matches the "type"
        attribute of FSX entry in the inventory config file.
        See devices/serialphone.py as a reference
        """

    @property
    @abstractmethod
    def number(self):
        """To get the registered SIP number.

        This property shall be dynamically populated during the post_boot
        activities of environment setup for voice.
        """

    @abstractmethod
    def phone_start(self) -> None:
        """Connect to the serial line of FXS modem.

        :param baud: serial baud rate, defaults to "115200"
        :type baud: str, optional
        :param timeout: connection timeout, defaults to "1"
        :type timeout: str, optional
        """

    @abstractmethod
    def phone_config(self, sip_server: str = "") -> None:
        """Configure the phone with a SIP url using SIP server IP for registration."""

    @abstractmethod
    def phone_kill(self) -> None:
        """Close the serial connection."""

    @abstractmethod
    def on_hook(self) -> None:
        """Execute on_hook procedure to disconnect to a line."""

    @abstractmethod
    def off_hook(self) -> None:
        """Execute off_hook procedure to connect to a line."""

    @abstractmethod
    def answer(self) -> bool:
        """To answer a call on RING state."""

    @abstractmethod
    def call(self, callee: "SIPPhoneTemplate") -> None:
        """To dial a call to callee.

        FXS modems simulate analog phones and requie ISDN/PSTN number to dial.
        In case of dialing a SIP enabled phone, SIP proxy IP is used
        to auto-generate a SIP URL for dialing.

        :param callee: Device which will act as the callee.
        :type callee: SIPPhoneTemplate
        """

    @abstractmethod
    def is_ringing(self) -> bool:
        """Check if Phone is ringing.

        :return: True if the phone is ringing
        :rtype: bool
        """

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if Phone is ringing.

        :return: True if the phone is ringing
        :rtype: bool
        """

    @abstractmethod
    def detect_dialtone(self) -> bool:
        """Check if dialtone is detected off_hook

        :return:
        :rtype: bool
        """

    @abstractmethod
    def is_line_busy(self) -> bool:
        """Check if the call is denied due to callee being busy.

        :return: True if line is busy, else False
        :rtype: bool
        """

    @abstractmethod
    def reply_with_code(self, code: int) -> None:
        """To reply back to an incoming call with a SIP code value.

        In case of certain phones, we need to explicitly send out SIP codes
        such as:
        - 486 Busy
        - 200 OK
        - 603 Decline
        - 608 Rejected

        :param code: SIP code value
        :type code: int
        """

    @abstractmethod
    def is_call_not_answered(self) -> bool:
        """Verify if caller's call was not answered

        :return: True if not answered, else False
        :rtype: bool
        """
