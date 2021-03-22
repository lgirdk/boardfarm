from abc import abstractmethod

from boardfarm.devices.debian import DebianBox
from boardfarm.lib.signature_checker import __MetaSignatureChecker


class SIPTemplate(DebianBox, metaclass=__MetaSignatureChecker):
    """SIP server template class.
    Contains basic list of APIs to be able to use TR069 intercation with CPE
    All methods, marked with @abstractmethod annotation have to be implemented in derived
    class with the same signatures as in template. You can use 'pass' keyword if you don't
    need some methods in derived class.
    """

    @property
    @abstractmethod
    def model(cls):
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
