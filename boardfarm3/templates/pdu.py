"""Define the PDU template."""

from abc import ABC, abstractmethod


class PDU(ABC):
    """PDU template to be implemented."""

    @abstractmethod
    def __init__(self, uri: str) -> None:
        """Initialise the PUD object.

        examples of PDU uris:

            NetIO:        "10.64.40.34; 2"
            Raritan PX2:  "10.71.10.53:23; 2"
            Raritan PX3:  "10.71.10.53:22; 1"

        No type is passed to the PDU only the connection parameters.

        :param uri: a string relating to the PDU access params
        :type uri: str
        """
        raise NotImplementedError

    @abstractmethod
    def power_off(self) -> bool:
        """Power OFF the given PDU outlet.

        :returns: True on success
        """
        raise NotImplementedError

    @abstractmethod
    def power_on(self) -> bool:
        """Power ON the given PDU outlet.

        :returns: True on success
        """
        raise NotImplementedError

    @abstractmethod
    def power_cycle(self) -> bool:
        """Power cycle the given PDU outlet.

        :returns: True on success
        """
        raise NotImplementedError
