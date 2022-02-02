"""Boardfarm TFTP device template."""

from abc import ABC, abstractmethod


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
