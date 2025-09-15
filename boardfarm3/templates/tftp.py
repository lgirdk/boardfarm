"""Boardfarm TFTP device template."""

from abc import ABC, abstractmethod
from collections.abc import Generator
from contextlib import contextmanager
from ipaddress import IPv4Address


class TFTP(ABC):
    """Boardfarm TFTP device template."""

    @abstractmethod
    def download_image_from_uri(self, image_uri: str) -> str:
        """Download image from given URI.

        :param image_uri: image URI
        :returns: downloaded image name
        """
        raise NotImplementedError

    @abstractmethod
    def get_eth_interface_ipv4_address(self) -> str:
        """Get eth interface ipv4 address.

        :returns: IPv4 address of eth interface
        """
        raise NotImplementedError

    @abstractmethod
    def restart_lighttpd(self) -> None:
        """Restart lighttpd service."""
        raise NotImplementedError

    @abstractmethod
    def stop_lighttpd(self) -> None:
        """Stop the lighttpd service."""
        raise NotImplementedError

    @abstractmethod
    @contextmanager
    def set_tmp_static_ip(
        self, static_address: IPv4Address
    ) -> Generator[None, None, None]:
        """Temporarily set a static IPv4 on the DUT connected iface via the `ip` cmd.

        :param static_address: Static IPv4 address to be set
        :type static_address: IPv4Address
        :yield: The DUT connected interface with the static ip address applied
        :rtype: Generator[None, None, None]
        """
        raise NotImplementedError
