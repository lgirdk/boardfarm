# ruff: noqa: FA100

"""SIPServer Template module."""

from abc import ABC, abstractmethod
from collections.abc import Generator
from contextlib import contextmanager
from typing import Literal, Optional

from debtcollector import moves

VscScopeType = Literal[
    "set_cf_busy",
    "unset_cf_busy",
    "set_cf_no_answer",
    "unset_cf_no_answer",
    "set_cf_unconditional",
    "unset_cf_unconditional",
]


# pylint: disable=too-many-public-methods
class SIPServer(ABC):
    """SIP Server template class.

    Contains a list of APIs to interact with the SIP server.
    All methods marked with @abstractmethod annotation have to be implemented
    in the derived class with the same signatures as in template.
    Unsupported functionality shall raise a NotSupportedError exception.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the SIP server name.

        :return: server name
        :rtype: str
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def iface_dut(self) -> str:
        """Return the DUT connected interface."""
        raise NotImplementedError

    @property
    def ipv4_addr(self) -> Optional[str]:
        """Return the server IP v4 address.

        :raises NotImplementedError: not implemented yet
        """
        raise NotImplementedError

    @property
    def ipv6_addr(self) -> Optional[str]:
        """Return the server IP v6 address.

        :raises NotImplementedError: not implemented yet
        """
        raise NotImplementedError

    @property
    def fqdn(self) -> Optional[str]:
        """Return the sipserver fqdn.

        :raises NotImplementedError: not implemented yet
        """
        raise NotImplementedError

    @abstractmethod
    def start(self) -> None:
        """Start the server."""
        raise NotImplementedError

    @moves.moved_method("start")
    def sipserver_start(self) -> None:
        """Start the server.

        :return: None
        """
        return self.start()

    @abstractmethod
    def stop(self) -> None:
        """Stop the server.

        :return: None
        """
        raise NotImplementedError

    @moves.moved_method("stop")
    def sipserver_stop(self) -> None:
        """Stop the server.

        :return: None
        """
        return self.stop()

    @abstractmethod
    def restart(self) -> None:
        """Restart the server.

        :return: None
        """
        raise NotImplementedError

    @moves.moved_method("restart")
    def sipserver_restart(self) -> None:
        """Restart the server.

        :return: None
        """
        return self.restart()

    @abstractmethod
    def get_status(self) -> str:
        """Return the status of the server.

        :return: the status of the server
        :rtype: str
        """
        raise NotImplementedError

    @moves.moved_method("get_status")
    def sipserver_status(self) -> str:
        """Return the status of the server.

        :return: the status of the server
        :rtype: str
        """
        return self.get_status()

    # TODO: why is this a string and not a list of strings?
    @abstractmethod
    def get_online_users(self) -> str:
        """Get SipServer online users.

        :return: the online users
        :rtype: str
        """
        raise NotImplementedError

    @moves.moved_method("get_online_users")
    def sipserver_get_online_users(self) -> str:
        """Get SipServer online users.

        :return: the online users
        :rtype: str
        """
        return self.get_online_users()

    @abstractmethod
    def add_user(
        self,
        user: str,
        password: Optional[str] = None,
    ) -> None:
        """Add user to the directory.

        :param user: the user entry to be added
        :type user: str
        :param password: the password of the endpoint is determined by the user
        :type password: Optional[str]
        """
        raise NotImplementedError

    @moves.moved_method("add_user")
    def sipserver_user_add(
        self,
        user: str,
        password: Optional[str] = None,
    ) -> None:
        """Add user to the directory.

        :param user: the user entry to be added
        :type user: str
        :param password: the password of the endpoint is determined by the user
        :type password: Optional[str]
        :return: None
        """
        return self.add_user(user=user, password=password)

    @abstractmethod
    def remove_endpoint(self, endpoint: str) -> None:
        """Remove an endpoint from the directory.

        :param endpoint: the endpoint entry to be added
        :type endpoint: str
        :return: None
        """
        raise NotImplementedError

    @moves.moved_method("remove_endpoint")
    def remove_endpoint_from_sipserver(self, endpoint: str) -> None:
        """Remove an endpoint from the directory.

        :param endpoint: the endpoint entry to be added
        :type endpoint: str
        :return: None
        """
        return self.remove_endpoint(endpoint=endpoint)

    @abstractmethod
    def allocate_number(self, number: Optional[str] = None) -> str:
        """Allocate a number from the sipserver number list.

        :param number: the phone number, defaults to None
        :type number: Optional[str]
        :return: the allocated number
        :rtype: str
        """
        raise NotImplementedError

    @moves.moved_method("ipv4_addr")
    def get_interface_ipaddr(self) -> Optional[str]:
        """Return the IPv4 address of the DUT connected interface.

        This method is deprecated in favour of reading the `ipv4_addr` property.

        :return: the IPv4 address
        :rtype: Optional[str]
        """
        return self.ipv4_addr

    @contextmanager
    @abstractmethod
    def tcpdump_capture(
        self,
        fname: str,
        interface: str = "any",
        additional_args: Optional[str] = None,
    ) -> Generator[str, None, None]:
        """Capture packets from specified interface.

        Packet capture using tcpdump utility at a specified interface.

        :param fname: name of the file where packet captures will be stored
        :type fname: str
        :param interface: name of the interface, defaults to "any"
        :type interface: str
        :param additional_args: arguments to tcpdump command, defaults to None
        :type additional_args: Optional[str]
        :return: process id of tcpdump process
        :rtype: Generator[str, None, None]
        """
        raise NotImplementedError

    @abstractmethod
    def tshark_read_pcap(
        self,
        fname: str,
        additional_args: Optional[str] = None,
        timeout: int = 30,
        rm_pcap: bool = False,
    ) -> str:
        """Read packet captures from an existing file.

        :param fname: name of the file in which captures are saved
        :type fname: str
        :param additional_args: additional arguments for tshark, defaults to None
        :type additional_args: Optional[str], optional
        :param timeout: timeout for tshark command to be executed, defaults to 30
        :type timeout: int
        :param rm_pcap: remove the pcap file after reading if True, defaults to False
        :type rm_pcap: bool
        :return: return tshark read command console output
        :rtype: str
        """
        raise NotImplementedError

    @abstractmethod
    def get_expire_timer(self) -> int:
        """Get the call expire timer in the sipserver config.

        :return: expiry timer saved in the config
        :rtype: int
        """
        raise NotImplementedError

    @moves.moved_method("get_expire_timer")
    def sipserver_get_expire_timer(self) -> int:
        """Get the call expire timer in the sipserver config.

        :return: expiry timer saved in the config
        :rtype: int
        """
        return self.get_expire_timer()

    @abstractmethod
    def set_expire_timer(self, to_timer: int = 60) -> None:
        """Modify call expire timer in the sipserver config.

        :param to_timer: Expire timer value change to, default to 60
        :type to_timer: int
        """
        raise NotImplementedError

    @moves.moved_method("set_expire_timer")
    def sipserver_set_expire_timer(self, to_timer: int = 60) -> None:
        """Modify call expire timer in the sipserver config.

        :param to_timer: Expire timer value change to, default to 60
        :type to_timer: int
        :return: None
        """
        return self.set_expire_timer(to_timer=to_timer)

    @abstractmethod
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
        :raises NotImplementedError: as this is a Template
        :return: the prefix to be dialled
        :rtype: str
        """
        raise NotImplementedError

    @abstractmethod
    def delete_file(self, filename: str) -> None:
        """Delete the file from the device.

        :param filename: name of the file with absolute path
        :type filename: str
        """
        raise NotImplementedError

    @abstractmethod
    def scp_device_file_to_local(self, local_path: str, source_path: str) -> None:
        """Copy a local file from a server using SCP.

        :param local_path: local file path
        :param source_path: source path
        """
        raise NotImplementedError
